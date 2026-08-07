#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research_artifacts import (
    load_json,
    validate_arbitration,
    validate_claim_graph,
    validate_evidence_packet,
    validate_review,
)


def main() -> None:
    ap = argparse.ArgumentParser(description="Cross-validate evidence, claim graph, adversarial reviews, and arbitration.")
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--claims")
    ap.add_argument("--review", action="append", default=[])
    ap.add_argument("--arbitration")
    ap.add_argument("--pit-strict", action="store_true")
    args = ap.parse_args()

    evidence = load_json(args.evidence)
    errors = validate_evidence_packet(evidence, pit_strict=args.pit_strict)
    claims = load_json(args.claims) if args.claims else None
    if claims is not None:
        errors += validate_claim_graph(claims, evidence)
    for review_path in args.review:
        if claims is None:
            errors.append("--review requires --claims")
            break
        errors += validate_review(load_json(review_path), claims, evidence)
    if args.arbitration:
        if claims is None:
            errors.append("--arbitration requires --claims")
        else:
            errors += validate_arbitration(load_json(args.arbitration), claims, evidence)

    if errors:
        raise SystemExit("FAIL research artifacts:\n- " + "\n- ".join(errors))
    print("OK research artifacts")


if __name__ == "__main__":
    main()
