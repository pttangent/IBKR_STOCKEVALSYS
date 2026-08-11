#!/usr/bin/env python3
"""Read-only market-data fetcher for Massive REST and IBKR/TWS.

Secrets are read only from environment variables. The script never calls an
order API and writes a provider-labelled JSON packet for the engine.
"""
from __future__ import annotations
import argparse
import asyncio
import datetime as dt
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def request_json(url: str, timeout: int = 30) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def normalize_ibkr_bar_size(value: str) -> str:
    aliases = {"1 sec": "1 secs", "5 sec": "5 secs", "10 sec": "10 secs", "15 sec": "15 secs", "30 sec": "30 secs"}
    normalized = aliases.get(value.strip().lower(), value.strip())
    legal = {"1 secs", "5 secs", "10 secs", "15 secs", "30 secs", "1 min", "2 mins", "3 mins", "4 mins", "5 mins", "10 mins", "15 mins", "20 mins", "30 mins", "1 hour", "2 hours", "3 hours", "4 hours", "8 hours", "1 day", "1W", "1M"}
    if normalized not in legal:
        raise ValueError(f"Invalid IBKR bar size {value!r}; use official strings such as '1 secs', '5 secs', or '1 min'")
    return normalized


def massive_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    key = os.environ.get("MASSIVE_API_KEY")
    if not key:
        raise RuntimeError("MASSIVE_API_KEY is not set; refusing to accept a key on the command line")
    base = os.environ.get("MASSIVE_BASE_URL", "https://api.massive.com").rstrip("/")
    query = dict(params)
    query["apiKey"] = key
    return request_json(f"{base}{path}?{urllib.parse.urlencode(query)}")


def fetch_massive(symbol: str, start: str, end: str, include_contracts: bool, spacing_seconds: float) -> dict[str, Any]:
    agg = massive_get(f"/v2/aggs/ticker/{symbol.upper()}/range/1/day/{start}/{end}", {"adjusted": "true", "sort": "asc", "limit": 50000})
    packet: dict[str, Any] = {"provider": "massive-rest", "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(), "symbol": symbol.upper(), "bars": agg.get("results", []), "bar_response": {k: agg.get(k) for k in ("status", "request_id", "resultsCount", "next_url") if k in agg}}
    if include_contracts:
        time.sleep(max(0.0, spacing_seconds))
        contracts = massive_get("/v3/reference/options/contracts", {"underlying_ticker": symbol.upper(), "limit": 1000, "expired": "false"})
        packet["contracts"] = contracts.get("results", [])
        packet["contracts_response"] = {k: contracts.get(k) for k in ("status", "request_id", "resultsCount", "next_url") if k in contracts}
    return packet


async def fetch_ibkr(symbol: str, duration: str, client_id: int, bar_size: str, what_to_show: str, end_date_time: str, use_rth: bool) -> dict[str, Any]:
    try:
        from ib_async import IB, Stock
    except ImportError as exc:
        raise RuntimeError("ib_async is not installed in the active Python environment") from exc
    host = os.environ.get("IBKR_HOST", "127.0.0.1")
    port = int(os.environ.get("IBKR_PORT", "7497"))
    ib = IB()
    bar_size = normalize_ibkr_bar_size(bar_size)
    await ib.connectAsync(host, port, clientId=client_id, readonly=True, timeout=10)
    try:
        contract = (await ib.qualifyContractsAsync(Stock(symbol.upper(), "SMART", "USD")))[0]
        bars = await asyncio.wait_for(ib.reqHistoricalDataAsync(contract, endDateTime=end_date_time, durationStr=duration, barSizeSetting=bar_size, whatToShow=what_to_show, useRTH=use_rth, formatDate=1, keepUpToDate=False), timeout=60)
        return {"provider": "ibkr-tws", "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(), "symbol": symbol.upper(), "request": {"duration": duration, "bar_size": bar_size, "what_to_show": what_to_show, "end_date_time": end_date_time, "use_rth": use_rth}, "connection": {"host": host, "port": port}, "bars": [{"date": str(x.date), "open": x.open, "high": x.high, "low": x.low, "close": x.close, "volume": x.volume, "count": getattr(x, "barCount", getattr(x, "count", None)), "wap": getattr(x, "average", getattr(x, "wap", None))} for x in bars]}
    finally:
        ib.disconnect()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--source", choices=("massive", "ibkr"), required=True)
    ap.add_argument("--start", default=(dt.date.today() - dt.timedelta(days=400)).isoformat())
    ap.add_argument("--end", default=dt.date.today().isoformat())
    ap.add_argument("--duration", default="1 Y")
    ap.add_argument("--bar-size", default="1 day", help="IBKR bar size, e.g. 1 secs, 5 secs, 10 secs, 1 day")
    ap.add_argument("--what-to-show", default="TRADES", choices=("TRADES", "MIDPOINT", "BID_ASK", "ADJUSTED_LAST"))
    ap.add_argument("--end-date-time", default="", help="IBKR exchange-local end time, e.g. 20260806 16:00:00")
    ap.add_argument("--all-hours", action="store_true", help="include outside regular trading hours")
    ap.add_argument("--contracts", action="store_true")
    ap.add_argument("--spacing-seconds", type=float, default=12.0)
    ap.add_argument("--client-id", type=int, default=4710)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    if args.source == "massive":
        packet = fetch_massive(args.symbol, args.start, args.end, args.contracts, args.spacing_seconds)
    else:
        packet = asyncio.run(fetch_ibkr(args.symbol, args.duration, args.client_id, args.bar_size, args.what_to_show, args.end_date_time, not args.all_hours))
    Path(args.out).write_text(json.dumps(packet, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"written": args.out, "provider": packet["provider"], "bars": len(packet.get("bars", [])), "contracts": len(packet.get("contracts", []))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
