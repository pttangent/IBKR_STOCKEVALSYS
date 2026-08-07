#!/usr/bin/env python3
"""Read-only diagnostic for IBKR historical bar responses and error events."""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone


async def diagnose(symbol: str, bar_size: str, duration: str, end: str, use_rth: bool, client_id: int, timeout: float) -> dict:
    from ib_async import IB, Stock

    host = "127.0.0.1"
    port = 7497
    ib = IB()
    errors = []

    def on_error(req_id, code, message, contract):
        errors.append({"req_id": req_id, "code": code, "message": message, "contract": getattr(contract, "symbol", None)})

    ib.errorEvent += on_error
    result = {"symbol": symbol.upper(), "bar_size": bar_size, "duration": duration, "end": end, "use_rth": use_rth,
              "started_at": datetime.now(timezone.utc).isoformat(), "errors": errors}
    try:
        await ib.connectAsync(host, port, clientId=client_id, readonly=True, timeout=10)
        contract = (await ib.qualifyContractsAsync(Stock(symbol.upper(), "SMART", "USD")))[0]
        try:
            bars = await asyncio.wait_for(ib.reqHistoricalDataAsync(contract, endDateTime=end, durationStr=duration,
                barSizeSetting=bar_size, whatToShow="TRADES", useRTH=use_rth, formatDate=1, keepUpToDate=False), timeout=timeout)
            result["status"] = "ok"
            result["bars"] = len(bars)
            result["first_bar"] = str(bars[0]) if bars else None
            result["last_bar"] = str(bars[-1]) if bars else None
        except asyncio.TimeoutError:
            result["status"] = "timeout"
            result["bars"] = 0
        except Exception as exc:
            result["status"] = "exception"
            result["exception"] = repr(exc)
    finally:
        result["errors"] = list(errors)
        if ib.isConnected():
            ib.disconnect()
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="XE")
    ap.add_argument("--bar-size", default="1 secs")
    ap.add_argument("--duration", default="60 S")
    ap.add_argument("--end", default="20260806 16:00:00 US/Eastern")
    ap.add_argument("--all-hours", action="store_true")
    ap.add_argument("--client-id", type=int, default=4820)
    ap.add_argument("--timeout", type=float, default=20)
    args = ap.parse_args()
    print(json.dumps(asyncio.run(diagnose(args.symbol, args.bar_size, args.duration, args.end, not args.all_hours, args.client_id, args.timeout)), ensure_ascii=False))


if __name__ == "__main__":
    main()
