#!/usr/bin/env python3
"""Fetch recent IBKR RTH intraday history with backward paging and deduplication."""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


def normalize_date(value: Any) -> str:
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    return str(value)


def session_date(value: Any) -> str:
    return normalize_date(value)[:10]


def cursor_before(value: Any) -> str:
    if isinstance(value, dt.datetime):
        stamp = value - dt.timedelta(seconds=1)
    else:
        raw = str(value).replace("Z", "+00:00")
        try:
            stamp = dt.datetime.fromisoformat(raw) - dt.timedelta(seconds=1)
        except ValueError:
            stamp = dt.datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S") - dt.timedelta(seconds=1)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=dt.timezone.utc)
    stamp = stamp.astimezone(ZoneInfo("America/New_York"))
    return stamp.strftime("%Y%m%d %H:%M:%S US/Eastern")


def session_complete(rows: list[dict[str, Any]], bar_size: str) -> bool:
    """Require both RTH endpoints before counting a date as complete."""
    if not rows:
        return False
    try:
        times = [dt.datetime.fromisoformat(str(row["date"]).replace("Z", "+00:00")).astimezone(ZoneInfo("America/New_York")).time()
                 for row in rows]
    except ValueError:
        return False
    first, last = min(times), max(times)
    if bar_size == "1 min":
        return first <= dt.time(9, 30) and last >= dt.time(15, 59)
    return first <= dt.time(9, 30) and last >= dt.time(15, 59, 50)


def bar_to_dict(bar: Any) -> dict[str, Any]:
    return {"date": normalize_date(bar.date), "open": bar.open, "high": bar.high, "low": bar.low,
            "close": bar.close, "volume": bar.volume,
            "count": getattr(bar, "barCount", getattr(bar, "count", None)),
            "wap": getattr(bar, "average", getattr(bar, "wap", None))}


async def fetch(symbol: str, sessions: int, client_id: int, bar_size: str, what_to_show: str,
                use_rth: bool, end_date_time: str, max_pages: int, pause_seconds: float) -> dict[str, Any]:
    if bar_size not in {"1 secs", "5 secs", "10 secs", "15 secs", "30 secs", "1 min"}:
        raise ValueError("This paginator supports IBKR short bars: 1 secs, 5 secs, 10 secs, 15 secs, 30 secs, 1 min")
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
        all_bars: dict[str, dict[str, Any]] = {}
        cursor = end_date_time
        for index in range(max_pages):
            started = dt.datetime.now(dt.timezone.utc)
            bars = await asyncio.wait_for(
                ib.reqHistoricalDataAsync(
                    contract,
                    endDateTime=cursor,
                    durationStr="14400 S",
                    barSizeSetting=bar_size,
                    whatToShow=what_to_show,
                    useRTH=use_rth,
                    formatDate=1,
                    keepUpToDate=False,
                ),
                timeout=90,
            )
            page = [bar_to_dict(bar) for bar in bars]
            requests.append({"index": index + 1, "end_date_time": cursor, "duration": "14400 S",
                             "bar_size": bar_size, "bars": len(page),
                             "elapsed_seconds": round((dt.datetime.now(dt.timezone.utc) - started).total_seconds(), 3)})
            if not page:
                break
            for row in page:
                # Date/time is unique at a given bar size; keep the first copy
                # when adjacent pages overlap at the boundary.
                all_bars[str(row["date"])] = row
            rows_by_date: dict[str, list[dict[str, Any]]] = {}
            for row in all_bars.values():
                rows_by_date.setdefault(session_date(row["date"]), []).append(row)
            complete_dates = [day for day, day_rows in rows_by_date.items() if session_complete(day_rows, bar_size)]
            if len(complete_dates) >= sessions:
                break
            earliest = min(page, key=lambda row: str(row["date"]))["date"]
            next_cursor = cursor_before(earliest)
            if next_cursor == cursor:
                break
            cursor = next_cursor
            if pause_seconds:
                await asyncio.sleep(pause_seconds)
        all_collected = [all_bars[key] for key in sorted(all_bars)]
        dates = sorted({session_date(row["date"]) for row in all_collected})
        complete_dates = sorted(day for day in dates if session_complete([row for row in all_collected if session_date(row["date"]) == day], bar_size))
        # Keep exactly the requested number of complete sessions in the
        # analytical packet; older partial pages remain visible in the audit.
        keep_dates = set(complete_dates[-sessions:])
        bars = [row for row in all_collected if session_date(row["date"]) in keep_dates]
        dates = sorted(keep_dates)
        return {"provider": "ibkr-tws", "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "symbol": symbol.upper(),
                "request": {"duration_per_page": "14400 S", "bar_size": bar_size, "what_to_show": what_to_show,
                             "end_date_time": end_date_time, "use_rth": use_rth, "target_sessions": sessions},
                "connection": {"host": host, "port": port, "readonly": True},
                "pagination": {"pages_requested": len(requests), "requests": requests, "deduplicated": True,
                                "session_dates": dates, "session_count": len(dates), "complete_session_dates": complete_dates,
                                "complete_session_count": len(complete_dates)},
                "bars": bars}
    finally:
        ib.disconnect()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--sessions", type=int, default=3)
    ap.add_argument("--client-id", type=int, default=4730)
    ap.add_argument("--bar-size", default="10 secs")
    ap.add_argument("--what-to-show", default="TRADES", choices=("TRADES", "MIDPOINT", "BID_ASK", "ADJUSTED_LAST"))
    ap.add_argument("--all-hours", action="store_true")
    ap.add_argument("--end-date-time", default="", help="e.g. 20260806 16:00:00 US/Eastern")
    ap.add_argument("--max-pages", type=int, default=20)
    ap.add_argument("--pause-seconds", type=float, default=0.5)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    packet = asyncio.run(fetch(args.symbol, args.sessions, args.client_id, args.bar_size, args.what_to_show,
                                not args.all_hours, args.end_date_time, args.max_pages, args.pause_seconds))
    Path(args.out).write_text(json.dumps(packet, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"written": args.out, "symbol": packet["symbol"], "bars": len(packet["bars"]),
                      "sessions": packet["pagination"]["session_count"], "complete_sessions": packet["pagination"]["complete_session_count"],
                      "pages": packet["pagination"]["pages_requested"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
