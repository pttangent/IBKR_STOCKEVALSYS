#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research_memory import calibration_summary, connect, record_decision, record_outcome


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser(description="Structured decision/outcome memory for research calibration.")
    ap.add_argument("--db", default="runs/decision_memory.sqlite")
    sub = ap.add_subparsers(dest="command", required=True)

    rec = sub.add_parser("record")
    rec.add_argument("--decision", required=True)

    out = sub.add_parser("outcome")
    out.add_argument("--decision-id", required=True)
    out.add_argument("--outcome", required=True)

    summary = sub.add_parser("summary")
    summary.add_argument("--symbol")

    args = ap.parse_args()
    conn = connect(args.db)
    try:
        if args.command == "record":
            did = record_decision(conn, load(args.decision))
            print(did)
        elif args.command == "outcome":
            oid = record_outcome(conn, args.decision_id, load(args.outcome))
            print(oid)
        else:
            print(json.dumps(calibration_summary(conn, args.symbol), ensure_ascii=False, indent=2))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
