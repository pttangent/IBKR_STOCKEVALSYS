#!/usr/bin/env python3
"""Compute a conservative microstructure proxy from intraday OHLCV bars.

IBKR TRADES bars may include a bar count.  The count is the number of trades
reported inside the bucket, not a list of executions and not aggressor side.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def _finite(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def report(packet: dict) -> dict:
    bars = packet.get("bars", [])
    usable = []
    for bar in bars:
        close = _finite(bar.get("close"))
        volume = _finite(bar.get("volume"))
        count = _finite(bar.get("count"))
        if close is not None and volume is not None and count is not None:
            usable.append({"date": bar.get("date"), "close": close, "volume": volume, "count": count,
                           "high": _finite(bar.get("high")), "low": _finite(bar.get("low"))})
    if not usable:
        return {"status": "unavailable", "reason": "bars do not contain numeric count fields", "proxy": "bar_count_proxy"}

    total_count = sum(row["count"] for row in usable)
    total_volume = sum(row["volume"] for row in usable)
    signed_volume = 0.0
    up_bars = down_bars = flat_bars = 0
    for previous, current in zip(usable, usable[1:]):
        delta = current["close"] - previous["close"]
        if delta > 0:
            signed_volume += current["volume"]
            up_bars += 1
        elif delta < 0:
            signed_volume -= current["volume"]
            down_bars += 1
        else:
            flat_bars += 1
    ranges = [row["high"] - row["low"] for row in usable if row["high"] is not None and row["low"] is not None]
    peak = max(usable, key=lambda row: row["count"])
    return {
        "status": "ok",
        "proxy": "bar_count_proxy",
        "provider": packet.get("provider"),
        "symbol": packet.get("symbol"),
        "request": packet.get("request", {}),
        "bars": len(usable),
        "coverage_start": usable[0]["date"],
        "coverage_end": usable[-1]["date"],
        "trade_count_sum": total_count,
        "mean_trades_per_bar": total_count / len(usable),
        "max_trades_in_bar": peak["count"],
        "peak_activity_bar": peak["date"],
        "total_volume": total_volume,
        "volume_per_reported_trade": total_volume / total_count if total_count else None,
        "close_return": usable[-1]["close"] / usable[0]["close"] - 1 if usable[0]["close"] else None,
        "range_sum": sum(ranges) if ranges else None,
        "up_bars": up_bars,
        "down_bars": down_bars,
        "flat_bars": flat_bars,
        "price_change_signed_volume_proxy": signed_volume,
        "caveats": [
            "count is aggregate reported trade count per bar, not raw executions",
            "up/down classification uses close-to-close price change and is not confirmed aggressor side",
            "bar count may reflect IBKR feed aggregation and entitlement/delay status",
            "use raw historical ticks for exact time-and-sales microstructure"
        ]
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bars", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    packet = json.loads(Path(args.bars).read_text(encoding="utf-8"))
    output = report(packet)
    Path(args.out).write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": output.get("status"), "proxy": output.get("proxy"), "bars": output.get("bars")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
