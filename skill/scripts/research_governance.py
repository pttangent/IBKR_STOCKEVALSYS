#!/usr/bin/env python3
"""Deterministic validation helpers for the stock-eval research-governance layer.

This module performs no network calls and does not talk to MCP services. It checks
claim graphs, constrained reviews, and arbitration payloads so that LLM reasoning
cannot silently detach from the frozen evidence/claim universe.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

CLAIM_TYPES = {"FACT", "DATA_RESULT", "MODEL_OUTPUT", "INFERENCE", "ASSUMPTION", "UNVERIFIED"}
DIRECTIONS = {"positive", "negative", "neutral", "mixed"}
CLAIM_STATUSES = {"supported", "contested", "unresolved", "invalidated"}
REVIEWERS = {"bull", "bear", "skeptic"}
ASSESSMENTS = {"strengthen", "weaken", "invalidate", "unchanged", "unresolved"}
RESEARCH_STATES = {
    "RESEARCH_READY",
    "READY_CONDITIONAL",
    "WAIT_CONFIRMATION",
    "NEEDS_EVIDENCE",
    "RISK_BLOCKED",
    "MONITOR_ONLY",
    "THESIS_INVALIDATED",
}
SCENARIOS = {"bull", "base", "bear", "unknown", "event"}


def _load(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _probability_sum(obj: dict[str, Any]) -> float | None:
    values = [v for k, v in obj.items() if k in SCENARIOS and v is not None]
    if not values:
        return None
    if not all(isinstance(v, (int, float)) and math.isfinite(v) and 0 <= v <= 1 for v in values):
        return math.nan
    return float(sum(values))


def validate_claim_graph(graph: dict[str, Any], evidence_ids: set[str] | None = None) -> list[str]:
    errors: list[str] = []
    claims = graph.get("claims")
    if not isinstance(claims, list) or not claims:
        return ["claim graph must contain a non-empty claims list"]

    ids: list[str] = []
    for i, claim in enumerate(claims):
        prefix = f"claims[{i}]"
        cid = claim.get("claim_id")
        if not isinstance(cid, str) or not cid.strip():
            errors.append(f"{prefix}.claim_id missing")
            continue
        ids.append(cid)
        if claim.get("claim_type") not in CLAIM_TYPES:
            errors.append(f"{cid}: invalid claim_type")
        if claim.get("direction") not in DIRECTIONS:
            errors.append(f"{cid}: invalid direction")
        if claim.get("status") not in CLAIM_STATUSES:
            errors.append(f"{cid}: invalid status")
        if not isinstance(claim.get("statement"), str) or not claim["statement"].strip():
            errors.append(f"{cid}: statement missing")
        if not isinstance(claim.get("horizon"), str) or not claim["horizon"].strip():
            errors.append(f"{cid}: horizon missing")

        support = claim.get("supporting_evidence_ids", [])
        deps = claim.get("depends_on", [])
        if not isinstance(support, list) or not isinstance(deps, list):
            errors.append(f"{cid}: evidence/dependency fields must be arrays")
            continue
        if claim.get("claim_type") == "FACT" and not support:
            errors.append(f"{cid}: FACT requires supporting_evidence_ids")
        if claim.get("claim_type") == "INFERENCE" and not support and not deps:
            errors.append(f"{cid}: INFERENCE requires evidence or upstream claim dependency")
        if evidence_ids is not None:
            unknown = sorted(set(support) - evidence_ids)
            if unknown:
                errors.append(f"{cid}: unknown supporting evidence IDs: {unknown}")

    duplicate = sorted({x for x in ids if ids.count(x) > 1})
    if duplicate:
        errors.append(f"duplicate claim IDs: {duplicate}")

    known_claims = set(ids)
    for claim in claims:
        cid = claim.get("claim_id", "<unknown>")
        unknown_deps = sorted(set(claim.get("depends_on", [])) - known_claims)
        if unknown_deps:
            errors.append(f"{cid}: unknown depends_on claim IDs: {unknown_deps}")
        if cid in set(claim.get("depends_on", [])):
            errors.append(f"{cid}: claim cannot depend on itself")

    return errors


def validate_review(review: dict[str, Any], claim_ids: set[str], evidence_ids: set[str] | None = None) -> list[str]:
    errors: list[str] = []
    reviewer = review.get("reviewer")
    if reviewer not in REVIEWERS:
        errors.append("invalid reviewer")
    for i, item in enumerate(review.get("claim_reviews", [])):
        cid = item.get("claim_id")
        if cid not in claim_ids:
            errors.append(f"claim_reviews[{i}]: unknown claim_id {cid!r}")
        if item.get("assessment") not in ASSESSMENTS:
            errors.append(f"claim_reviews[{i}]: invalid assessment")
        if not isinstance(item.get("reason"), str) or not item["reason"].strip():
            errors.append(f"claim_reviews[{i}]: reason missing")
        refs = item.get("evidence_ids", [])
        if evidence_ids is not None:
            unknown = sorted(set(refs) - evidence_ids)
            if unknown:
                errors.append(f"claim_reviews[{i}]: unknown evidence IDs: {unknown}")
        delta = item.get("confidence_delta")
        if delta is not None and (not isinstance(delta, (int, float)) or not -1 <= delta <= 1):
            errors.append(f"claim_reviews[{i}]: confidence_delta outside [-1,1]")

    deltas = review.get("scenario_probability_deltas", {})
    if not isinstance(deltas, dict):
        errors.append("scenario_probability_deltas must be an object")
    else:
        unknown_keys = set(deltas) - SCENARIOS
        if unknown_keys:
            errors.append(f"unknown scenario delta keys: {sorted(unknown_keys)}")
        for key, value in deltas.items():
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                errors.append(f"scenario delta {key} must be finite numeric")
    return errors


def validate_arbitration(arbitration: dict[str, Any], claim_ids: set[str]) -> list[str]:
    errors: list[str] = []
    if arbitration.get("research_state") not in RESEARCH_STATES:
        errors.append("invalid research_state")
    for field in ("material_supported_claims", "material_contested_claims", "material_unresolved_claims"):
        values = arbitration.get(field, [])
        if not isinstance(values, list):
            errors.append(f"{field} must be a list")
            continue
        unknown = sorted(set(values) - claim_ids)
        if unknown:
            errors.append(f"{field} contains unknown claim IDs: {unknown}")
    probabilities = arbitration.get("scenario_probabilities", {})
    if probabilities:
        total = _probability_sum(probabilities)
        if total is None or math.isnan(total):
            errors.append("scenario_probabilities contain invalid values")
        elif abs(total - 1.0) > 1e-6:
            errors.append(f"scenario_probabilities must sum to 1.0, got {total:.6f}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate claim/review/arbitration governance payloads")
    parser.add_argument("--claims", required=True, help="claim_graph.json")
    parser.add_argument("--evidence-manifest", help="JSON containing evidence IDs under evidence_ids or records[*].evidence_id")
    parser.add_argument("--review", action="append", default=[], help="review JSON; may be repeated")
    parser.add_argument("--arbitration", help="arbitration JSON")
    args = parser.parse_args()

    graph = _load(args.claims)
    evidence_ids: set[str] | None = None
    if args.evidence_manifest:
        manifest = _load(args.evidence_manifest)
        evidence_ids = set(manifest.get("evidence_ids", []))
        evidence_ids.update(
            r.get("evidence_id") for r in manifest.get("records", []) if isinstance(r, dict) and r.get("evidence_id")
        )

    errors = validate_claim_graph(graph, evidence_ids)
    claim_ids = {c.get("claim_id") for c in graph.get("claims", []) if c.get("claim_id")}
    for path in args.review:
        errors.extend(f"{path}: {e}" for e in validate_review(_load(path), claim_ids, evidence_ids))
    if args.arbitration:
        errors.extend(f"{args.arbitration}: {e}" for e in validate_arbitration(_load(args.arbitration), claim_ids))

    if errors:
        print(json.dumps({"status": "invalid", "errors": errors}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps({"status": "ok", "claim_count": len(claim_ids), "review_count": len(args.review)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
