#!/usr/bin/env python3
"""Validate high-value report-output invariants without external dependencies."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ALLOWED_STATES = {
    "RESEARCH_READY", "READY_CONDITIONAL", "WAIT_CONFIRMATION", "NEEDS_EVIDENCE",
    "RISK_BLOCKED", "MONITOR_ONLY", "THESIS_INVALIDATED",
}


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate(doc: dict) -> list[str]:
    errors: list[str] = []
    for key in ("schema_version", "symbol", "as_of", "research_state", "modules"):
        if key not in doc:
            errors.append(f"missing top-level field: {key}")
    if doc.get("research_state") not in ALLOWED_STATES:
        errors.append(f"invalid research_state: {doc.get('research_state')!r}")
    modules = doc.get("modules")
    if not isinstance(modules, dict):
        return errors + ["modules must be an object"]
    for name, module in modules.items():
        if not isinstance(module, dict):
            errors.append(f"module {name}: must be an object")
            continue
        for key in ("status", "freshness_status", "source_artifacts", "missing_fields"):
            if key not in module:
                errors.append(f"module {name}: missing {key}")
        if module.get("freshness_status") == "stale_after_material_event" and module.get("status") not in {
            "unverified", "needs_evidence", "risk_blocked", "stale"
        }:
            errors.append(
                f"module {name}: stale_after_material_event cannot be published with status={module.get('status')!r}"
            )
        for key in ("source_artifacts", "missing_fields", "evidence_ids", "limitations"):
            if key in module and not isinstance(module[key], list):
                errors.append(f"module {name}: {key} must be a list")
        metrics = module.get("metrics", {})
        if isinstance(metrics, dict):
            gamma_status = metrics.get("gamma_status")
            wall = metrics.get("gamma_wall") or metrics.get("largest_gamma_concentration")
            if gamma_status in {"UNAVAILABLE_ZERO_OR_UNTRUSTED_OI", "unavailable", "not_observed"} and wall not in (None, {}, []):
                errors.append(f"module {name}: unavailable gamma must not publish a wall/concentration")
            if metrics.get("intraday_evidence_available") is False and metrics.get("timing_label") in {
                "today_timing", "opening_confirmation", "intraday_confirmed"
            }:
                errors.append(f"module {name}: intraday timing label requires intraday evidence")
    return errors


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    args = ap.parse_args()
    errors = validate(load(args.manifest))
    if errors:
        raise SystemExit("FAIL report manifest:\n- " + "\n- ".join(errors))
    print("OK report manifest")


if __name__ == "__main__":
    main()
