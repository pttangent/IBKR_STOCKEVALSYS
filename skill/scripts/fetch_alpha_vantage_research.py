#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent))
from research_http import request_bytes, request_json, source_packet, write_json

AV_URL = "https://www.alphavantage.co/query"


def _url(api_key: str, **params: Any) -> str:
    return f"{AV_URL}?{urlencode({**params, 'apikey': api_key})}"


def _check_api_payload(payload: Any, function_name: str) -> Any:
    if isinstance(payload, dict):
        for key in ("Error Message", "Information", "Note"):
            if payload.get(key):
                raise RuntimeError(f"Alpha Vantage {function_name}: {payload[key]}")
    return payload


def fetch_estimates(symbol: str, api_key: str) -> dict[str, Any]:
    url = _url(api_key, function="EARNINGS_ESTIMATES", symbol=symbol)
    return _check_api_payload(request_json(url), "EARNINGS_ESTIMATES")


def fetch_transcript(symbol: str, quarter: str, api_key: str) -> dict[str, Any]:
    url = _url(api_key, function="EARNINGS_CALL_TRANSCRIPT", symbol=symbol, quarter=quarter)
    return _check_api_payload(request_json(url), "EARNINGS_CALL_TRANSCRIPT")


def fetch_calendar(symbol: str, horizon: str, api_key: str) -> list[dict[str, Any]]:
    url = _url(api_key, function="EARNINGS_CALENDAR", symbol=symbol, horizon=horizon)
    raw = request_bytes(url, headers={"Accept": "text/csv"})
    text = raw.decode("utf-8", errors="replace")
    if text.lstrip().startswith("{"):
        import json
        _check_api_payload(json.loads(text), "EARNINGS_CALENDAR")
    return list(csv.DictReader(io.StringIO(text)))


def compact_estimates(payload: dict[str, Any]) -> dict[str, Any]:
    """Preserve provider fields while surfacing the forecast collections used by research."""
    # Alpha Vantage may evolve field names. Keep the raw response but expose known collections
    # without inventing a canonical consensus value when the provider shape changes.
    collections = {}
    for key, value in payload.items():
        lowered = key.lower()
        if isinstance(value, list) and ("annual" in lowered or "quarter" in lowered or "estimate" in lowered):
            collections[key] = value
    return {"collections": collections, "raw": payload}


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch Alpha Vantage consensus/earnings research context only.")
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--as-of", help="Research cutoff metadata. AV endpoints are not assumed PIT-safe unless historical fields prove it.")
    ap.add_argument("--quarter", help="Optional fiscal quarter YYYYQn for EARNINGS_CALL_TRANSCRIPT")
    ap.add_argument("--include-calendar", action="store_true")
    ap.add_argument("--horizon", choices=["3month", "6month", "12month"], default="3month")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    api_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Missing ALPHA_VANTAGE_API_KEY")
    symbol = args.symbol.strip().upper()
    as_of = args.as_of or date.today().isoformat()

    estimates = fetch_estimates(symbol, api_key)
    transcript = fetch_transcript(symbol, args.quarter, api_key) if args.quarter else None
    calendar = fetch_calendar(symbol, args.horizon, api_key) if args.include_calendar else None

    packet = source_packet(
        provider="ALPHA_VANTAGE",
        source_type="consensus_estimates_transcript_calendar",
        source_id=f"av:{symbol}:{as_of}",
        as_of=as_of,
        # Current endpoint retrieval is not automatically historical PIT evidence.
        available_at=None,
        reliability="secondary_structured",
        source_url=AV_URL,
        data={
            "symbol": symbol,
            "earnings_estimates": compact_estimates(estimates),
            "earnings_call_transcript": transcript,
            "earnings_calendar": calendar,
        },
        warnings=[
            "Analyst consensus and revisions are market expectations, not company-reported facts.",
            "A current API response must not be used in a historical replay unless each included estimate/revision is timestamped on or before the research cutoff.",
            "Call-transcript content should be cross-checked against company IR/SEC exhibits for material numeric claims.",
        ],
        metadata={"transcript_quarter": args.quarter, "calendar_horizon": args.horizon if args.include_calendar else None},
    )
    write_json(args.output, packet)
    print(f"OK AlphaVantage {symbol} estimates=yes transcript={bool(transcript)} calendar={calendar is not None} -> {args.output}")


if __name__ == "__main__":
    main()
