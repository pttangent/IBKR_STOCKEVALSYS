#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

STATES = {"RESEARCH_READY", "READY_CONDITIONAL", "WAIT_CONFIRMATION", "NEEDS_EVIDENCE", "RISK_BLOCKED", "MONITOR_ONLY", "THESIS_INVALIDATED"}
REQUIRED_MODULE = {"title", "status", "freshness_status", "source_artifacts", "missing_fields"}
REQUIRED_INTERPRETATION = {"what", "read", "why", "limit"}


def validate(data: dict) -> list[str]:
    errors: list[str] = []
    for key in ["schema_version", "run_id", "symbol", "as_of", "research_state", "modules"]:
        if key not in data:
            errors.append(f"missing top-level {key}")
    if data.get("research_state") not in STATES:
        errors.append("invalid research_state")
    if not isinstance(data.get("modules"), dict):
        errors.append("modules must be object")
        return errors
    for name, module in data["modules"].items():
        if not isinstance(module, dict):
            errors.append(f"module {name} not object")
            continue
        for key in REQUIRED_MODULE:
            if key not in module:
                errors.append(f"module {name} missing {key}")
        for index, chart in enumerate(module.get("charts", [])):
            if not all(chart.get(key) for key in ["id", "kind", "title"]):
                errors.append(f"module {name} chart {index} missing id/kind/title")
            interpretation = chart.get("interpretation", {})
            for key in REQUIRED_INTERPRETATION:
                if not str(interpretation.get(key) or "").strip():
                    errors.append(f"module {name} chart {chart.get('id', index)} missing interpretation.{key}")
    return errors


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    args = ap.parse_args()
    data = json.loads(Path(args.report).read_text(encoding="utf-8"))
    errors = validate(data)
    if errors:
        raise SystemExit("FAIL structured report:\n- " + "\n- ".join(errors))
    print("OK structured report")


if __name__ == "__main__":
    main()
