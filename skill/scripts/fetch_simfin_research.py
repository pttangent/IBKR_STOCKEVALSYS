#!/usr/bin/env python3
"""Fetch SimFin as the standardized / peer-ready fundamental layer.

SEC/issuer IR remains the accounting truth source. SimFin provides a more
comparable schema and derived fields across companies; it never silently
replaces an SEC reported fact or repairs a filing-period mismatch.
"""
from __future__ import annotations

import argparse
import os
import re
from datetime import date
from typing import Any
from urllib.parse import urlencode

from research_http import request_json, source_packet, write_json

BASE = "https://prod.simfin.com/api/v3"
DOCS = "https://www.simfin.com/en/fundamental-data-download/"
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
    ap.add_argument("--statement-mode", choices=["standardized", "as_reported"], default="standardized")
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
        "statements": ("companies/statements/compact", {"ticker": symbol, "statements": "PL,BS,CF,DERIVED", "period": "Q1,Q2,Q3,Q4,FY,H1,H2,NINE_MONTH", "asreported": "true" if args.statement_mode == "as_reported" else "false", "details": "true"}),
        "shares": ("companies/common-shares-outstanding", {"ticker": symbol, "end": as_of.isoformat()}),
        "prices": ("companies/prices/compact", {"ticker": symbol, "end": as_of.isoformat()}),
    }
    results: dict[str, Any] = {}
    for name in modules:
        endpoint, params = requests[name]
        results[name] = request(endpoint, params, key)
    packet = source_packet(
        provider="SIMFIN", source_type="standardized_fundamentals", source_id=f"simfin:{symbol}:{as_of.isoformat()}",
        as_of=as_of.isoformat(), available_at=None, reliability="secondary_standardized", source_url=DOCS,
        data={"symbol": symbol, "role": "standardization", "statement_mode": args.statement_mode, "modules": modules, "endpoints": results, "primary_policy": "SEC/issuer IR remains accounting truth; SimFin supplies normalized peer-ready fields only"},
        warnings=["SimFin normalized values never overwrite SEC/issuer reported facts.", "Period/accession alignment must be checked before mixing SimFin with SEC or deriving ratios.", "A current SimFin response is not automatically historical point-in-time evidence.", "Requests are made sequentially to respect provider rate limits."],
        metadata={"authorization_header_excludes_key": True, "sequential_requests": True, "statement_mode": args.statement_mode, "api_base": BASE},
    )
    write_json(args.output, packet)
    print("OK SimFin %s role=standardization mode=%s: %s -> %s" % (symbol, args.statement_mode, ", ".join(f"{name}={item['status']}" for name, item in results.items()), args.output))


if __name__ == "__main__":
    main()
