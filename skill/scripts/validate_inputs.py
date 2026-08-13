#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stock_eval_engine import normalize_bars, norm_options

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bars", required=True)
    ap.add_argument("--options")
    args = ap.parse_args()
    bars = normalize_bars(json.loads(Path(args.bars).read_text(encoding="utf-8")))
    if len(bars) < 30:
        raise SystemExit(f"FAIL: need >=30 valid bars, got {len(bars)}")
    if any(bars[i]["date"] > bars[i+1]["date"] for i in range(len(bars)-1)):
        raise SystemExit("FAIL: bars are not ordered")
    if args.options:
        options = norm_options(json.loads(Path(args.options).read_text(encoding="utf-8")))
        crossed = [x for x in options if x["bid"] is not None and x["ask"] is not None and x["bid"] > x["ask"]]
        if crossed:
            raise SystemExit(f"FAIL: {len(crossed)} crossed option markets")
        print(f"OK bars={len(bars)} options={len(options)}")
    else:
        print(f"OK bars={len(bars)}")

if __name__ == "__main__":
    main()
