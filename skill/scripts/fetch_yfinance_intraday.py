#!/usr/bin/env python3
"""Optional Yahoo/yfinance 1-minute fallback, chunked to Yahoo's request window."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from fetch_intraday_resilient import optional_yfinance


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--end-date-time", default="20260806 16:00:00 US/Eastern")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    audit, bars = optional_yfinance(args.symbol, args.end_date_time, args.days)
    packet = {"provider": "yfinance", "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "symbol": args.symbol.upper(), "request": {"interval": "1m", "days": args.days,
              "end_date_time": args.end_date_time, "prepost": False}, "audit": audit, "bars": bars}
    Path(args.out).write_text(json.dumps(packet, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"written": args.out, "provider": packet["provider"], "status": audit.get("status"), "bars": len(bars)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
