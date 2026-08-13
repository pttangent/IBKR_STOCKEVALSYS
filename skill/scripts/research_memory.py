#!/usr/bin/env python3
"""Local decision-memory and calibration utility.

No external APIs, no brokerage calls, and no MCP mutations. The utility only
creates/updates local JSON research records and computes simple calibration
statistics from completed records.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path
from typing import Any

SCENARIOS = ("bull", "base", "bear", "unknown", "event")


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, payload: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_probabilities(probabilities: dict[str, Any]) -> None:
    numeric = {k: v for k, v in probabilities.items() if k in SCENARIOS and v is not None}
    if not numeric:
        return
    for key, value in numeric.items():
        if not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f"invalid probability for {key}: {value!r}")
    total = sum(numeric.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"scenario probabilities must sum to 1.0, got {total:.6f}")


def freeze_decision(source: dict[str, Any]) -> dict[str, Any]:
    required = ("run_id", "symbol", "as_of", "primary_horizon", "research_state", "scenario_probabilities", "thesis_claim_ids", "key_invalidation_conditions")
    missing = [k for k in required if k not in source]
    if missing:
        raise ValueError(f"missing required decision fields: {missing}")
    validate_probabilities(source.get("scenario_probabilities", {}))
    out = dict(source)
    out["frozen_at"] = source.get("frozen_at") or now_utc()
    out.setdefault("outcome", None)
    return out


def attach_outcome(decision: dict[str, Any], outcome: dict[str, Any]) -> dict[str, Any]:
    if decision.get("outcome") not in (None, {}):
        raise ValueError("decision already has an outcome; create a new record/version instead of overwriting")
    out = dict(decision)
    outcome = dict(outcome)
    outcome.setdefault("attached_at", now_utc())
    out["outcome"] = outcome
    return out


def brier_score(probabilities: dict[str, Any], observed: str) -> float | None:
    numeric = {k: v for k, v in probabilities.items() if k in SCENARIOS and isinstance(v, (int, float))}
    if observed not in numeric or not numeric:
        return None
    if abs(sum(numeric.values()) - 1.0) > 1e-6:
        return None
    return sum((float(p) - (1.0 if k == observed else 0.0)) ** 2 for k, p in numeric.items())


def range_coverage(decision: dict[str, Any], outcome: dict[str, Any]) -> dict[str, Any] | None:
    rng = decision.get("expected_range")
    realized = outcome.get("end_price")
    if not isinstance(rng, dict) or not isinstance(realized, (int, float)):
        return None
    lo, hi = rng.get("lower"), rng.get("upper")
    if not isinstance(lo, (int, float)) or not isinstance(hi, (int, float)) or hi < lo:
        return None
    ref = rng.get("reference_price")
    width_pct = (hi - lo) / ref if isinstance(ref, (int, float)) and ref > 0 else None
    return {"covered": bool(lo <= realized <= hi), "range_width_pct": width_pct}


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [r for r in records if isinstance(r.get("outcome"), dict)]
    briers: list[float] = []
    covered: list[bool] = []
    alphas: list[float] = []
    state_counts: dict[str, int] = {}
    scenario_counts: dict[str, int] = {}

    for r in completed:
        state = str(r.get("research_state", "UNKNOWN"))
        state_counts[state] = state_counts.get(state, 0) + 1
        outcome = r["outcome"]
        observed = outcome.get("observed_scenario")
        if isinstance(observed, str):
            scenario_counts[observed] = scenario_counts.get(observed, 0) + 1
            score = brier_score(r.get("scenario_probabilities", {}), observed)
            if score is not None:
                briers.append(score)
        cov = range_coverage(r, outcome)
        if cov is not None:
            covered.append(cov["covered"])
        alpha = outcome.get("alpha")
        if isinstance(alpha, (int, float)) and math.isfinite(alpha):
            alphas.append(float(alpha))

    return {
        "records": len(records),
        "completed": len(completed),
        "mean_multiclass_brier": sum(briers) / len(briers) if briers else None,
        "range_coverage_rate": sum(covered) / len(covered) if covered else None,
        "mean_alpha": sum(alphas) / len(alphas) if alphas else None,
        "research_state_counts": state_counts,
        "observed_scenario_counts": scenario_counts,
        "notes": [
            "Brier score is reported only for records with numeric probabilities summing to 1 and a resolved observed_scenario.",
            "Calibration conclusions require adequate sample size; these aggregates are diagnostics, not proof of edge."
        ],
    }


def collect_records(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if p.is_file():
        payload = load_json(p)
        return payload if isinstance(payload, list) else [payload]
    records = []
    for file in sorted(p.rglob("decision.json")):
        try:
            records.append(load_json(file))
        except (json.JSONDecodeError, OSError):
            continue
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Local decision memory and calibration")
    sub = parser.add_subparsers(dest="command", required=True)

    freeze = sub.add_parser("freeze", help="freeze an ex-ante decision JSON")
    freeze.add_argument("--input", required=True)
    freeze.add_argument("--out", required=True)

    attach = sub.add_parser("attach-outcome", help="attach outcome to a frozen decision")
    attach.add_argument("--decision", required=True)
    attach.add_argument("--outcome", required=True)
    attach.add_argument("--out", required=True)

    cal = sub.add_parser("calibrate", help="summarize completed decision records")
    cal.add_argument("--path", required=True, help="decision JSON, JSON list, or directory containing decision.json files")
    cal.add_argument("--out")

    args = parser.parse_args()
    try:
        if args.command == "freeze":
            payload = freeze_decision(load_json(args.input))
            write_json(args.out, payload)
            print(json.dumps({"status": "ok", "out": args.out, "run_id": payload["run_id"]}, ensure_ascii=False))
            return 0
        if args.command == "attach-outcome":
            payload = attach_outcome(load_json(args.decision), load_json(args.outcome))
            write_json(args.out, payload)
            print(json.dumps({"status": "ok", "out": args.out, "run_id": payload["run_id"]}, ensure_ascii=False))
            return 0
        if args.command == "calibrate":
            summary = summarize(collect_records(args.path))
            if args.out:
                write_json(args.out, summary)
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
