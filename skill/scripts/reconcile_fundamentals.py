#!/usr/bin/env python3
"""Reconcile accounting identity without collapsing provider roles."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--as-of", required=True)
    ap.add_argument("--sec", required=True)
    ap.add_argument("--finnhub")
    ap.add_argument("--ibkr")
    ap.add_argument("--simfin")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    sec = load(Path(args.sec))
    canonical = ((sec.get("data") or {}).get("canonical_financials") or {})
    sec_facts = canonical.get("facts") or {}
    sec_quality = canonical.get("quality") or {}
    providers: dict[str, Any] = {"SEC_EDGAR": {"role": "reported_truth", "status": "ok" if sec_facts else "empty", "quality": sec_quality, "facts": sec_facts}}
    if args.simfin:
        sf = load(Path(args.simfin))
        endpoints = (sf.get("data") or {}).get("endpoints") or {}
        providers["SIMFIN"] = {"role": "standardization", "status": "ok" if any(item.get("status") == "ok" for item in endpoints.values() if isinstance(item, dict)) else "unavailable_or_empty", "packet": sf}
    if args.finnhub:
        fh = load(Path(args.finnhub))
        endpoints = (fh.get("data") or {}).get("endpoints") or {}
        providers["FINNHUB"] = {"role": "events_metadata_crosscheck", "status": "ok" if any(item.get("status") == "ok" for item in endpoints.values() if isinstance(item, dict)) else "unavailable_or_empty", "reported_financials_status": endpoints.get("financials_reported", {}).get("status", "not_requested"), "packet": fh}
    if args.ibkr:
        ib = load(Path(args.ibkr))
        providers["IBKR_REUTERS_FUNDAMENTALS"] = {"role": "optional_legacy_entitlement_probe", "status": (ib.get("data") or {}).get("status", "missing"), "packet": ib}
    conflicts = []
    if not sec_quality.get("duration_period_alignment", False):
        conflicts.append({"type": "period_alignment", "scope": "duration", "action": "block ratios and same-period comparisons"})
    if not sec_quality.get("instant_filing_alignment", False):
        conflicts.append({"type": "filing_alignment", "scope": "instant balance sheet", "action": "block balance-sheet cross-ratios"})
    result = {
        "schema_version": "1.1", "source_id": f"fundamentals-reconciled:{args.symbol.upper()}:{args.as_of}", "provider": "ROLE_AWARE_ACCOUNTING_RECONCILIATION", "symbol": args.symbol.upper(), "as_of": args.as_of,
        "primary_provider": "SEC_EDGAR",
        "source_roles": {"reported_truth": ["SEC_EDGAR", "ISSUER_IR"], "standardization": ["SIMFIN"], "events_metadata_crosscheck": ["FINNHUB"], "optional_legacy_entitlement_probe": ["IBKR_REUTERS_FUNDAMENTALS"], "expectations_excluded_from_accounting_merge": ["ALPHA_VANTAGE"], "market_reaction_excluded_from_accounting_merge": ["ALPACA", "IBKR_TWS"]},
        "facts": sec_facts,
        "quality": {**sec_quality, "primary_policy": "SEC/issuer IR remains accounting truth; other roles never overwrite reported actuals", "ratio_safe": bool(sec_quality.get("ratio_safe", False))},
        "providers": providers, "conflicts": conflicts,
        "warnings": ["No provider may repair an SEC period mismatch by silently substituting another period.", "SimFin normalized values remain standardization evidence until field/period mapping is verified.", "Finnhub is event/metadata/quick-cross-check context; its financial values do not control reported actuals.", "IBKR Reuters entitlement failure is a provider-access state, not missing company fundamentals.", "Alpha Vantage estimates and Alpaca/IBKR market reaction are intentionally outside accounting reconciliation."],
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK role-aware fundamentals reconciliation {args.symbol.upper()}: primary=SEC_EDGAR ratio_safe={result['quality']['ratio_safe']} conflicts={len(conflicts)} -> {args.output}")


if __name__ == "__main__":
    main()
