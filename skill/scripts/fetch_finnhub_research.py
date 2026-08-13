#!/usr/bin/env python3
"""Fetch Finnhub event, metadata, peer, and quick cross-check context."""
from __future__ import annotations

import argparse
import os
import re
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlencode

from research_http import request_json, source_packet, write_json

BASE = "https://finnhub.io/api/v1"
DOCS = "https://finnhub.io/docs/api"
DEFAULT_MODULES = "profile,peers,metric,earnings,calendar"
VALID_MODULES = {"profile", "peers", "financials_reported", "financials_standardized", "metric", "quote", "earnings", "news", "calendar", "recommendation", "insider_sentiment", "price_target", "upgrade_downgrade"}


def endpoint(endpoint_name: str, params: dict[str, Any], token: str) -> dict[str, Any]:
    clean = {k: v for k, v in params.items() if v not in (None, "")}
    try:
        payload = request_json(f"{BASE}/{endpoint_name}?{urlencode(clean)}", headers={"X-Finnhub-Token": token, "Accept": "application/json"}, retries=1)
        return {"endpoint": endpoint_name, "status": "ok", "http_status": 200, "request_params": clean, "payload": payload}
    except Exception as exc:
        message = str(exc)[:500]
        match = re.search(r"HTTP (\d{3})", message)
        code = int(match.group(1)) if match else None
        return {"endpoint": endpoint_name, "status": "not_entitled" if code == 403 else "rate_limited" if code == 429 else "error", "http_status": code, "request_params": clean, "error": message}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--as-of")
    ap.add_argument("--modules", default=DEFAULT_MODULES)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    token = os.environ.get("FINNHUB_API_KEY", "").strip()
    if not token:
        raise SystemExit("Missing FINNHUB_API_KEY")
    symbol = args.symbol.upper()
    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    modules = list(dict.fromkeys(x.strip().lower() for x in args.modules.split(",") if x.strip()))
    unknown = sorted(set(modules) - VALID_MODULES)
    if unknown:
        raise SystemExit(f"Unknown Finnhub module(s): {', '.join(unknown)}")
    one_year_start = (as_of - timedelta(days=365)).isoformat()
    three_year_start = (as_of - timedelta(days=365 * 3)).isoformat()
    requests: dict[str, tuple[str, dict[str, Any]]] = {
        "profile": ("stock/profile2", {"symbol": symbol}),
        "peers": ("stock/peers", {"symbol": symbol}),
        "financials_reported": ("stock/financials-reported", {"symbol": symbol, "freq": "quarterly"}),
        "financials_standardized": ("stock/financials", {"symbol": symbol, "statement": "ic", "freq": "quarterly"}),
        "metric": ("stock/metric", {"symbol": symbol, "metric": "all"}),
        "quote": ("quote", {"symbol": symbol}),
        "earnings": ("stock/earnings", {"symbol": symbol}),
        "news": ("company-news", {"symbol": symbol, "from": one_year_start, "to": as_of.isoformat()}),
        "calendar": ("calendar/earnings", {"symbol": symbol, "from": as_of.isoformat(), "to": (as_of + timedelta(days=31)).isoformat()}),
        "recommendation": ("stock/recommendation", {"symbol": symbol}),
        "insider_sentiment": ("stock/insider-sentiment", {"symbol": symbol, "from": three_year_start, "to": as_of.isoformat()}),
        "price_target": ("stock/price-target", {"symbol": symbol}),
        "upgrade_downgrade": ("stock/upgrade-downgrade", {"symbol": symbol}),
    }
    results = {}
    for name in modules:
        ep, params = requests[name]
        results[name] = endpoint(ep, params, token)
    packet = source_packet(
        provider="FINNHUB", source_type="events_metadata_and_quick_crosscheck", source_id=f"finnhub:{symbol}:{as_of.isoformat()}",
        as_of=as_of.isoformat(), available_at=None, reliability="secondary_context", source_url=DOCS,
        data={"symbol": symbol, "role": "events_metadata_crosscheck", "modules": modules, "endpoints": results, "primary_policy": "SEC/issuer IR controls reported facts; Finnhub never repairs or overwrites them"},
        warnings=["profile/peers/earnings/calendar/news/metric are event, metadata, peer-discovery, or quick cross-check inputs.", "financials-reported is optional cross-check evidence only; standardized financials may require a higher entitlement.", "Finnhub earnings/calendar values may use adjusted/non-GAAP conventions and must stay separate from SEC GAAP actuals.", "Finnhub responses are not automatically historical point-in-time safe."],
        metadata={"token_excluded_from_packet": True, "sequential_requests": True},
    )
    write_json(args.output, packet)
    print("OK Finnhub %s role=events_metadata_crosscheck: %s -> %s" % (symbol, ", ".join(f"{k}={v['status']}" for k, v in results.items()), args.output))


if __name__ == "__main__":
    main()
