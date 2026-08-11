#!/usr/bin/env python3
"""Fetch a bounded Massive option slice for cross-source research.

The free-tier-safe default uses four calls at most: contract reference,
underlying daily bars, and one call/put historical bar request. It deliberately
does not pretend to provide a live snapshot, Greeks, quotes, or open interest.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env.local")


def number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def request_json(url: str, timeout: int = 30) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body[:500]}") from exc


def massive_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    key = os.environ.get("MASSIVE_API_KEY")
    if not key:
        raise RuntimeError("MASSIVE_API_KEY is not set; refusing to accept a key on the command line")
    base = os.environ.get("MASSIVE_BASE_URL", "https://api.massive.com").rstrip("/")
    query = dict(params)
    query["apiKey"] = key
    url = f"{base}{path}?{urllib.parse.urlencode(query)}"
    return request_json(url)


def latest_close(bars: list[dict[str, Any]]) -> float | None:
    ordered = sorted(bars, key=lambda row: str(row.get("t", row.get("date", ""))))
    return number(ordered[-1].get("c", ordered[-1].get("close"))) if ordered else None


def contract_type(row: dict[str, Any]) -> str:
    value = str(row.get("contract_type", row.get("type", ""))).lower()
    return "call" if value in {"call", "c"} else "put" if value in {"put", "p"} else value


def expiry_value(row: dict[str, Any]) -> str:
    return str(row.get("expiration_date", row.get("expiration", ""))).replace("-", "")


def select_pair(contracts: list[dict[str, Any]], expiry: str, spot: float, strike: float | None) -> list[dict[str, Any]]:
    target_expiry = expiry.replace("-", "")
    eligible = [row for row in contracts if expiry_value(row) == target_expiry]
    grouped: dict[float, dict[str, dict[str, Any]]] = {}
    for row in eligible:
        price = number(row.get("strike_price", row.get("strike")))
        kind = contract_type(row)
        ticker = row.get("ticker")
        if price is not None and kind in {"call", "put"} and ticker:
            grouped.setdefault(price, {})[kind] = row
    paired = [(price, sides) for price, sides in grouped.items() if "call" in sides and "put" in sides]
    if not paired:
        return []
    target = spot if strike is None else strike
    _, sides = min(paired, key=lambda item: abs(item[0] - target))
    return [sides["call"], sides["put"]]


def fetch(symbol: str, expiry: str, start: str, end: str, requested_strike: float | None, spacing: float) -> dict[str, Any]:
    symbol = symbol.upper()
    audit: list[dict[str, Any]] = []
    calls = 0

    def call(path: str, params: dict[str, Any], label: str) -> dict[str, Any]:
        nonlocal calls
        if calls:
            time.sleep(max(0.0, spacing))
        result = massive_get(path, params)
        calls += 1
        audit.append({"label": label, "path": path, "status": result.get("status"), "results_count": result.get("resultsCount")})
        return result

    contracts_response = call(
        "/v3/reference/options/contracts",
        {"underlying_ticker": symbol, "expiration_date": f"{expiry[:4]}-{expiry[4:6]}-{expiry[6:8]}", "limit": 1000, "expired": "false"},
        "contracts_reference",
    )
    contracts = contracts_response.get("results", []) or []

    stock_response = call(
        f"/v2/aggs/ticker/{symbol}/range/1/day/{start}/{end}",
        {"adjusted": "true", "sort": "asc", "limit": 50000},
        "underlying_daily_bars",
    )
    stock_bars = stock_response.get("results", []) or []
    stock_spot = latest_close(stock_bars)
    if stock_spot is None:
        raise RuntimeError(f"Massive returned no underlying daily close for {symbol}")

    selected = select_pair(contracts, expiry, stock_spot, requested_strike)
    if not selected:
        raise RuntimeError(f"Massive returned no call/put pair for {symbol} expiry {expiry}")

    option_rows: list[dict[str, Any]] = []
    selected_contracts: list[dict[str, Any]] = []
    for contract in selected:
        ticker = str(contract["ticker"])
        encoded_ticker = urllib.parse.quote(ticker, safe=":")
        response = call(
            f"/v2/aggs/ticker/{encoded_ticker}/range/1/day/{start}/{end}",
            {"adjusted": "true", "sort": "asc", "limit": 50000},
            f"option_daily_bars:{ticker}",
        )
        bars = response.get("results", []) or []
        last = latest_close(bars)
        expiration = str(contract.get("expiration_date", expiry))
        strike = number(contract.get("strike_price", contract.get("strike")))
        kind = contract_type(contract)
        option_rows.append({
            "type": kind,
            "expiry": expiration,
            "strike": strike,
            "contract_symbol": ticker,
            "last": last,
            "close": last,
            "bid": None,
            "ask": None,
            "volume": None,
            "open_interest": None,
            "iv": None,
            "delta": None,
            "gamma": None,
            "theta": None,
            "vega": None,
            "last_trade_date": str(bars[-1].get("t")) if bars else None,
            "history": bars,
            "quote_source": "massive-rest-historical-bars",
            "quote_quality": "historical_daily_close_no_snapshot",
        })
        selected_contracts.append({
            "ticker": ticker,
            "contract_type": kind,
            "expiration_date": expiration,
            "strike_price": strike,
        })

    return {
        "provider": "massive-rest",
        "source_role": "historical_option_contract_and_underlying_bars",
        "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "symbol": symbol,
        "status": "ok" if all(row["last"] is not None for row in option_rows) else "partial",
        "spot": stock_spot,
        "request": {"expiry": expiry, "start": start, "end": end, "requested_strike": requested_strike, "spacing_seconds": spacing},
        "contract_discovery": {"returned": len(contracts), "selected": selected_contracts},
        "underlying_bars": stock_bars,
        "options": option_rows,
        "api_audit": {"calls": calls, "requests": audit},
        "warnings": [
            "This packet uses historical daily closes, not a live option snapshot.",
            "Bid/ask, open interest, Greeks, and provider IV are intentionally null unless a separately entitled endpoint supplies them.",
            "Do not treat a missing volume field as zero.",
        ],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--expiry", required=True, help="YYYYMMDD or YYYY-MM-DD")
    ap.add_argument("--start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD")
    ap.add_argument("--strike", type=float, help="Optional exact target strike; otherwise nearest paired strike to spot")
    ap.add_argument("--spacing-seconds", type=float, default=12.0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    packet = fetch(args.symbol, args.expiry, args.start, args.end, args.strike, args.spacing_seconds)
    Path(args.out).write_text(json.dumps(packet, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"written": args.out, "provider": packet["provider"], "status": packet["status"], "api_calls": packet["api_audit"]["calls"], "options": len(packet["options"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
