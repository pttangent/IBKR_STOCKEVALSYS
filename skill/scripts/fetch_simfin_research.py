#!/usr/bin/env python3
"""Fetch SimFin fundamental data as a secondary, auditable research packet.

SEC/IR remains the accounting primary. SimFin is never allowed to silently
repair a filing-period mismatch or replace SEC facts.
"""
from __future__ import annotations

import argparse
import os
import re
from datetime import date
from typing import Any
from urllib.parse import urlencode

from research_http import request_json, source_packet, write_json

BASE = "https://backend.simfin.com/api/v3"
DOCS = "https://simfin.readme.io/reference/getting-started-1"
VALID_MODULES = {"general", "statements", "shares", "prices"}


def request(endpoint: str, params: dict[str, Any], api_key: str) -> dict[str, Any]:
    clean = {key: value for key, value in params.items() if value not in (None, "")}
    try:
        payload = request_json(
            f"{BASE}/{endpoint}?{urlencode(clean)}",
            headers={"Authorization": f"api-key {api_key}", "Accept": "application/json"},
            retries=1,
        )
        return {"endpoint": endpoint, "status": "ok", "http_status": 200, "request_params": clean, "payload": payload}
    except Exception as exc:
        message = str(exc)[:500]
        match = re.search(r"HTTP (\d{3})", message)
        code = int(match.group(1)) if match else None
        return {"endpoint": endpoint, "status": "rate_limited" if code == 429 else "not_entitled" if code in (401, 403) else "error", "http_status": code, "request_params": clean, "error": message}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--as-of", required=True)
    ap.add_argument("--modules", default="general,statements,shares")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    key = os.environ.get("SIMFIN_API_KEY", "").strip()
    if not key:
        raise SystemExit("Missing SIMFIN_API_KEY")
    symbol = args.symbol.strip().upper()
    as_of = date.fromisoformat(args.as_of)
    modules = list(dict.fromkeys(item.strip().lower() for item in args.modules.split(",") if item.strip()))
    unknown = sorted(set(modules) - VALID_MODULES)
    if unknown:
        raise SystemExit(f"Unknown SimFin module(s): {', '.join(unknown)}")
    requests = {
        "general": ("companies/general/compact", {"ticker": symbol}),
        "statements": ("companies/statements/compact", {"ticker": symbol, "statements": "PL,BS,CF,DERIVED", "period": "Q1,Q2,Q3,Q4,FY,H1,H2,NINE_MONTH", "asreported": "true", "details": "true"}),
        "shares": ("companies/common-shares-outstanding", {"ticker": symbol, "end": as_of.isoformat()}),
        "prices": ("companies/prices/compact", {"ticker": symbol, "end": as_of.isoformat()}),
    }
    results: dict[str, Any] = {}
    for name in modules:  # sequential: respect the provider's pacing limits
        endpoint, params = requests[name]
        results[name] = request(endpoint, params, key)
    packet = source_packet(
        provider="SIMFIN", source_type="secondary_fundamentals",
        source_id=f"simfin:{symbol}:{as_of.isoformat()}", as_of=as_of.isoformat(), available_at=None,
        reliability="secondary_structured", source_url=DOCS,
        data={"symbol": symbol, "modules": modules, "endpoints": results, "primary_policy": "SEC/IR remains primary; no silent cross-period substitution"},
        warnings=[
            "SimFin is a secondary independent data provider; SEC/IR remains primary for reported accounting facts.",
            "The statements request asks for as-reported data, but period/accession alignment must still be checked before ratios.",
            "API responses are not automatically point-in-time safe merely because an as-of parameter is supplied.",
            "Requests are made sequentially to respect SimFin rate limits.",
        ],
        metadata={"authorization_header_excludes_key": True, "sequential_requests": True},
    )
    write_json(args.output, packet)
    print("OK SimFin %s: %s -> %s" % (symbol, ", ".join(f"{name}={item['status']}" for name, item in results.items()), args.output))


if __name__ == "__main__":
    main()
