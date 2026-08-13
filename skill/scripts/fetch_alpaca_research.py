#!/usr/bin/env python3
"""Fetch Alpaca market/event evidence for the non-IBKR Research Lane.

Read-only GET requests only. The adapter deliberately labels IEX stock data as
IEX-only and never treats Alpaca as an accounting-fundamentals provider.
"""
from __future__ import annotations

import argparse
import os
import re
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlencode

from research_http import request_json, source_packet, write_json

VALID_MODULES = {"asset", "snapshot", "bars", "news", "corporate_actions", "option_contracts", "option_snapshot"}
DEFAULT_MODULES = "asset,snapshot,bars,news,corporate_actions,option_contracts,option_snapshot"


def _headers() -> dict[str, str]:
    key = os.environ.get("ALPACA_API_KEY_ID", "").strip()
    secret = os.environ.get("ALPACA_API_SECRET_KEY", "").strip()
    if not key or not secret:
        raise SystemExit("Missing ALPACA_API_KEY_ID or ALPACA_API_SECRET_KEY")
    return {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret, "Accept": "application/json"}


def _bases() -> tuple[str, str]:
    trading = os.environ.get("ALPACA_TRADING_BASE_URL", "https://paper-api.alpaca.markets/v2").rstrip("/")
    data = os.environ.get("ALPACA_DATA_BASE_URL", "https://data.alpaca.markets").rstrip("/")
    return trading, data


def call(url: str, headers: dict[str, str], endpoint_name: str) -> dict[str, Any]:
    try:
        payload = request_json(url, headers=headers, retries=1)
        return {"endpoint": endpoint_name, "status": "ok", "http_status": 200, "payload": payload}
    except Exception as exc:
        message = str(exc)[:500]
        match = re.search(r"HTTP (\d{3})", message)
        code = int(match.group(1)) if match else None
        return {"endpoint": endpoint_name, "status": "not_entitled" if code in (401, 403) else "rate_limited" if code == 429 else "error", "http_status": code, "error": message}


def with_params(base: str, params: dict[str, Any]) -> str:
    clean = {k: v for k, v in params.items() if v not in (None, "")}
    return f"{base}?{urlencode(clean)}" if clean else base


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch Alpaca Research-Lane stock/option/news/corporate-action context without IBKR.")
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--as-of")
    ap.add_argument("--modules", default=DEFAULT_MODULES)
    ap.add_argument("--history-days", type=int, default=400)
    ap.add_argument("--timeframe", default="1Day", help="Alpaca bars timeframe, e.g. 1Day or 1Min")
    ap.add_argument("--option-limit", type=int, default=100)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    symbol = args.symbol.strip().upper()
    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    start = as_of - timedelta(days=max(1, args.history_days))
    modules = list(dict.fromkeys(item.strip().lower() for item in args.modules.split(",") if item.strip()))
    unknown = sorted(set(modules) - VALID_MODULES)
    if unknown:
        raise SystemExit(f"Unknown Alpaca module(s): {', '.join(unknown)}")

    headers = _headers()
    trading_base, data_base = _bases()
    requests: dict[str, tuple[str, str]] = {
        "asset": (f"{trading_base}/assets/{symbol}", "GET /v2/assets/{symbol}"),
        "snapshot": (with_params(f"{data_base}/v2/stocks/{symbol}/snapshot", {"feed": "iex"}), "GET /v2/stocks/{symbol}/snapshot?feed=iex"),
        "bars": (with_params(f"{data_base}/v2/stocks/{symbol}/bars", {"timeframe": args.timeframe, "start": start.isoformat(), "end": as_of.isoformat(), "adjustment": "all", "feed": "iex", "sort": "asc", "limit": 10000}), "GET /v2/stocks/{symbol}/bars?feed=iex"),
        "news": (with_params(f"{data_base}/v1beta1/news", {"symbols": symbol, "start": start.isoformat(), "end": as_of.isoformat(), "limit": 50, "sort": "desc"}), "GET /v1beta1/news"),
        "corporate_actions": (with_params(f"{data_base}/v1/corporate-actions", {"symbols": symbol, "start": start.isoformat(), "end": as_of.isoformat()}), "GET /v1/corporate-actions"),
        "option_contracts": (with_params(f"{trading_base}/options/contracts", {"underlying_symbols": symbol, "status": "active", "limit": args.option_limit}), "GET /v2/options/contracts"),
        "option_snapshot": (with_params(f"{data_base}/v1beta1/options/snapshots/{symbol}", {"feed": "indicative", "limit": args.option_limit}), "GET /v1beta1/options/snapshots/{symbol}?feed=indicative"),
    }

    results: dict[str, Any] = {}
    for name in modules:
        url, endpoint_name = requests[name]
        item = call(url, headers, endpoint_name)
        item["request_url_redacted"] = url
        results[name] = item

    snapshot_payload = (results.get("option_snapshot") or {}).get("payload") or {}
    snapshots = snapshot_payload.get("snapshots") if isinstance(snapshot_payload, dict) else None
    iv_rows = 0
    greek_rows = 0
    if isinstance(snapshots, dict):
        for row in snapshots.values():
            if isinstance(row, dict) and row.get("impliedVolatility") is not None:
                iv_rows += 1
            if isinstance(row, dict) and row.get("greeks"):
                greek_rows += 1

    packet = source_packet(
        provider="ALPACA", source_type="research_lane_market_events", source_id=f"alpaca:{symbol}:{as_of.isoformat()}",
        as_of=as_of.isoformat(), available_at=None, reliability="primary_timestamped_market_context_iex", source_url="https://docs.alpaca.markets/us/docs/about-market-data-api",
        data={
            "symbol": symbol,
            "role": "market_reaction",
            "data_lane": "research_non_ibkr",
            "stock_feed": "iex",
            "option_feed": "indicative",
            "modules": modules,
            "endpoints": results,
            "option_snapshot_quality": {"rows": len(snapshots) if isinstance(snapshots, dict) else 0, "rows_with_provider_iv": iv_rows, "rows_with_greeks": greek_rows},
            "accounting_fundamentals_allowed": False,
        },
        warnings=[
            "IEX stock data is not consolidated SIP; do not label IEX volume/quotes as total-market data.",
            "Alpaca is a market/event layer, not an accounting-fundamentals source.",
            "Indicative option data is not OPRA executable evidence. Missing IV/Greeks remain missing; a model-derived IV must be separately labelled.",
            "This Research-Lane adapter intentionally avoids opening an IBKR/TWS session.",
        ],
        metadata={"credentials_excluded_from_packet": True, "sequential_requests": True, "history_days": args.history_days, "timeframe": args.timeframe},
    )
    write_json(args.output, packet)
    print("OK Alpaca %s lane=research_non_ibkr: %s -> %s" % (symbol, ", ".join(f"{k}={v['status']}" for k, v in results.items()), args.output))


if __name__ == "__main__":
    main()
