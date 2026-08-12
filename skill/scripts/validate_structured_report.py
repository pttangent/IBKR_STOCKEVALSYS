#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path

STATES = {"RESEARCH_READY", "READY_CONDITIONAL", "WAIT_CONFIRMATION", "NEEDS_EVIDENCE", "RISK_BLOCKED", "MONITOR_ONLY", "THESIS_INVALIDATED"}
REQUIRED_MODULE = {"title", "status", "freshness_status", "source_artifacts", "missing_fields"}
REQUIRED_INTERPRETATION = {"what", "what_observed", "read", "read_result", "why", "why_now", "limit", "limit_effect"}
REQUIRED_SCENARIO_NODE = {"id", "label", "trigger", "watch", "interpretation", "response", "invalidation", "action_boundary", "sizing_tier", "price_reference", "price_anchors", "children"}
REQUIRED_PRICE_ANCHOR = {"id", "label", "value", "role", "source", "method", "confidence", "status"}
SIZING_TIERS = {"none", "quarter", "half", "full_diagnostic", "risk_only"}
LONG_TERM_TECHNICAL_TOKENS = ("現價", "股價", "支撐", "阻力", "壓力", "EMA", "SMA", "VWAP", "ORH", "ORL", "ATR", "突破", "跌破", "回踩", "反抽", "收復", "前高", "前低")


def _parse_time(value):
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _validate_price_anchor(anchor: dict, path: str, errors: list[str]) -> None:
    if not isinstance(anchor, dict):
        errors.append(f"{path} must be object")
        return
    for key in REQUIRED_PRICE_ANCHOR:
        if key not in anchor:
            errors.append(f"{path} missing {key}")
    value = anchor.get("value")
    if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        errors.append(f"{path} invalid value")
    for key in ["id", "label", "role", "source", "method", "confidence", "status"]:
        if key in anchor and not str(anchor.get(key) or "").strip():
            errors.append(f"{path} empty {key}")


def _validate_scenario_node(node: dict, path: str, errors: list[str], *, horizon: str | None = None) -> None:
    if not isinstance(node, dict):
        errors.append(f"{path} must be object")
        return
    for key in REQUIRED_SCENARIO_NODE:
        if key not in node:
            errors.append(f"{path} missing {key}")
    for key in ["id", "label", "trigger", "interpretation", "response", "invalidation", "action_boundary"]:
        if key in node and not str(node.get(key) or "").strip():
            errors.append(f"{path} empty {key}")
    if node.get("sizing_tier") not in SIZING_TIERS:
        errors.append(f"{path} invalid sizing_tier")
    if not isinstance(node.get("watch", []), list):
        errors.append(f"{path} watch must be list")
    if not isinstance(node.get("price_reference", {}), dict):
        errors.append(f"{path} price_reference must be object")
    anchors = node.get("price_anchors", [])
    if not isinstance(anchors, list):
        errors.append(f"{path} price_anchors must be list")
    else:
        for index, anchor in enumerate(anchors):
            _validate_price_anchor(anchor, f"{path}.price_anchors[{index}]", errors)
        reference = node.get("price_reference", {})
        for anchor in anchors:
            if isinstance(anchor, dict) and anchor.get("id") in reference and reference.get(anchor.get("id")) != anchor.get("value"):
                errors.append(f"{path} price_reference does not tie to price_anchors for {anchor.get('id')}")
    if horizon == "long_term":
        # Purity applies to the condition that selects a branch and the KPI watch
        # list. Explanatory prose may explicitly say that price/VWAP must NOT be
        # used, and a valuation response may legitimately ask whether price has
        # already discounted the new economics.
        causal_inputs = " ".join([str(node.get("trigger") or ""), " ".join(str(x) for x in node.get("watch", []) if x is not None)])
        if any(token in causal_inputs for token in LONG_TERM_TECHNICAL_TOKENS):
            errors.append(f"{path} long-term trigger/watch contains technical price-action condition")
        if anchors or node.get("price_reference"):
            errors.append(f"{path} long-term scenario must not carry technical price anchors")
    children = node.get("children", [])
    if not isinstance(children, list):
        errors.append(f"{path} children must be list")
        return
    for index, child in enumerate(children):
        _validate_scenario_node(child, f"{path}.children[{index}]", errors, horizon=horizon)


