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


def _structured_bullets(title: str | None, value: str) -> list[str] | None:
    """Turn compact reader-facing compound prose into auditable bullet points."""
    if not isinstance(value, str):
        return None
    labels = ["看什麼：", "讀到什麼：", "為什麼重要：", "限制："]
    if all(label in value for label in labels):
        return [f"- **{label[:-1]}：** {value.split(label, 1)[1].split(labels[i + 1], 1)[0].strip()}" for i, label in enumerate(labels[:-1])] + [f"- **限制：** {value.split('限制：', 1)[1].strip()}"]
    scenarios = ["下行情景：", "基準情景：", "上行情景："]
    if title and "估值判斷" in title and all(label in value for label in scenarios):
        return [f"- **{label[:-1]}：** {value.split(label, 1)[1].split(scenarios[i + 1], 1)[0].strip()}" for i, label in enumerate(scenarios[:-1])] + [f"- **上行情景：** {value.split('上行情景：', 1)[1].strip()}"]
    return None


def render_block(block: dict) -> str:
    kind = block.get("type")
    title = block.get("title")
    out: list[str] = []
    if title:
        out.append(f"### {title}")
    if kind in {"paragraph", "markdown", "callout"} and block.get("text"):
        structured = _structured_bullets(title, str(block["text"]))
        out += structured if structured else [str(block["text"])]
    elif kind == "bullets":
        out += [f"- {item}" for item in block.get("items", [])]
    elif kind == "metric_grid":
        out += ["| 指標 | 數值 |", "|---|---:|"]
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
        "### Kelly 計算鏈 / 1 萬美元倉位參考",
        f"- **账户：** {text(guidance.get('simulation_label'))}",
        f"- **当前 20 日实现波动率：** {pct(guidance.get('current_realized_vol_20d_annualized'))}",
        f"- **日内 1σ：** {pct(guidance.get('daily_sigma'), 3)}",
        f"- **样本等级：** `{text(sample.get('tier'))}`",
        f"- **设置匹配：** `{text(setup.get('status'))}`",
        f"- **仓位建议：** `{text(guidance.get('guidance_variant'))}` = **{pct(guidance.get('guidance_fraction'))} NAV / {money(guidance.get('guidance_notional_dollars'))}**",
        "",
        "| 凯利输入 | 数值 |",
        "|---|---:|",
        f"| p / 勝率 | {pct(formula.get('p_win_rate'))} |",
        f"| b / 平均盈利 ÷ 平均亏损 | {num(formula.get('b_avg_win_over_avg_loss'), 3)} |",
        f"| 公式 Kelly | {pct(formula.get('raw_formula_kelly_fraction'))} |",
        f"| 经验对数增长 Kelly | {pct(empirical)} |",
        f"| 选用基础优势 | {pct(selected.get('fraction'))} |",
        f"| 综合风险折扣 | {pct(overlay.get('combined_haircut'))} |",
        "",
        "| 仓位方案 | 风险折扣后 | 最终 NAV | 1 万美元名义金额 | 股数 | 日内 1σ NAV | 日内 1σ 金额 | 止损金额 | 约束来源 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for label in ("full", "half", "quarter"):
        item = guidance.get("variants", {}).get(label)
        if not item:
            continue
        suffix = " **← 建议**" if label == guidance.get("guidance_variant") else ""
        lines.append(
            f"| {label.upper()}{suffix} | {pct(item.get('theoretical_post_overlay_fraction'))} | {pct(item.get('final_fraction'))} | "
            f"{money(item.get('notional_dollars'))} | {num(item.get('exact_fractional_shares'))} | "
            f"{pct(item.get('one_day_one_sigma_nav_fraction'), 3)} | {money(item.get('one_day_one_sigma_dollars'), 2)} | "
            f"{money(item.get('stop_loss_dollars'), 2)} | {text(item.get('binding_constraint'))} |"
        )
    if not guidance.get("variants"):
        lines.append(f"\n**仅风险约束 / 暂不可用：** {text(guidance.get('interpretation') or guidance.get('reason'))}")
    return lines


def _tree_lines(node: dict, prefix: str = "", is_last: bool = True, root: bool = False) -> list[str]:
    connector = "" if root else ("└─ " if is_last else "├─ ")
    refs = node.get("price_reference", {})
    ref_text = " · ".join(f"{key}={num(value)}" for key, value in refs.items())
    tier = node.get("sizing_tier")
    line = f"{prefix}{connector}{node.get('label')} — 如果 {node.get('trigger')}"
    if ref_text:
        line += f" [{ref_text}]"
    if tier:
        line += f" [仓位={tier}]"
    lines = [line, f"{prefix}{'   ' if root or is_last else '│  '}那么： {node.get('response')}"]
    child_prefix = prefix + ("   " if root or is_last else "│  ")
    children = node.get("children", [])
    for index, child in enumerate(children):
        lines.extend(_tree_lines(child, child_prefix, index == len(children) - 1, root=False))
    return lines


