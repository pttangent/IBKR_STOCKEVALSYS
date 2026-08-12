#!/usr/bin/env python3
"""Render Markdown from canonical structured_report.json. No Markdown is parsed as input."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def text(value):
    return "—" if value is None or value == "" else str(value)


def pct(value, digits=2):
    try:
        return f"{float(value) * 100:.{digits}f}%"
    except (TypeError, ValueError):
        return "—"


def money(value, digits=0):
    try:
        return f"${float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def num(value, digits=2):
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return "—"


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


def kelly_markdown(module: dict) -> list[str]:
    metrics = module.get("metrics", {})
    guidance = metrics.get("position_guidance", {}) or {}
    kelly = metrics.get("kelly", {}) or {}
    if not guidance:
        return []
    formula = kelly.get("out_of_sample_formula", {}) if kelly.get("out_of_sample_formula", {}).get("trades") else kelly.get("full_sample_formula", {})
    empirical = kelly.get("conditional_oos_kelly_fraction") if kelly.get("conditional_oos_kelly_fraction") is not None else kelly.get("exploratory_full_sample_kelly_fraction")
    selected = kelly.get("selected_edge", {}) or {}
    overlay = guidance.get("risk_overlay_combination", {}) or {}
    setup = guidance.get("setup_match", {}) or {}
    sample = guidance.get("sample_confidence", {}) or {}
    lines = [
        "### KELLY CALCULATION / $10K POSITION GUIDE",
        f"- **Account:** {text(guidance.get('simulation_label'))}",
        f"- **Current RV20:** {pct(guidance.get('current_realized_vol_20d_annualized'))}",
        f"- **Daily sigma:** {pct(guidance.get('daily_sigma'), 3)}",
        f"- **Sample tier:** `{text(sample.get('tier'))}`",
        f"- **Setup match:** `{text(setup.get('status'))}`",
        f"- **Guidance:** `{text(guidance.get('guidance_variant'))}` = **{pct(guidance.get('guidance_fraction'))} NAV / {money(guidance.get('guidance_notional_dollars'))}**",
        "",
        "| Edge input | Value |",
        "|---|---:|",
        f"| p / win rate | {pct(formula.get('p_win_rate'))} |",
        f"| b / avg win ÷ avg loss | {num(formula.get('b_avg_win_over_avg_loss'), 3)} |",
        f"| formula Kelly | {pct(formula.get('raw_formula_kelly_fraction'))} |",
        f"| empirical log-growth Kelly | {pct(empirical)} |",
        f"| selected base edge | {pct(selected.get('fraction'))} |",
        f"| combined risk haircut | {pct(overlay.get('combined_haircut'))} |",
        "",
        "| Variant | Post-overlay | Final NAV | $10k notional | Shares | 1D 1σ NAV | 1D 1σ $ | Stop loss $ | Binding |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for label in ("full", "half", "quarter"):
        item = guidance.get("variants", {}).get(label)
        if not item:
            continue
        suffix = " **← GUIDE**" if label == guidance.get("guidance_variant") else ""
        lines.append(
            f"| {label.upper()}{suffix} | {pct(item.get('theoretical_post_overlay_fraction'))} | {pct(item.get('final_fraction'))} | "
            f"{money(item.get('notional_dollars'))} | {num(item.get('exact_fractional_shares'))} | "
            f"{pct(item.get('one_day_one_sigma_nav_fraction'), 3)} | {money(item.get('one_day_one_sigma_dollars'), 2)} | "
            f"{money(item.get('stop_loss_dollars'), 2)} | {text(item.get('binding_constraint'))} |"
        )
    if not guidance.get("variants"):
        lines.append(f"\n**Risk-only / unavailable:** {text(guidance.get('interpretation') or guidance.get('reason'))}")
    return lines


def _tree_lines(node: dict, prefix: str = "", is_last: bool = True, root: bool = False) -> list[str]:
    connector = "" if root else ("└─ " if is_last else "├─ ")
    refs = node.get("price_reference", {})
    ref_text = " · ".join(f"{key}={num(value)}" for key, value in refs.items())
    tier = node.get("sizing_tier")
    line = f"{prefix}{connector}{node.get('label')} — IF {node.get('trigger')}"
    if ref_text:
        line += f" [{ref_text}]"
    if tier:
        line += f" [SIZE={tier}]"
    lines = [line, f"{prefix}{'   ' if root or is_last else '│  '}THEN: {node.get('response')}"]
    child_prefix = prefix + ("   " if root or is_last else "│  ")
    children = node.get("children", [])
    for index, child in enumerate(children):
        lines.extend(_tree_lines(child, child_prefix, index == len(children) - 1, root=False))
    return lines


def scenario_markdown(tree: dict) -> list[str]:
    lines = [f"### {tree.get('title')}",
             f"`horizon={tree.get('horizon')}` · `evidence={tree.get('evidence_status')}`"]
    if tree.get("opening_range_minutes"):
        lines[-1] += f" · `opening_range={tree.get('opening_range_minutes')}m`"
    lines += ["", "```text"] + _tree_lines(tree.get("root", {}), root=True) + ["```"]
    return lines


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
        f"- **Default simulation account:** `${data.get('package_hints', {}).get('default_simulation_portfolio_value', 10000):,.0f}` when no user portfolio is supplied",
    ]

    summary = data.get("summary", {})
    if summary:
        lines += ["\n## EXECUTIVE SUMMARY / 摘要"]
        for key, label in [("headline", "Headline"), ("thesis", "Thesis"), ("variant_perception", "Variant perception"), ("primary_horizon", "Primary horizon")]:
            if summary.get(key):
                lines.append(f"**{label}:** {summary[key]}")
        if summary.get("key_risks"):
            lines += ["\n**Key risks**"] + [f"- {item}" for item in summary["key_risks"]]
        if summary.get("next_evidence"):
            lines += ["\n**Next evidence**"] + [f"- {item}" for item in summary["next_evidence"]]

    for name, module in data.get("modules", {}).items():
        if name not in selected:
            continue
        lines += [f"\n## {module.get('title', name)}",
                  f"`status={module.get('status')}` · `confidence={text(module.get('confidence'))}` · `freshness={module.get('freshness_status')}`"]
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
        if name == "risk":
            lines += kelly_markdown(module)
        if module.get("charts"):
            lines.append("### VISUAL INTERPRETATION / 圖表解讀")
            for chart in module["charts"]:
                interpretation = chart.get("interpretation", {})
                lines += [
                    f"**{chart.get('title')}**",
                    f"- WHAT: {interpretation.get('what', '')}",
                    f"  - OBSERVED: {interpretation.get('what_observed', '')}",
                    f"- READ: {interpretation.get('read', '')}",
                    f"  - RESULT: {interpretation.get('read_result', '')}",
                    f"- WHY: {interpretation.get('why', '')}",
                    f"  - NOW: {interpretation.get('why_now', '')}",
                    f"- LIMIT: {interpretation.get('limit', '')}",
                    f"  - EFFECT: {interpretation.get('limit_effect', '')}",
                ]
        for tree in module.get("scenario_trees", []):
            lines += scenario_markdown(tree)
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
