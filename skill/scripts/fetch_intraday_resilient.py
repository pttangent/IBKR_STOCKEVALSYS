#!/usr/bin/env python3
"""IBKR-first intraday acquisition with retries, chunk fallback, and source audit."""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env.local")


ROOT = Path(__file__).resolve().parent


def bar_to_dict(bar: Any) -> dict[str, Any]:
    return {"date": str(bar.date), "open": bar.open, "high": bar.high, "low": bar.low, "close": bar.close,
            "volume": bar.volume, "count": getattr(bar, "barCount", getattr(bar, "count", None)),
            "wap": getattr(bar, "average", getattr(bar, "wap", None))}


async def ibkr_request(symbol: str, duration: str, end: str, client_id: int, timeout: float) -> list[dict[str, Any]]:
    from ib_async import IB, Stock
    host = os.environ.get("IBKR_HOST", "127.0.0.1")
    port = int(os.environ.get("IBKR_PORT", "7497"))
    ib = IB()
    await ib.connectAsync(host, port, clientId=client_id, readonly=True, timeout=10)
    try:
        contract = (await ib.qualifyContractsAsync(Stock(symbol.upper(), "SMART", "USD")))[0]
        bars = await asyncio.wait_for(ib.reqHistoricalDataAsync(
            contract, endDateTime=end, durationStr=duration, barSizeSetting="1 min", whatToShow="TRADES",
            useRTH=True, formatDate=1, keepUpToDate=False), timeout=timeout)
        return [bar_to_dict(bar) for bar in bars]
    finally:
        ib.disconnect()


async def fetch_ibkr(symbol: str, end: str, client_id: int, retries: int, timeout: float, pause: float) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    durations = ["30 D"] + (["14 D", "14 D", "4 D"] if retries >= 0 else [])
    # Try the large batch once. IBKR can soft-throttle a large 1-minute
    # request without rejecting the underlying contract. Repeating the same
    # slow request only adds minutes and does not improve coverage; rebuild
    # the window in smaller pages immediately after the first timeout or
    # incomplete response. Explicit retries remain opt-in.
    for attempt in range(max(1, retries + 1)):
        started = dt.datetime.now(dt.timezone.utc)
        try:
            bars = await ibkr_request(symbol, "30 D", end, client_id + attempt, timeout)
            attempts.append({"mode": "single", "attempt": attempt + 1, "status": "ok", "bars": len(bars),
                             "elapsed_seconds": round((dt.datetime.now(dt.timezone.utc) - started).total_seconds(), 3)})
            if len(bars) >= 9000:
                return {"status": "ok", "mode": "single", "attempts": attempts}, bars
            attempts[-1]["status"] = "incomplete"
        except Exception as exc:
            attempts.append({"mode": "single", "attempt": attempt + 1, "status": "error", "error": f"{type(exc).__name__}: {exc}",
                             "elapsed_seconds": round((dt.datetime.now(dt.timezone.utc) - started).total_seconds(), 3)})
        if attempt < retries:
            await asyncio.sleep(pause * (attempt + 1))

    chunks: list[dict[str, Any]] = []
    cursor = end
    merged: dict[str, dict[str, Any]] = {}
    for index, duration in enumerate(durations[1:], 1):
        started = dt.datetime.now(dt.timezone.utc)
        try:
            page = await ibkr_request(symbol, duration, cursor, client_id + retries + index + 1, timeout)
            chunks.append({"mode": "chunk", "index": index, "duration": duration, "end": cursor, "status": "ok", "bars": len(page),
                           "elapsed_seconds": round((dt.datetime.now(dt.timezone.utc) - started).total_seconds(), 3)})
            if not page:
                break
            for bar in page:
                merged[str(bar["date"])] = bar
            earliest = min(page, key=lambda row: str(row["date"]))["date"]
            try:
                stamp = dt.datetime.fromisoformat(str(earliest).replace("Z", "+00:00")) - dt.timedelta(minutes=1)
                cursor = stamp.strftime("%Y%m%d %H:%M:%S US/Eastern")
            except ValueError:
                break
        except Exception as exc:
            chunks.append({"mode": "chunk", "index": index, "duration": duration, "end": cursor, "status": "error",
                           "error": f"{type(exc).__name__}: {exc}"})
            break
        await asyncio.sleep(pause)
    if len(merged) >= 9000:
        return {"status": "ok", "mode": "chunked", "single_attempts": attempts, "chunks": chunks}, [merged[key] for key in sorted(merged)]
    return {"status": "failed", "mode": "ibkr", "single_attempts": attempts, "chunks": chunks}, []


