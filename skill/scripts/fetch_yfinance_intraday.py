#!/usr/bin/env python3
"""Optional Yahoo/yfinance 1-minute fallback, chunked to Yahoo's request window."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from fetch_intraday_resilient import optional_yfinance

NY = ZoneInfo("America/New_York")


def effective_end_date_time(requested: str | None) -> tuple[str, bool]:
    """Return an exchange-time cursor that is never in the future."""
    now = dt.datetime.now(NY)
    if not requested:
        return now.strftime("%Y%m%d %H:%M:%S US/Eastern"), False
    text = requested.strip()
    try:
        parsed = dt.datetime.strptime(text.replace(" US/Eastern", ""), "%Y%m%d %H:%M:%S").replace(tzinfo=NY)
    except ValueError:
        raise SystemExit("--end-date-time must use YYYYMMDD HH:mm:ss US/Eastern")
    if parsed > now:
        return now.strftime("%Y%m%d %H:%M:%S US/Eastern"), True
    return parsed.strftime("%Y%m%d %H:%M:%S US/Eastern"), False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--end-date-time", help="YYYYMMDD HH:mm:ss US/Eastern; default=current exchange time; future values are capped")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    effective_end, capped = effective_end_date_time(args.end_date_time)
    audit, bars = optional_yfinance(args.symbol, effective_end, args.days)
    packet = {
        "provider": "yfinance",
        "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "symbol": args.symbol.upper(),
        "request": {
            "interval": "1m", "days": args.days,
            "requested_end_date_time": args.end_date_time,
            "end_date_time": effective_end,
            "future_cursor_capped": capped,
            "prepost": False,
        },
        "audit": audit,
        "bars": bars,
    }
    Path(args.out).write_text(json.dumps(packet, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"written": args.out, "provider": packet["provider"], "status": audit.get("status"), "bars": len(bars), "future_cursor_capped": capped}, ensure_ascii=False))


if __name__ == "__main__":
    main()
