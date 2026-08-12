#!/usr/bin/env python3
"""Render Markdown from canonical structured_report.json. No Markdown is parsed as input."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def text(value):
    return "—" if value is None or value == "" else str(value)


def render_block(block: dict) -> str:
    kind = block.get("type")
    title = block.get("title")
    out: list[str] = []
    if title:
        out.append(f"### {title}")
    if kind in {"paragraph", "markdown", "callout"} and block.get("text"):
        out.append(str(block["text"]))
    elif kind == "bullets":
        out += [f"- {item}" for item in block.get("items", [])]
    elif kind == "metric_grid":
        out += ["| Metric | Value |", "|---|---:|"]
        out += [f"| {item.get('label', '')} | {text(item.get('value'))} |" for item in block.get("items", [])]
    elif kind == "divider":
        out.append("---")
    return "\n\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--structured-report", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--modules")
    args = ap.parse_args()

    data = json.loads(Path(args.structured_report).read_text(encoding="utf-8"))
    selected = set(args.modules.split(",")) if args.modules else set(data.get("modules", {}))
    lines = [
        f"# {data.get('title') or data.get('symbol', '')}\n",
        f"- **Run ID:** `{data.get('run_id')}`",
        f"- **As-of:** `{data.get('as_of')}`",
        f"- **Evidence cutoff:** `{text(data.get('evidence_cutoff'))}`",
        f"- **Price timestamp:** `{text(data.get('price_timestamp'))}`",
        f"- **Research state:** `{data.get('research_state')}`",
    ]

    summary = data.get("summary", {})
    if summary:
        lines += ["\n## EXECUTIVE SUMMARY / 摘要"]
        for key, label in [
            ("headline", "Headline"),
            ("thesis", "Thesis"),
            ("variant_perception", "Variant perception"),
            ("primary_horizon", "Primary horizon"),
        ]:
            if summary.get(key):
                lines.append(f"**{label}:** {summary[key]}")
        if summary.get("key_risks"):
            lines += ["\n**Key risks**"] + [f"- {item}" for item in summary["key_risks"]]
        if summary.get("next_evidence"):
            lines += ["\n**Next evidence**"] + [f"- {item}" for item in summary["next_evidence"]]

    for name, module in data.get("modules", {}).items():
        if name not in selected:
            continue
        lines += [
            f"\n## {module.get('title', name)}",
            f"`status={module.get('status')}` · `confidence={text(module.get('confidence'))}` · `freshness={module.get('freshness_status')}`",
        ]
        for block in module.get("blocks", []):
            rendered = render_block(block)
            if rendered:
                lines.append(rendered)
        if module.get("judgments"):
            lines.append("### KEY JUDGMENTS / 關鍵判斷")
            for judgment in module["judgments"]:
                lines.append(f"**{judgment.get('label')}** — {judgment.get('conclusion')}")
                if judgment.get("why"):
                    lines.append(f"Why: {judgment['why']}")
                if judgment.get("invalidation"):
                    lines += ["Invalidation:"] + [f"- {item}" for item in judgment["invalidation"]]
        if module.get("knowledge_notes"):
            lines.append("### KNOWLEDGE NOTES / 判讀知識")
            for note in module["knowledge_notes"]:
                lines.append(f"**{note.get('title')}** — {note.get('explanation')}")
                if note.get("applied_to_current_report"):
                    lines.append(f"Applied here: {note['applied_to_current_report']}")
        if module.get("charts"):
            lines.append("### VISUAL INTERPRETATION / 圖表解讀")
            for chart in module["charts"]:
                interpretation = chart.get("interpretation", {})
                lines += [
                    f"**{chart.get('title')}**",
                    f"- WHAT: {interpretation.get('what', '')}",
                    f"- READ: {interpretation.get('read', '')}",
                    f"- WHY: {interpretation.get('why', '')}",
                    f"- LIMIT: {interpretation.get('limit', '')}",
                ]
        if module.get("missing_fields"):
            lines += ["### MISSING / 缺失"] + [f"- {item}" for item in module["missing_fields"]]
        if module.get("limitations"):
            lines += ["### LIMITATIONS / 限制"] + [f"- {item}" for item in module["limitations"]]

    if data.get("global_limitations"):
        lines += ["\n## GLOBAL LIMITATIONS / 全局限制"] + [f"- {item}" for item in data["global_limitations"]]

    Path(args.output).write_text("\n\n".join(lines).strip() + "\n", encoding="utf-8")
    print(json.dumps({"written": args.output, "modules": sorted(selected)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
