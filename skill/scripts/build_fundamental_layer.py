#!/usr/bin/env python3
"""Build the role-aware fundamental layer consumed by single-stock reports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def endpoint_statuses(packet: dict[str, Any]) -> dict[str, str]:
    endpoints = ((packet.get("data") or {}).get("endpoints") or {})
    return {name: str(item.get("status", "unknown")) for name, item in endpoints.items() if isinstance(item, dict)}


def any_ok(statuses: dict[str, str]) -> bool:
    return any(status == "ok" for status in statuses.values())


def count_estimate_records(packet: dict[str, Any]) -> int:
    estimates = ((packet.get("data") or {}).get("earnings_estimates") or {})
    collections = estimates.get("collections") or {}
    count = sum(len(value) for value in collections.values() if isinstance(value, list))
    if count:
        return count
    raw = estimates.get("raw") or {}
    if isinstance(raw, dict):
        for key in ("estimates", "annualEstimates", "quarterlyEstimates"):
            value = raw.get(key)
            if isinstance(value, list):
                count += len(value)
    return count


def pit_status(packet: dict[str, Any], as_of: str) -> str:
    available_at = packet.get("available_at")
    if not available_at:
        return "CURRENT_SNAPSHOT_ONLY"
    return "PIT_QUALIFIED" if str(available_at)[:10] <= str(as_of)[:10] else "AFTER_CUTOFF"


def role_status(packet: dict[str, Any], statuses: dict[str, str] | None = None) -> str:
    if not packet:
        return "missing"
    if statuses is not None:
        return "ok" if any_ok(statuses) else "unavailable_or_empty"
    explicit = packet.get("status")
    if explicit:
        return str(explicit)
    return "ok"


def build_layer(*, symbol: str, as_of: str, sec: dict[str, Any], reconciled: dict[str, Any], simfin: dict[str, Any], alpha_vantage: dict[str, Any], finnhub: dict[str, Any], ibkr_fundamentals: dict[str, Any], alpaca: dict[str, Any]) -> dict[str, Any]:
    canonical = ((sec.get("data") or {}).get("canonical_financials") or {})
    sec_facts = canonical.get("facts") or {}
    sec_quality = canonical.get("quality") or {}
    simfin_status = endpoint_statuses(simfin)
    finnhub_status = endpoint_statuses(finnhub)
    alpaca_statuses = endpoint_statuses(alpaca)
    av_records = count_estimate_records(alpha_vantage)
    av_pit = pit_status(alpha_vantage, as_of) if alpha_vantage else "MISSING"
    ibkr_status = "missing"
    if ibkr_fundamentals:
        ibkr_status = str((ibkr_fundamentals.get("data") or {}).get("status") or ibkr_fundamentals.get("status") or "present")
    ratio_safe = bool((reconciled.get("quality") or {}).get("ratio_safe", sec_quality.get("ratio_safe", False)))
    roles = {
        "reported_truth": {"providers": ["SEC_EDGAR", "ISSUER_IR"], "status": "ok" if sec_facts else "needs_primary_source", "controls": ["reported_actuals", "filing_identity", "reported_period", "company_guidance_and_kpis"], "fact_count": len(sec_facts)},
        "standardization": {"providers": ["SIMFIN"], "status": role_status(simfin, simfin_status), "controls": ["normalized_schema", "peer_ready_fields", "cross_sectional_comparability"], "endpoint_statuses": simfin_status, "statement_mode": ((simfin.get("data") or {}).get("statement_mode"))},
        "expectations": {"providers": ["ALPHA_VANTAGE"], "status": "ok" if av_records > 0 else ("missing" if not alpha_vantage else "empty_or_limited"), "controls": ["eps_estimates", "revenue_estimates", "analyst_count", "estimate_revisions", "earnings_surprise_context"], "estimate_record_count": av_records, "pit_status": av_pit},
        "events_metadata_crosscheck": {"providers": ["FINNHUB"], "status": role_status(finnhub, finnhub_status), "controls": ["profile", "peers", "earnings_calendar", "earnings_surprise", "news", "basic_metric_crosscheck"], "endpoint_statuses": finnhub_status},
        "market_reaction": {"providers": ["ALPACA"], "status": role_status(alpaca, alpaca_statuses), "controls": ["iex_price_reaction", "iex_volume_reaction", "quotes", "corporate_actions", "news", "indicative_option_context"], "endpoint_statuses": alpaca_statuses, "data_lane": "research_non_ibkr", "accounting_fundamentals_allowed": False},
        "optional_legacy_fundamentals": {"providers": ["IBKR_REUTERS_FUNDAMENTALS"], "status": ibkr_status, "required_for_report_readiness": False},
    }
    readiness = {
        "reported_actuals": bool(sec_facts),
        "period_safe_ratios": bool(sec_facts) and ratio_safe,
        "peer_standardization": roles["standardization"]["status"] == "ok",
        "current_market_expectations": av_records > 0,
        "historical_pit_expectations": av_records > 0 and av_pit == "PIT_QUALIFIED",
        "event_metadata_context": roles["events_metadata_crosscheck"]["status"] == "ok",
        "market_reaction_context": roles["market_reaction"]["status"] == "ok",
        "ibkr_required_for_current_report": False,
        "fair_value_model": False,
    }
    limitations = []
    if not readiness["reported_actuals"]:
        limitations.append("SEC/issuer primary reported facts are missing; fundamental conclusions require primary-source evidence.")
    if not readiness["period_safe_ratios"]:
        limitations.append("Filing/period alignment is not ratio-safe; suppress same-period ratios that require incompatible facts.")
    if not readiness["peer_standardization"]:
        limitations.append("SimFin standardization is unavailable; peer/cross-sectional comparisons are downgraded, but SEC single-name facts remain usable.")
    if not readiness["current_market_expectations"]:
        limitations.append("Alpha Vantage expectations are unavailable/empty; consensus, revision, and priced-in claims must be downgraded.")
    elif not readiness["historical_pit_expectations"]:
        limitations.append("Alpha Vantage estimates are current-snapshot evidence only; do not use them for historical replay without timestamp-qualified snapshots.")
    if not readiness["event_metadata_context"]:
        limitations.append("Finnhub event/metadata context is incomplete; this does not invalidate SEC reported actuals.")
    if not readiness["market_reaction_context"]:
        limitations.append("Alpaca Research-Lane packet is absent; use Massive/yfinance timestamped research evidence or invoke IBKR only for a documented exception.")
    return {
        "schema_version": "1.0", "provider": "FUNDAMENTAL_ROLE_LAYER", "symbol": symbol.upper(), "as_of": as_of,
        "data_lane": "research_non_ibkr",
        "source_roles": roles,
        "gates": {"accounting_primary": "SEC_EDGAR/ISSUER_IR", "no_cross_role_substitution": True, "normalized_values_never_overwrite_reported_actuals": True, "expectations_never_overwrite_reported_actuals": True, "market_reaction_never_becomes_accounting_fact": True, "ibkr_reuters_optional": True, "research_prefers_non_ibkr": True, "ratio_safe": ratio_safe},
        "report_readiness": readiness,
        "report_order": ["reported_truth", "fundamental_trajectory", "standardization", "expectations", "events_metadata_crosscheck", "expectation_vs_actual", "market_reaction", "valuation_readiness", "conflicts_and_missing_evidence"],
        "limitations": limitations,
        "source_artifacts": {"sec": bool(sec), "reconciled": bool(reconciled), "simfin": bool(simfin), "alpha_vantage": bool(alpha_vantage), "finnhub": bool(finnhub), "ibkr_fundamentals": bool(ibkr_fundamentals), "alpaca": bool(alpaca)},
    }


def apply_to_report(run: Path, layer: dict[str, Any]) -> None:
    research_path = run / "research_content.json"
    if research_path.exists():
        research = load(research_path)
        modules = research.setdefault("modules", {})
        fundamental = modules.setdefault("fundamentals", {})
        fundamental["source_roles"] = layer["source_roles"]
        fundamental["report_readiness"] = layer["report_readiness"]
        fundamental["data_lane"] = layer["data_lane"]
        fundamental.setdefault("limitations", [])
        for item in layer["limitations"]:
            if item not in fundamental["limitations"]:
                fundamental["limitations"].append(item)
        blocks = fundamental.setdefault("blocks", [])
        status_text = "; ".join(f"{name}={value.get('status')}" for name, value in layer["source_roles"].items())
        blocks.insert(0, {"type": "paragraph", "title": "多源能力邊界 / Research Lane", "text": f"本次個股研究預設不佔用 IBKR/TWS。來源角色狀態：{status_text}。SEC/IR 控制 reported actual；SimFin 做標準化；Alpha Vantage 做市場預期；Finnhub 做事件/metadata；Alpaca 做 IEX 市場反應。IBKR Reuters 非必要條件。"})
        research_path.write_text(json.dumps(research, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest_path = run / "report_manifest.json"
    if manifest_path.exists():
        manifest = load(manifest_path)
        module = (manifest.setdefault("modules", {})).setdefault("fundamentals", {})
        artifacts = module.setdefault("source_artifacts", [])
        for name, present in layer["source_artifacts"].items():
            filename = {"sec": "sec_research.json", "reconciled": "fundamentals_reconciled.json", "simfin": "simfin_research.json", "alpha_vantage": "alpha_vantage_research.json", "finnhub": "finnhub_research.json", "ibkr_fundamentals": "ibkr_fundamentals.json", "alpaca": "alpaca_research.json"}[name]
            if present and filename not in artifacts:
                artifacts.append(filename)
        if "fundamental_layer.json" not in artifacts:
            artifacts.append("fundamental_layer.json")
        module["data_lane"] = "research_non_ibkr"
        module["provider_roles"] = layer["source_roles"]
        module["status"] = "complete" if layer["report_readiness"]["reported_actuals"] else "partial"
        missing = module.setdefault("missing_fields", [])
        role_missing = []
        if not layer["report_readiness"]["reported_actuals"]:
            role_missing.append("reported_truth")
        if not layer["report_readiness"]["peer_standardization"]:
            role_missing.append("peer_standardization")
        if not layer["report_readiness"]["current_market_expectations"]:
            role_missing.append("market_expectations")
        if not layer["report_readiness"]["event_metadata_context"]:
            role_missing.append("event_metadata_context")
        if not layer["report_readiness"]["market_reaction_context"]:
            role_missing.append("market_reaction_context")
        for item in role_missing:
            if item not in missing:
                missing.append(item)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Build role-aware fundamental report layer without merging provider values.")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--as-of", required=True)
    ap.add_argument("--output")
    ap.add_argument("--no-apply", action="store_true", help="Do not patch existing research_content/report_manifest artifacts.")
    args = ap.parse_args()
    run = Path(args.run_dir)
    output = Path(args.output) if args.output else run / "fundamental_layer.json"
    layer = build_layer(symbol=args.symbol, as_of=args.as_of, sec=load(run / "sec_research.json"), reconciled=load(run / "fundamentals_reconciled.json"), simfin=load(run / "simfin_research.json"), alpha_vantage=load(run / "alpha_vantage_research.json"), finnhub=load(run / "finnhub_research.json"), ibkr_fundamentals=load(run / "ibkr_fundamentals.json"), alpaca=load(run / "alpaca_research.json"))
    output.write_text(json.dumps(layer, ensure_ascii=False, indent=2), encoding="utf-8")
    if not args.no_apply:
        apply_to_report(run, layer)
    ready = layer["report_readiness"]
    print("OK fundamental layer %s lane=research_non_ibkr actuals=%s standardization=%s expectations=%s event_context=%s market_reaction=%s -> %s" % (args.symbol.upper(), ready["reported_actuals"], ready["peer_standardization"], ready["current_market_expectations"], ready["event_metadata_context"], ready["market_reaction_context"], output))


if __name__ == "__main__":
    main()