def scenario_markdown(tree: dict) -> list[str]:
    lines = [f"### {tree.get('title')}",
             f"`观察期限={tree.get('horizon')}` · `证据状态={tree.get('evidence_status')}`"]
    if tree.get("opening_range_minutes"):
        lines[-1] += f" · `开盘区间={tree.get('opening_range_minutes')} 分钟`"
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
        f"- **运行编号：** `{data.get('run_id')}`",
        f"- **截至时间：** `{data.get('as_of')}`",
        f"- **证据截止：** `{text(data.get('evidence_cutoff'))}`",
        f"- **价格时间戳：** `{text(data.get('price_timestamp'))}`",
        f"- **研究状态：** `{data.get('research_state')}`",
        f"- **默认模拟账户：** `${data.get('package_hints', {}).get('default_simulation_portfolio_value', 10000):,.0f}`（未提供用户组合时）",
    ]

    summary = data.get("summary", {})
    if summary:
        lines += ["\n## 执行摘要"]
        for key, label in [("headline", "摘要"), ("thesis", "核心主線"), ("variant_perception", "差異化判斷"), ("primary_horizon", "研究時間軸")]:
            if summary.get(key):
                lines.append(f"**{label}:** {summary[key]}")
        if summary.get("key_risks"):
            lines += ["\n**主要风险**"] + [f"- {item}" for item in summary["key_risks"]]
        if summary.get("next_evidence"):
            lines += ["\n**下一步证据**"] + [f"- {item}" for item in summary["next_evidence"]]

    for name, module in data.get("modules", {}).items():
        if name not in selected:
            continue
        lines += [f"\n## {module.get('title', name)}",
                  f"`状态={module.get('status')}` · `置信度={text(module.get('confidence'))}` · `新鲜度={module.get('freshness_status')}`"]
        for block in module.get("blocks", []):
            rendered = render_block(block)
            if rendered:
                lines.append(rendered)
        if module.get("judgments"):
            lines.append("### 关键判断")
            for judgment in module["judgments"]:
                lines.append(f"**{judgment.get('label')}** — {judgment.get('conclusion')}")
                if judgment.get("why"):
                    lines.append(f"依据：{judgment['why']}")
                if judgment.get("invalidation"):
                    lines += ["失效条件："] + [f"- {item}" for item in judgment["invalidation"]]
        if module.get("knowledge_notes"):
            lines.append("### 判读知识")
            for note in module["knowledge_notes"]:
                lines.append(f"**{note.get('title')}** — {note.get('explanation')}")
                if note.get("applied_to_current_report"):
                    lines.append(f"本报告应用：{note['applied_to_current_report']}")
        if name == "risk":
            lines += kelly_markdown(module)
        if module.get("charts"):
            lines.append("### 图表解读")
            for chart in module["charts"]:
                interpretation = chart.get("interpretation", {})
                lines += [
                    f"**{chart.get('title')}**",
                    f"- 看什么：{interpretation.get('what', '')}",
                    f"  - 观察到：{interpretation.get('what_observed', '')}",
                    f"- 当前解读：{interpretation.get('read', '')}",
                    f"  - 當前結果：{interpretation.get('read_result', '')}",
                    f"- 为什么重要：{interpretation.get('why', '')}",
                    f"  - 当前含义：{interpretation.get('why_now', '')}",
                    f"- 限制：{interpretation.get('limit', '')}",
                    f"  - 影响：{interpretation.get('limit_effect', '')}",
                ]
        for tree in module.get("scenario_trees", []):
            lines += scenario_markdown(tree)
        if module.get("missing_fields"):
            lines += ["### 缺失项 / 解决审计"] + [f"- {item}" for item in module["missing_fields"]]
        if module.get("limitations"):
            lines += ["### 限制"] + [f"- {item}" for item in module["limitations"]]

    if data.get("global_limitations"):
        lines += ["\n## 全局限制"] + [f"- {item}" for item in data["global_limitations"]]

    Path(args.output).write_text("\n\n".join(lines).strip() + "\n", encoding="utf-8")
    print(json.dumps({"written": args.output, "modules": sorted(selected)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
