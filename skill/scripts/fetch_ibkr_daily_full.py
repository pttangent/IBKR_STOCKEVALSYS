#!/usr/bin/env python3
"""Fetch the available IBKR daily history in read-only, deduplicated chunks."""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
from pathlib import Path
from typing import Any


def _date_value(value: Any) -> str:
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    return str(value)


def _bar_to_dict(bar: Any) -> dict[str, Any]:
    return {
        "date": _date_value(bar.date),
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
        "count": getattr(bar, "barCount", getattr(bar, "count", None)),
        "wap": getattr(bar, "average", getattr(bar, "wap", None)),
    }


def _cursor_before(date_value: str) -> str:
    # Daily bars are keyed by exchange date.  A timezone-qualified cursor
    # avoids IBKR's ambiguous local-time warning on subsequent requests.
    day = dt.date.fromisoformat(date_value[:10]) - dt.timedelta(days=1)
    return f"{day:%Y%m%d} 16:00:00 US/Eastern"


async def fetch(symbol: str, client_id: int, what_to_show: str, use_rth: bool,
                max_chunks: int, pause_seconds: float, end_date_time: str) -> dict[str, Any]:
    try:
        from ib_async import IB, Stock
    except ImportError as exc:
        raise RuntimeError("ib_async is not installed; use the local ibkr-pro Python environment") from exc
    host = os.environ.get("IBKR_HOST", "127.0.0.1")
    port = int(os.environ.get("IBKR_PORT", "7497"))
    ib = IB()
    await ib.connectAsync(host, port, clientId=client_id, readonly=True, timeout=10)
    requests: list[dict[str, Any]] = []
    try:
        contract = (await ib.qualifyContractsAsync(Stock(symbol.upper(), "SMART", "USD")))[0]
        head = await ib.reqHeadTimeStampAsync(contract, what_to_show, use_rth, 1)
        head_date = _date_value(head)[:10] if head else None
        cursor = end_date_time
        all_bars: dict[str, dict[str, Any]] = {}
        for index in range(max_chunks):
            started = dt.datetime.now(dt.timezone.utc)
            bars = await asyncio.wait_for(
                ib.reqHistoricalDataAsync(
                    contract,
                    endDateTime=cursor,
                    durationStr="1 Y",
                    barSizeSetting="1 day",
                    whatToShow=what_to_show,
                    useRTH=use_rth,
                    formatDate=1,
                    keepUpToDate=False,
                ),
                timeout=90,
            )
            packet_bars = [_bar_to_dict(bar) for bar in bars]
            requests.append({
                "index": index + 1,
                "end_date_time": cursor,
                "duration": "1 Y",
                "bar_size": "1 day",
                "bars": len(packet_bars),
                "elapsed_seconds": round((dt.datetime.now(dt.timezone.utc) - started).total_seconds(), 3),
            })
            if not packet_bars:
                break
            before = min(str(row["date"])[:10] for row in packet_bars)
            for row in packet_bars:
                all_bars[str(row["date"])[:10]] = row
            if head_date and before <= head_date:
                break
            next_cursor = _cursor_before(before)
            if next_cursor == cursor:
                break
            cursor = next_cursor
            if pause_seconds:
                await asyncio.sleep(pause_seconds)
        bars = [all_bars[key] for key in sorted(all_bars)]
        return {
            "provider": "ibkr-tws",
            "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "symbol": symbol.upper(),
            "request": {"duration_per_page": "1 Y", "bar_size": "1 day", "what_to_show": what_to_show,
                         "end_date_time": end_date_time, "use_rth": use_rth},
            "connection": {"host": host, "port": port, "readonly": True},
            "head_timestamp": _date_value(head) if head else None,
            "pagination": {"chunks_requested": len(requests), "requests": requests, "deduplicated": True},
            "bars": bars,
        }
    finally:
        ib.disconnect()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--client-id", type=int, default=4720)
    ap.add_argument("--what-to-show", default="TRADES", choices=("TRADES", "MIDPOINT", "BID_ASK", "ADJUSTED_LAST"))
    ap.add_argument("--all-hours", action="store_true")
    ap.add_argument("--max-chunks", type=int, default=60)
    ap.add_argument("--pause-seconds", type=float, default=1.0)
    ap.add_argument("--end-date-time", default="", help="e.g. 20260806 16:00:00 US/Eastern")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    packet = asyncio.run(fetch(args.symbol, args.client_id, args.what_to_show, not args.all_hours,
                                args.max_chunks, args.pause_seconds, args.end_date_time))
    Path(args.out).write_text(json.dumps(packet, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"written": args.out, "symbol": packet["symbol"], "bars": len(packet["bars"]),
                      "head_timestamp": packet["head_timestamp"], "chunks": packet["pagination"]["chunks_requested"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
