#!/usr/bin/env python3
"""Reconcile SEC, Finnhub and IBKR fundamentals without cross-period mixing."""
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
    providers: dict[str, Any] = {"SEC_EDGAR": {"status": "ok" if sec_facts else "empty", "quality": sec_quality, "facts": sec_facts}}
    if args.finnhub:
        fh = load(Path(args.finnhub))
        providers["FINNHUB"] = {"status": fh.get("data", {}).get("endpoints", {}).get("financials_reported", {}).get("status", "missing"), "packet": fh}
    if args.ibkr:
        ib = load(Path(args.ibkr))
        providers["IBKR_REUTERS_FUNDAMENTALS"] = {"status": (ib.get("data") or {}).get("status", "missing"), "packet": ib}
    if args.simfin:
        sf = load(Path(args.simfin))
        endpoints = (sf.get("data") or {}).get("endpoints") or {}
        providers["SIMFIN"] = {"status": "ok" if any(item.get("status") == "ok" for item in endpoints.values() if isinstance(item, dict)) else "unavailable_or_empty", "packet": sf}
    conflicts = []
    if not sec_quality.get("duration_period_alignment", False):
        conflicts.append({"type": "period_alignment", "scope": "duration", "action": "block ratios and same-period comparisons"})
    if not sec_quality.get("instant_filing_alignment", False):
        conflicts.append({"type": "filing_alignment", "scope": "instant balance sheet", "action": "block balance-sheet cross-ratios"})
    result = {
        "schema_version": "1.0", "source_id": f"fundamentals-reconciled:{args.symbol.upper()}:{args.as_of}",
        "provider": "MULTI_SOURCE_RECONCILIATION", "symbol": args.symbol.upper(), "as_of": args.as_of,
        "primary_provider": "SEC_EDGAR", "facts": sec_facts,
        "quality": {**sec_quality, "primary_policy": "SEC/IR remains accounting primary; secondary sources cross-check only", "ratio_safe": bool(sec_quality.get("ratio_safe", False))},
        "providers": providers, "conflicts": conflicts,
        "warnings": ["No provider is allowed to repair an SEC period mismatch by silently substituting another period.", "Finnhub, IBKR and SimFin values remain raw cross-check evidence until a field-level same-period mapping is explicitly verified."],
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK fundamentals reconciliation {args.symbol.upper()}: primary=SEC_EDGAR ratio_safe={result['quality']['ratio_safe']} conflicts={len(conflicts)} -> {args.output}")


if __name__ == "__main__":
    main()
