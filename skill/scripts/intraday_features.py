#!/usr/bin/env python3
"""Summarize provider intraday bars without overstating them as tick data."""
from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


def number(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def percentile(values, q):
    values = sorted(values)
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * q
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return values[lower]
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def summarize(packet):
    raw = packet.get("bars", [])
    rows = []
    for bar in raw:
        row = {"date": str(bar.get("date")), "open": number(bar.get("open")), "high": number(bar.get("high")),
               "low": number(bar.get("low")), "close": number(bar.get("close")), "volume": number(bar.get("volume")),
               "count": number(bar.get("count"))}
        if row["close"] is not None and row["high"] is not None and row["low"] is not None:
            rows.append(row)
    rows.sort(key=lambda r: r["date"])
    if not rows:
        return {"status": "unavailable", "reason": "no usable intraday OHLC bars", "symbol": packet.get("symbol")}

    dates = sorted({row["date"][:10] for row in rows})
    returns = []
    ranges = []
    counts = [row["count"] for row in rows if row["count"] is not None]
    volumes = [row["volume"] for row in rows if row["volume"] is not None]
    signed_volume = 0.0
    up = down = flat = 0
    previous = None
    for row in rows:
        if row["high"] is not None and row["low"] is not None and row["close"]:
            ranges.append((row["high"] - row["low"]) / row["close"])
        if previous and previous["close"] and row["close"]:
            ret = math.log(row["close"] / previous["close"])
            returns.append(ret)
            if row["close"] > previous["close"]:
                up += 1
                if row["volume"] is not None:
                    signed_volume += row["volume"]
            elif row["close"] < previous["close"]:
                down += 1
                if row["volume"] is not None:
                    signed_volume -= row["volume"]
            else:
                flat += 1
        previous = row

    by_session = defaultdict(list)
    for row in rows:
        by_session[row["date"][:10]].append(row)
    session_summaries = []
    for day, day_rows in sorted(by_session.items()):
        day_counts = [x["count"] for x in day_rows if x["count"] is not None]
        day_volumes = [x["volume"] for x in day_rows if x["volume"] is not None]
        nonzero = [x for x in day_volumes if x > 0]
        session_summaries.append({
            "date": day, "bars": len(day_rows), "first": day_rows[0]["date"], "last": day_rows[-1]["date"],
            "open": day_rows[0]["open"], "close": day_rows[-1]["close"],
            "return": day_rows[-1]["close"] / day_rows[0]["close"] - 1 if day_rows[0]["close"] else None,
            "high": max(x["high"] for x in day_rows), "low": min(x["low"] for x in day_rows),
            "volume": sum(day_volumes) if day_volumes else None, "trade_count": sum(day_counts) if day_counts else None,
            "max_count": max(day_counts) if day_counts else None,
            "count_p95": percentile(day_counts, 0.95) if day_counts else None,
            "zero_volume_bars": sum(1 for x in day_volumes if x == 0) if day_volumes else None,
            "peak_count_bar": max(day_rows, key=lambda x: x["count"] if x["count"] is not None else -1)["date"] if day_counts else None,
        })

    # Compare the first/last 30 minutes against the session middle. This is a
    # shape diagnostic, not a claim about institutional execution.
    edge = []
    middle = []
    for day_rows in by_session.values():
        n = len(day_rows)
        if n < 6:
            continue
        edge.extend(day_rows[:min(180, n // 3)])
        edge.extend(day_rows[-min(180, n // 3):])
        middle.extend(day_rows[min(180, n // 3):-min(180, n // 3)])
    edge_counts = [x["count"] for x in edge if x["count"] is not None]
    middle_counts = [x["count"] for x in middle if x["count"] is not None]
    edge_volume = [x["volume"] for x in edge if x["volume"] is not None]
    middle_volume = [x["volume"] for x in middle if x["volume"] is not None]

    max_row = max(rows, key=lambda x: x["count"] if x["count"] is not None else -1)
    volatility = math.sqrt(sum(x * x for x in returns)) if returns else None
    provider = str(packet.get("provider") or "unknown")
    count_caveat = (
        "yfinance 目前未提供可驗證的逐筆成交數；本包的 bar count 不應解讀為逐筆成交數"
        if provider == "yfinance" else
        "Massive 聚合 bar 的 count 不是原始逐筆成交紀錄"
        if provider == "massive-rest" else
        "IBKR bar count 是每根聚合 bar 的數量，不是原始逐筆成交紀錄"
    )
    return {
        "status": "ok", "provider": packet.get("provider"), "symbol": packet.get("symbol"),
        "request": packet.get("request", {}), "coverage": {"start": rows[0]["date"], "end": rows[-1]["date"],
        "sessions": dates, "session_count": len(dates), "bars": len(rows)},
        "bar_count_proxy": {"reported_bars_with_count": len(counts), "count_sum": sum(counts) if counts else None,
                             "mean_per_bar": statistics.mean(counts) if counts else None,
                             "median_per_bar": statistics.median(counts) if counts else None,
                             "p95_per_bar": percentile(counts, 0.95) if counts else None,
                             "p99_per_bar": percentile(counts, 0.99) if counts else None,
                             "max_per_bar": max(counts) if counts else None,
                             "peak_bar": max_row["date"] if counts else None,
                             "volume_per_reported_trade": sum(volumes) / sum(counts) if counts and sum(counts) else None},
        "price_and_range": {"first_close": rows[0]["close"], "last_close": rows[-1]["close"],
                            "close_return": rows[-1]["close"] / rows[0]["close"] - 1 if rows[0]["close"] else None,
                            "realized_log_return_vol": volatility, "mean_bar_range_pct": statistics.mean(ranges) if ranges else None,
                            "max_bar_range_pct": max(ranges) if ranges else None, "up_bars": up, "down_bars": down,
                            "flat_bars": flat, "price_change_signed_volume_proxy": signed_volume},
        "activity_shape": {"edge_count_mean": statistics.mean(edge_counts) if edge_counts else None,
                           "middle_count_mean": statistics.mean(middle_counts) if middle_counts else None,
                           "edge_to_middle_count_ratio": statistics.mean(edge_counts) / statistics.mean(middle_counts) if edge_counts and middle_counts and statistics.mean(middle_counts) else None,
                           "edge_volume_mean": statistics.mean(edge_volume) if edge_volume else None,
                           "middle_volume_mean": statistics.mean(middle_volume) if middle_volume else None,
                           "edge_definition": "first and last one-third, capped at 180 bars per edge per session"},
        "sessions_detail": session_summaries,
        "caveats": [count_caveat,
                    "price-change signed volume is a heuristic proxy and does not identify aggressor side",
                    "zero-volume bars and partial sessions are retained and disclosed",
                    "use historical ticks or a direct feed for exact order-flow reconstruction"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bars", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    output = summarize(json.loads(Path(args.bars).read_text(encoding="utf-8")))
    Path(args.out).write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"written": args.out, "status": output.get("status"), "bars": output.get("coverage", {}).get("bars"),
                      "sessions": output.get("coverage", {}).get("session_count")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