def optional_yfinance(symbol: str, end_date_time: str, days: int = 30) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        import yfinance as yf
    except ImportError:
        return {"status": "unavailable", "reason": "yfinance is not installed"}, []
    try:
        end_day = dt.date.fromisoformat(end_date_time[:4] + "-" + end_date_time[4:6] + "-" + end_date_time[6:8])
    except ValueError:
        end_day = dt.datetime.now(dt.timezone.utc).date()
    start_day = end_day - dt.timedelta(days=days)
    merged: dict[str, dict[str, Any]] = {}
    chunks = []
    cursor = start_day
    while cursor < end_day:
        chunk_end = min(cursor + dt.timedelta(days=7), end_day)
        try:
            frame = yf.download(symbol, start=cursor.isoformat(), end=chunk_end.isoformat(), interval="1m",
                                prepost=False, auto_adjust=False, progress=False, timeout=30)
            chunk_bars = []
            for index, row in frame.iterrows():
                def value(name):
                    item = row[name]
                    if hasattr(item, "iloc"):
                        item = item.iloc[0]
                    return float(item)
                stamp = index.isoformat()
                bar = {"date": stamp, "open": value("Open"), "high": value("High"), "low": value("Low"),
                       "close": value("Close"), "volume": value("Volume"), "count": None, "wap": None}
                merged[stamp] = bar
                chunk_bars.append(bar)
            chunks.append({"start": cursor.isoformat(), "end": chunk_end.isoformat(), "status": "ok" if chunk_bars else "empty",
                           "bars": len(chunk_bars)})
        except Exception as exc:
            chunks.append({"start": cursor.isoformat(), "end": chunk_end.isoformat(), "status": "error",
                           "error": f"{type(exc).__name__}: {exc}"})
        cursor = chunk_end
    bars = [merged[key] for key in sorted(merged)]
    if not bars:
        return {"status": "failed", "bars": 0, "chunks": chunks, "reason": "no yfinance intraday bars returned"}, []
    partial = any(chunk.get("status") != "ok" for chunk in chunks)
    return {"status": "partial" if partial else "ok", "bars": len(bars), "chunks": chunks,
            "note": "Yahoo/yfinance data; 7-day request windows; no verified time-and-sales count"}, bars


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--end-date-time", default="20260806 16:00:00 US/Eastern")
    ap.add_argument("--client-id", type=int, default=4780)
    ap.add_argument("--retries", type=int, default=0,
                    help="retries of the large 30 D request; default 0, then use IBKR chunks")
    ap.add_argument("--timeout", type=float, default=75)
    ap.add_argument("--pause-seconds", type=float, default=2.0)
    ap.add_argument("--also-massive", action="store_true", help="also query Massive for cross-check even when IBKR succeeds")
    ap.add_argument("--also-yfinance", action="store_true", help="also query yfinance for cross-check even when IBKR succeeds")
    ap.add_argument("--no-massive", action="store_true", help="disable automatic Massive fallback")
    ap.add_argument("--no-yfinance", action="store_true", help="disable automatic yfinance fallback")
    ap.add_argument("--massive-start", default="2026-06-25")
    ap.add_argument("--massive-end", default="2026-08-07")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    try:
        from ib_async import IB  # noqa: F401
        ibkr_available = True
    except ImportError:
        ibkr_available = False
    if ibkr_available:
        ibkr_audit, bars = asyncio.run(fetch_ibkr(args.symbol, args.end_date_time, args.client_id, args.retries, args.timeout, args.pause_seconds))
    else:
        ibkr_audit, bars = {"status": "unavailable", "reason": "ib_async is not installed"}, []
    sources = {"ibkr": ibkr_audit}
    selected = "ibkr" if bars else None
    if (not bars and not args.no_massive) or args.also_massive:
        spec = importlib.util.spec_from_file_location("fetch_massive_intraday", ROOT / "fetch_massive_intraday.py")
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        try:
            packet = module.fetch(args.symbol, args.massive_start, args.massive_end, rth_only=True)
            sources["massive"] = {"status": "ok", "bars": len(packet["bars"]), "response": packet.get("response")}
            if not bars:
                bars = packet["bars"]
                selected = "massive"
        except Exception as exc:
            sources["massive"] = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    if (not bars and not args.no_yfinance) or args.also_yfinance:
        audit, yf_bars = optional_yfinance(args.symbol, args.end_date_time)
        sources["yfinance"] = audit
        if not bars and yf_bars:
            bars, selected = yf_bars, "yfinance"
    output = {"provider": selected, "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(), "symbol": args.symbol.upper(),
              "request": {"target": "30 calendar days of 1-minute RTH TRADES", "end_date_time": args.end_date_time},
              "source_selection": {"priority": ["ibkr", "massive", "yfinance"], "selected": selected, "sources": sources},
              "bars": bars}
    Path(args.out).write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"written": args.out, "selected": selected, "bars": len(bars), "sources": sources}, ensure_ascii=False))


if __name__ == "__main__":
    main()
