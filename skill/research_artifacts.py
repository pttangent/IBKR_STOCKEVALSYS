from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EVIDENCE_LABELS = {"FACT", "DATA_RESULT", "MODEL_OUTPUT", "INFERENCE", "ASSUMPTION", "UNVERIFIED"}
REVIEW_ROLES = {"bull", "bear", "skeptic"}


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) == 10:
        return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
    text = text.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def canonical_sha256(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_evidence_packet(symbol: str, as_of: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
    ids = [s.get("source_id") for s in sources]
    if any(not x for x in ids):
        raise ValueError("Every source packet must have source_id")
    if len(set(ids)) != len(ids):
        raise ValueError("source_id values must be unique")
    payload = {
        "schema_version": "1.0",
        "symbol": symbol.upper(),
        "as_of": as_of,
        "sources": sources,
        "source_ids": ids,
        "warnings": [],
        "missing_evidence_requests": [],
    }
    payload["evidence_freeze_hash"] = canonical_sha256(payload)
    return payload


def validate_evidence_packet(packet: dict[str, Any], *, pit_strict: bool = False) -> list[str]:
    errors: list[str] = []
    cutoff = parse_time(packet.get("as_of"))
    if cutoff is None:
        errors.append("evidence packet missing/invalid as_of")
    sources = packet.get("sources")
    if not isinstance(sources, list) or not sources:
        errors.append("evidence packet requires non-empty sources")
        return errors
    ids: list[str] = []
    for idx, source in enumerate(sources):
        prefix = f"sources[{idx}]"
        sid = source.get("source_id")
        if not sid:
            errors.append(f"{prefix} missing source_id")
        else:
            ids.append(sid)
        if not source.get("provider"):
            errors.append(f"{prefix} missing provider")
        if not source.get("reliability"):
            errors.append(f"{prefix} missing reliability")
        available = parse_time(source.get("available_at"))
        if pit_strict:
            if available is None:
                errors.append(f"{prefix} has no available_at; cannot prove PIT eligibility")
            elif cutoff is not None and available > cutoff:
                errors.append(f"{prefix} available_at {source.get('available_at')} is after research cutoff {packet.get('as_of')}")
    if len(ids) != len(set(ids)):
        errors.append("duplicate source_id values")
    expected_hash = packet.get("evidence_freeze_hash")
    if expected_hash:
        clone = dict(packet)
        clone.pop("evidence_freeze_hash", None)
        # Hash is computed before the hash field itself is attached.
        if canonical_sha256(clone) != expected_hash:
            errors.append("evidence_freeze_hash does not match packet content")
    return errors


def validate_claim_graph(graph: dict[str, Any], evidence_packet: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    source_ids = set(evidence_packet.get("source_ids") or [s.get("source_id") for s in evidence_packet.get("sources", [])])
    claims = graph.get("claims")
    if not isinstance(claims, list):
        return ["claim graph requires claims list"]
    claim_ids: set[str] = set()
    for idx, claim in enumerate(claims):
        cid = claim.get("claim_id")
        if not cid:
            errors.append(f"claims[{idx}] missing claim_id")
        elif cid in claim_ids:
            errors.append(f"duplicate claim_id {cid}")
        else:
            claim_ids.add(cid)
        label = claim.get("label")
        if label not in EVIDENCE_LABELS:
            errors.append(f"claims[{idx}] invalid label {label!r}")
        refs = claim.get("evidence_refs") or []
        unknown = [r for r in refs if r not in source_ids]
        if unknown:
            errors.append(f"claims[{idx}] references unknown evidence sources: {unknown}")
        if label in {"FACT", "DATA_RESULT", "MODEL_OUTPUT", "INFERENCE"} and not refs:
            errors.append(f"claims[{idx}] label {label} requires evidence_refs")
        if not claim.get("invalidation") and label in {"INFERENCE", "MODEL_OUTPUT"}:
            errors.append(f"claims[{idx}] {label} requires invalidation")
    return errors


def validate_review(review: dict[str, Any], graph: dict[str, Any], evidence_packet: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    role = review.get("role")
    if role not in REVIEW_ROLES:
        errors.append(f"invalid review role {role!r}")
    claim_ids = {c.get("claim_id") for c in graph.get("claims", [])}
    source_ids = set(evidence_packet.get("source_ids") or [])
    for idx, finding in enumerate(review.get("findings") or []):
        cid = finding.get("claim_id")
        if cid and cid not in claim_ids:
            errors.append(f"findings[{idx}] unknown claim_id {cid}")
        unknown = [x for x in finding.get("evidence_refs", []) if x not in source_ids]
        if unknown:
            errors.append(f"findings[{idx}] uses evidence outside freeze: {unknown}")
        if not finding.get("reason"):
            errors.append(f"findings[{idx}] missing reason")
    # Reviewers may request new evidence but may not silently cite it as if already present.
    for idx, req in enumerate(review.get("evidence_requests") or []):
        if not req.get("request"):
            errors.append(f"evidence_requests[{idx}] missing request")
    return errors


def validate_arbitration(
    arbitration: dict[str, Any],
    graph: dict[str, Any],
    evidence_packet: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    source_ids = set(evidence_packet.get("source_ids") or [])
    claim_ids = {c.get("claim_id") for c in graph.get("claims", [])}
    scenarios = arbitration.get("scenarios") or {}
    numeric = []
    for name, scenario in scenarios.items():
        probability = scenario.get("probability") if isinstance(scenario, dict) else None
        if probability is not None:
            if not isinstance(probability, (int, float)) or not 0 <= probability <= 1:
                errors.append(f"scenario {name} probability must be between 0 and 1")
            else:
                numeric.append(float(probability))
    if numeric and abs(sum(numeric) - 1.0) > 1e-6:
        errors.append(f"numeric scenario probabilities sum to {sum(numeric):.6f}, not 1")
    for idx, adj in enumerate(arbitration.get("claim_adjustments") or []):
        if adj.get("claim_id") not in claim_ids:
            errors.append(f"claim_adjustments[{idx}] unknown claim_id {adj.get('claim_id')}")
        unknown = [x for x in adj.get("evidence_refs", []) if x not in source_ids]
        if unknown:
            errors.append(f"claim_adjustments[{idx}] uses evidence outside freeze: {unknown}")
    return errors
