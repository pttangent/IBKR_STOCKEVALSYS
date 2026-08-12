#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

STATES = {"RESEARCH_READY", "READY_CONDITIONAL", "WAIT_CONFIRMATION", "NEEDS_EVIDENCE", "RISK_BLOCKED", "MONITOR_ONLY", "THESIS_INVALIDATED"}
REQUIRED_MODULE = {"title", "status", "freshness_status", "source_artifacts", "missing_fields"}
REQUIRED_INTERPRETATION = {"what", "what_observed", "read", "read_result", "why", "why_now", "limit", "limit_effect"}
REQUIRED_SCENARIO_NODE = {"id", "label", "trigger", "watch", "interpretation", "response", "invalidation", "action_boundary", "sizing_tier", "price_reference", "price_anchors", "children"}
REQUIRED_PRICE_ANCHOR = {"id", "label", "value", "role", "source", "method", "confidence", "status"}
SIZING_TIERS = {"none", "quarter", "half", "full_diagnostic", "risk_only"}


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


def _validate_scenario_node(node: dict, path: str, errors: list[str]) -> None:
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
            if isinstance(anchor, dict) and anchor.get("id") in reference:
                if reference.get(anchor.get("id")) != anchor.get("value"):
                    errors.append(f"{path} price_reference does not tie to price_anchors for {anchor.get('id')}")
    children = node.get("children", [])
    if not isinstance(children, list):
        errors.append(f"{path} children must be list")
        return
    for index, child in enumerate(children):
        _validate_scenario_node(child, f"{path}.children[{index}]", errors)


def _validate_kelly_guidance(module: dict, errors: list[str]) -> None:
    guidance = module.get("metrics", {}).get("position_guidance", {})
    if not isinstance(guidance, dict) or not guidance:
        return
    if guidance.get("portfolio_value_source") == "default_10000_simulation" and guidance.get("portfolio_value") != 10000.0:
        errors.append("risk position_guidance default simulation must be 10000")
    variants = guidance.get("variants", {})
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


def validate(data: dict) -> list[str]:
    errors: list[str] = []
    for key in ["schema_version", "run_id", "symbol", "as_of", "research_state", "modules"]:
        if key not in data:
            errors.append(f"missing top-level {key}")
    if data.get("research_state") not in STATES:
        errors.append("invalid research_state")
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
            _validate_scenario_node(tree.get("root", {}), f"module {name} scenario tree {tree.get('id', index)}.root", errors)
            if tree.get("horizon") == "intraday":
                anchor_ids = {a.get("id") for a in tree.get("anchor_book", []) if isinstance(a, dict)}
                if "PRIOR_CLOSE" in anchor_ids:
                    errors.append("intraday scenario tree must not use prior close as structural anchor")
        if name == "risk":
            _validate_kelly_guidance(module, errors)
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
