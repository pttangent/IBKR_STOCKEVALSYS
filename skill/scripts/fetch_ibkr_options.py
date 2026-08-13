#!/usr/bin/env python3
"""Read-only IBKR option-chain discovery and bounded live quote snapshot.

This is the separate live/OPRA path. It is intentionally blocked by default
for accounts that only have historical option bars. Use
fetch_ibkr_mcp_historical_options.py for the project-local historical path.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import math
import os
from pathlib import Path
from typing import Any


def finite(value: Any):
    try:
        value = float(value)
        return value if math.isfinite(value) and value >= 0 else None
    except (TypeError, ValueError):
        return None


def raw(value: Any):
    if value is None:
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return str(value)


def greek(greeks: Any, name: str):
    return raw(getattr(greeks, name, None)) if greeks else None


async def fetch(symbol: str, spot: float | None, expiries_count: int, strikes_each_side: int,
                client_id: int, quote_timeout: float) -> dict[str, Any]:
    try:
        from ib_async import IB, Option, Stock
    except ImportError as exc:
        raise RuntimeError("ib_async is not installed; use the local ibkr-pro Python environment") from exc
    host = os.environ.get("IBKR_HOST", "127.0.0.1")
    port = int(os.environ.get("IBKR_PORT", "7497"))
    ib = IB()
    errors: list[dict[str, Any]] = []
    ib.errorEvent += lambda reqId, errorCode, errorString, contract: errors.append({"reqId": reqId, "code": errorCode, "message": errorString,
                                                                                       "contract": str(contract) if contract else None})
    await ib.connectAsync(host, port, clientId=client_id, readonly=True, timeout=10)
    try:
        underlying = (await ib.qualifyContractsAsync(Stock(symbol.upper(), "SMART", "USD")))[0]
        if spot is None:
            tickers = await asyncio.wait_for(ib.reqTickersAsync(underlying), timeout=quote_timeout)
            ticker = tickers[0] if tickers else None
            spot = finite(ticker.marketPrice() if ticker else None) or finite(ticker.close if ticker else None)
        chains = await asyncio.wait_for(ib.reqSecDefOptParamsAsync(underlying.symbol, "", "STK", underlying.conId), timeout=quote_timeout)
        if not chains:
            return {"provider": "ibkr-tws", "symbol": symbol.upper(), "status": "unavailable", "reason": "no option chain returned", "errors": errors}
        chain = next((x for x in chains if x.exchange == "SMART"), chains[0])
        expiry_values = sorted(str(x) for x in chain.expirations)
        selected_expiries = expiry_values[:expiries_count]
        strikes = sorted(float(x) for x in chain.strikes if finite(x) is not None)
        if spot is None or not strikes:
            return {"provider": "ibkr-tws", "symbol": symbol.upper(), "status": "unavailable", "reason": "no spot or strikes", "errors": errors}
        nearest = min(range(len(strikes)), key=lambda i: abs(strikes[i] - spot))
        lo, hi = max(0, nearest - strikes_each_side), min(len(strikes), nearest + strikes_each_side + 1)
        selected_strikes = strikes[lo:hi]
        contracts = []
        for expiry in selected_expiries:
            for strike in selected_strikes:
                for right in ("C", "P"):
                    contracts.append(Option(symbol.upper(), expiry, strike, right, "SMART", multiplier=str(chain.multiplier),
                                            currency="USD", tradingClass=str(chain.tradingClass)))
        qualified = await ib.qualifyContractsAsync(*contracts, returnAll=True)
        qualified = [x for x in qualified if x is not None]
        tickers = await asyncio.wait_for(ib.reqTickersAsync(*qualified), timeout=quote_timeout)
        rows = []
        for ticker in tickers:
            contract = ticker.contract
            mg = ticker.modelGreeks
            rows.append({
                "type": "call" if contract.right == "C" else "put", "expiry": contract.lastTradeDateOrContractMonth,
                "strike": contract.strike, "local_symbol": contract.localSymbol, "con_id": contract.conId,
                "bid": raw(ticker.bid), "ask": raw(ticker.ask), "last": raw(ticker.last), "close": raw(ticker.close),
                "volume": raw(ticker.volume), "open_interest": raw(ticker.openInterest),
                "iv": greek(mg, "impliedVol"), "delta": greek(mg, "delta"), "gamma": greek(mg, "gamma"),
                "theta": greek(mg, "theta"), "vega": greek(mg, "vega"), "model_und_price": greek(mg, "undPrice"),
                "model_opt_price": greek(mg, "optPrice"), "market_data_type": ticker.marketDataType,
                "quote_timestamp": ticker.time.isoformat() if ticker.time else None,
            })
            try:
                ib.cancelMktData(contract)
            except Exception:
                pass
        has_market_fields = any(any(row.get(field) is not None for field in ("bid", "ask", "last", "volume", "open_interest", "iv")) for row in rows)
        packet_status = "ok" if has_market_fields else "discovery_only"
        return {"provider": "ibkr-tws", "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(), "symbol": symbol.upper(),
                "status": packet_status, "spot": spot, "chain_discovery": {"chains_returned": len(chains), "selected_exchange": chain.exchange,
                "trading_class": chain.tradingClass, "all_expiries": expiry_values, "all_strikes_count": len(strikes),
                "selected_expiries": selected_expiries, "selected_strikes": selected_strikes},
                "request": {"expiries_count": expiries_count, "strikes_each_side": strikes_each_side, "quote_timeout": quote_timeout,
                "readonly": True}, "quote_coverage": {"contracts_requested": len(contracts), "contracts_qualified": len(qualified),
                "tickers_returned": len(tickers)}, "errors": errors, "options": rows}
    finally:
        ib.disconnect()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--spot", type=float)
    ap.add_argument("--expiries-count", type=int, default=3)
    ap.add_argument("--strikes-each-side", type=int, default=6)
    ap.add_argument("--client-id", type=int, default=5010)
    ap.add_argument("--quote-timeout", type=float, default=45)
    ap.add_argument("--allow-live-options", action="store_true",
                    help="explicitly confirm live/OPRA option permission")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    if not args.allow_live_options:
        raise SystemExit(
            "Blocked: this helper calls live reqMktData/reqTickers and requires "
            "explicit live/OPRA permission. Use fetch_ibkr_mcp_historical_options.py "
            "for historical option bars."
        )
    packet = asyncio.run(fetch(args.symbol, args.spot, args.expiries_count, args.strikes_each_side, args.client_id, args.quote_timeout))
    Path(args.out).write_text(json.dumps(packet, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"written": args.out, "symbol": packet["symbol"], "status": packet.get("status"),
                      "options": len(packet.get("options", [])), "errors": len(packet.get("errors", []))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