def _validate_kelly_guidance(module: dict, errors: list[str]) -> None:
    metrics = module.get("metrics", {}) or {}
    guidance = metrics.get("position_guidance", {})
    kelly = metrics.get("kelly", {}) or {}
    if not isinstance(guidance, dict) or not guidance:
        return
    if guidance.get("portfolio_value_source") == "default_10000_simulation" and guidance.get("portfolio_value") != 10000.0:
        errors.append("risk position_guidance default simulation must be 10000")
    variants = guidance.get("variants", {})
    full = kelly.get("full_sample", {}) or {}
    formula = kelly.get("full_sample_formula", {}) or {}
    trades = int(full.get("trades") or 0)
    if isinstance(variants, dict) and variants:
        if trades < 10:
            errors.append("risk position_guidance cannot expose Kelly variants with fewer than 10 completed setup trades")
        if full.get("at_grid_cap") and formula.get("raw_formula_kelly_fraction") is None:
            errors.append("risk position_guidance cannot use grid-cap empirical Kelly when p/b Kelly is undefined")
    if not isinstance(variants, dict) or not variants:
        return
    present = [label for label in ("full", "half", "quarter") if label in variants]
    if present and present != ["full", "half", "quarter"]:
        errors.append("risk position_guidance Kelly ladder must expose full, half, quarter together")
        return
    finals = []
    portfolio = guidance.get("portfolio_value")
    for label in ("full", "half", "quarter"):
        item = variants.get(label, {})
        final = item.get("final_fraction")
        if not isinstance(final, (int, float)) or final < 0:
            errors.append(f"risk position_guidance {label} invalid final_fraction")
            continue
        finals.append(final)
        notional = item.get("notional_dollars")
        if isinstance(portfolio, (int, float)) and isinstance(notional, (int, float)):
            expected = portfolio * final
            if not math.isclose(notional, expected, rel_tol=1e-9, abs_tol=1e-6):
                errors.append(f"risk position_guidance {label} notional does not tie to portfolio*fraction")
    if len(finals) == 3 and not (finals[0] >= finals[1] >= finals[2]):
        errors.append("risk position_guidance final fractions must be non-increasing full >= half >= quarter")


def _validate_pit(data: dict, errors: list[str]) -> None:
    generated = _parse_time(data.get("generated_at"))
    if not generated:
        return
    cutoff = _parse_time(data.get("evidence_cutoff"))
    price = _parse_time(data.get("price_timestamp"))
    if cutoff and cutoff > generated:
        errors.append("evidence_cutoff must not be later than generated_at")
    if price and price > generated:
        errors.append("price_timestamp must not be later than generated_at")


def validate(data: dict) -> list[str]:
    errors: list[str] = []
    for key in ["schema_version", "run_id", "symbol", "as_of", "research_state", "modules"]:
        if key not in data:
            errors.append(f"missing top-level {key}")
    if data.get("research_state") not in STATES:
        errors.append("invalid research_state")
    _validate_pit(data, errors)
    if not isinstance(data.get("modules"), dict):
        errors.append("modules must be object")
        return errors
    for name, module in data["modules"].items():
        if not isinstance(module, dict):
            errors.append(f"module {name} not object")
            continue
        for key in REQUIRED_MODULE:
            if key not in module:
                errors.append(f"module {name} missing {key}")
        for index, chart in enumerate(module.get("charts", [])):
            if not all(chart.get(key) for key in ["id", "kind", "title"]):
                errors.append(f"module {name} chart {index} missing id/kind/title")
            interpretation = chart.get("interpretation", {})
            for key in REQUIRED_INTERPRETATION:
                if not str(interpretation.get(key) or "").strip():
                    errors.append(f"module {name} chart {chart.get('id', index)} missing interpretation.{key}")
        for index, tree in enumerate(module.get("scenario_trees", [])):
            if not isinstance(tree, dict):
                errors.append(f"module {name} scenario tree {index} not object")
                continue
            for key in ["id", "horizon", "title", "evidence_status", "root"]:
                if key not in tree:
                    errors.append(f"module {name} scenario tree {index} missing {key}")
            horizon = tree.get("horizon")
            _validate_scenario_node(tree.get("root", {}), f"module {name} scenario tree {tree.get('id', index)}.root", errors, horizon=horizon)
            if horizon == "intraday":
                anchor_ids = {a.get("id") for a in tree.get("anchor_book", []) if isinstance(a, dict)}
                if "PRIOR_CLOSE" in anchor_ids:
                    errors.append("intraday scenario tree must not use prior close as structural anchor")
        if name == "risk":
            _validate_kelly_guidance(module, errors)
        if name == "options":
            quality = (((module.get("metrics", {}) or {}).get("gamma", {}) or {}).get("data_quality", {}) or {})
            positive = quality.get("rows_with_positive_open_interest")
            if isinstance(positive, (int, float)) and positive > 0 and "positive_open_interest" in (module.get("missing_fields", []) or []):
                errors.append("options cannot mark positive_open_interest missing when deterministic Gamma artifact contains positive OI rows")
        missing = module.get("missing_fields", [])
        resolutions = module.get("evidence_resolution", [])
        if missing and not isinstance(resolutions, list):
            errors.append(f"module {name} missing evidence_resolution for unresolved fields")
        if isinstance(resolutions, list):
            resolved_fields = {item.get("field") for item in resolutions if isinstance(item, dict)}
            for field in missing:
                if field not in resolved_fields:
                    errors.append(f"module {name} missing resolution record for {field}")
    return errors


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    args = ap.parse_args()
    data = json.loads(Path(args.report).read_text(encoding="utf-8"))
    errors = validate(data)
    if errors:
        raise SystemExit("FAIL structured report:\n- " + "\n- ".join(errors))
    print("OK structured report")


if __name__ == "__main__":
    main()
