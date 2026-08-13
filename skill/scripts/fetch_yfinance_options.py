#!/usr/bin/env python3
"""Fetch Yahoo/yfinance option-chain evidence with bounded or full-expiry strike coverage."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path


def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def fetch(
    symbol: str,
    spot: float,
    expiries_count: int,
    strikes_each_side: int,
    requested_expiries: list[str] | None = None,
    full_chain: bool = False,
) -> dict:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError("yfinance is not installed in the active Python environment") from exc
    ticker = yf.Ticker(symbol.upper())
    expiries = list(ticker.options)
    selected_expiries = requested_expiries or expiries[:expiries_count]
    rows = []
    audit = []
    for expiry in selected_expiries:
        try:
            chain = ticker.option_chain(expiry)
            calls = chain.calls.copy()
            puts = chain.puts.copy()
            strikes = sorted(set(number(x) for x in list(calls["strike"]) + list(puts["strike"]) if number(x) is not None))
            if not strikes:
                audit.append({"expiry": expiry, "status": "empty"})
                continue
            if full_chain:
                selected = set(strikes)
            else:
                center = min(range(len(strikes)), key=lambda i: abs(strikes[i] - spot))
                selected = set(strikes[max(0, center - strikes_each_side):min(len(strikes), center + strikes_each_side + 1)])
            for kind, frame in (("call", calls), ("put", puts)):
                for _, row in frame.iterrows():
                    strike = number(row.get("strike"))
                    if strike not in selected:
                        continue
                    rows.append({"type": kind, "expiry": expiry, "strike": strike,
                                 "contract_symbol": str(row.get("contractSymbol")),
                                 "bid": number(row.get("bid")), "ask": number(row.get("ask")),
                                 "last": number(row.get("lastPrice")), "volume": number(row.get("volume")),
                                 "open_interest": number(row.get("openInterest")),
                                 "iv": number(row.get("impliedVolatility")), "delta": None, "gamma": None,
                                 "theta": None, "vega": None, "last_trade_date": str(row.get("lastTradeDate")),
                                 "quote_source": "yfinance/yahoo", "quote_quality": "provider_fields_without_timestamp"})
            audit.append({"expiry": expiry, "status": "ok", "calls": len(calls), "puts": len(puts),
                          "strike_mode": "full_expiry" if full_chain else "bounded_atm",
                          "available_strikes": len(strikes), "selected_strikes_count": len(selected),
                          "selected_strikes": sorted(selected) if not full_chain else None})
        except Exception as exc:
            audit.append({"expiry": expiry, "status": "error", "error": f"{type(exc).__name__}: {exc}"})
    status = "ok" if rows and all(x["status"] == "ok" for x in audit) else "partial" if rows else "failed"
    return {"provider": "yfinance", "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(), "symbol": symbol.upper(),
            "status": status, "spot": spot,
            "request": {"expiries_count": expiries_count, "strikes_each_side": strikes_each_side, "full_chain": full_chain},
            "chain_discovery": {"all_expiries": expiries, "selected_expiries": selected_expiries},
            "audit": audit, "quote_coverage": {"options": len(rows), "expiries_returned": len(audit)}, "options": rows,
            "warnings": ["Yahoo/yfinance is an unofficial research wrapper and quote timestamps are not normalized here",
                         "Greeks are unavailable in this adapter; IV is provider-reported and may be stale",
                         "open_interest is preserved as null when missing; never replace it with zero",
                         "--full-chain is intended for nightly gamma/OI concentration scans; bounded ATM mode remains the default for quick IV diagnostics",
                         "put/call volume and OI are activity distributions, not opening/closing or aggressor direction"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--spot", type=float, required=True)
    ap.add_argument("--expiries-count", type=int, default=3)
    ap.add_argument("--expiries", nargs="*", help="Optional exact Yahoo expiry dates (YYYY-MM-DD)")
    ap.add_argument("--strikes-each-side", type=int, default=6)
    ap.add_argument("--full-chain", action="store_true", help="Keep every strike for each selected expiry; use for nightly gamma/OI concentration analysis")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    packet = fetch(args.symbol, args.spot, args.expiries_count, args.strikes_each_side, args.expiries, args.full_chain)
    Path(args.out).write_text(json.dumps(packet, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"written": args.out, "symbol": packet["symbol"], "status": packet["status"], "options": len(packet["options"]),
                      "full_chain": args.full_chain}, ensure_ascii=False))


if __name__ == "__main__":
    main()
