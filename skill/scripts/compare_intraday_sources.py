#!/usr/bin/env python3
"""Compare intraday bars by timestamp while keeping volume-unit caveats explicit."""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


def key(row):
    return str(row.get("date", "")).replace("T", " ")[:19]


def load(path):
    packet = json.loads(Path(path).read_text(encoding="utf-8"))
    return packet, {key(row): row for row in packet.get("bars", []) if key(row)}


def compare(left_path, right_path):
    left_packet, left = load(left_path)
    right_packet, right = load(right_path)
    common = sorted(set(left) & set(right))
    close_bp = []
    for stamp in common:
        a, b = left[stamp], right[stamp]
        try:
            close_bp.append(abs(float(a["close"]) - float(b["close"])) / float(b["close"]) * 10000)
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            pass
    def total(name, packet):
        return sum(float(row.get(name) or 0) for row in packet.get("bars", []))
    return {"status": "ok", "left": {"provider": left_packet.get("provider"), "bars": len(left),
            "start": min(left) if left else None, "end": max(left) if left else None},
            "right": {"provider": right_packet.get("provider"), "bars": len(right), "start": min(right) if right else None,
            "end": max(right) if right else None}, "common_timestamps": len(common),
            "close_deviation_bp": {"median": statistics.median(close_bp) if close_bp else None,
            "p95": sorted(close_bp)[int((len(close_bp) - 1) * 0.95)] if close_bp else None,
            "max": max(close_bp) if close_bp else None},
            "volume": {"left_sum": total("volume", left_packet), "right_sum": total("volume", right_packet),
                       "ratio_left_to_right": total("volume", left_packet) / total("volume", right_packet) if total("volume", right_packet) else None,
                       "warning": "IBKR volume may be shares or round lots depending on TWS API setting; do not treat volume ratio as a price mismatch"},
            "count": {"left_present": sum(1 for row in left_packet.get("bars", []) if row.get("count") is not None),
                      "right_present": sum(1 for row in right_packet.get("bars", []) if row.get("count") is not None)},
            "caveats": ["timestamps are normalized only to seconds; provider session/timezone rules still apply",
                        "a close match does not prove identical trade-condition filtering",
                        "volume comparisons require unit normalization"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--left", required=True)
    ap.add_argument("--right", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    result = compare(args.left, args.right)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"written": args.out, "common_timestamps": result["common_timestamps"], "max_close_bp": result["close_deviation_bp"]["max"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
