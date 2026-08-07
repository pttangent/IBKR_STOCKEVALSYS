#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research_artifacts import build_evidence_packet, load_json, validate_evidence_packet


def main() -> None:
    ap = argparse.ArgumentParser(description="Freeze provider source packets into one immutable research evidence packet.")
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--as-of", required=True)
    ap.add_argument("--source", action="append", required=True, help="Provider packet JSON; repeat for multiple sources")
    ap.add_argument("--pit-strict", action="store_true")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    sources = [load_json(p) for p in args.source]
    packet = build_evidence_packet(args.symbol, args.as_of, sources)
    errors = validate_evidence_packet(packet, pit_strict=args.pit_strict)
    if errors:
        raise SystemExit("FAIL evidence packet:\n- " + "\n- ".join(errors))
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK evidence sources={len(sources)} freeze={packet['evidence_freeze_hash'][:12]} -> {out}")


if __name__ == "__main__":
    main()
