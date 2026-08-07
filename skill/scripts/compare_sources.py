#!/usr/bin/env python3
"""Compare two normalized OHLCV packets without modifying either source."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stock_eval_engine import load_json, normalize_bars

def compare(left_payload, right_payload):
    left = {x["date"][:10]: x for x in normalize_bars(left_payload)}
    right = {x["date"][:10]: x for x in normalize_bars(right_payload)}
    common = sorted(set(left) & set(right))
    diffs = []
    for date in common:
        a, b = left[date], right[date]
        diffs.append({"date": date, "close_abs": abs(a["close"]-b["close"]), "close_bps": abs(a["close"]-b["close"])/b["close"]*10000, "high_abs": abs(a["high"]-b["high"]), "low_abs": abs(a["low"]-b["low"]), "volume_pct": abs(a["volume"]-b["volume"])/b["volume"]*100 if b["volume"] else None})
    latest = diffs[-1] if diffs else None
    return {"left_bars": len(left), "right_bars": len(right), "common_days": len(common), "left_only_days": sorted(set(left)-set(right)), "right_only_days": sorted(set(right)-set(left)), "latest_common": latest, "max_close_bps": max((x["close_bps"] for x in diffs), default=None), "median_close_bps": sorted(x["close_bps"] for x in diffs)[len(diffs)//2] if diffs else None, "max_volume_pct": max((x["volume_pct"] for x in diffs if x["volume_pct"] is not None), default=None), "interpretation": "price series broadly aligned; inspect volume definitions and missing sessions" if diffs and max(x["close_bps"] for x in diffs) < 10 else "material price/date differences require provider reconciliation"}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--left",required=True); ap.add_argument("--right",required=True); ap.add_argument("--left-name",default="left"); ap.add_argument("--right-name",default="right"); ap.add_argument("--out",required=True); args=ap.parse_args()
    result=compare(load_json(args.left),load_json(args.right)); result["left_name"]=args.left_name; result["right_name"]=args.right_name
    Path(args.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); print(json.dumps(result,ensure_ascii=False))
if __name__ == "__main__": main()
