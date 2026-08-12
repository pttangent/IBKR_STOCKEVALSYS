#!/usr/bin/env python3
"""Finalize structured_report.json against deterministic artifacts before rendering.

This pass repairs mechanical contradictions that must never reach a reader:
- future evidence/price timestamps;
- stale prior-session intraday bars masquerading as the current price;
- deterministic fields simultaneously reported as observed and missing;
- tiny-sample/grid-cap Kelly diagnostics being converted into position guidance;
- technical price language contaminating the quarters-long scenario tree.

It does not invent research facts. When a contradiction cannot be repaired from
frozen artifacts, it downgrades/blocks the affected output and records why.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from stock_eval_scenarios import build_scenario_trees

NY = ZoneInfo("America/New_York")
LONG_TERM_TECHNICAL_TOKENS = (
    "現價", "價格", "股價", "支撐", "阻力", "壓力", "均線", "EMA", "SMA", "VWAP",
    "ORH", "ORL", "ATR", "突破", "跌破", "回踩", "反抽", "收復", "前高", "前低",
)


def load(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return {} if default is None else default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def _number(value: Any) -> float | None:
    try:
        x = float(value)
        return x if x == x and abs(x) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _parse_time(value: Any) -> dt.datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _append_unique(rows: list[str], value: str) -> None:
    if value not in rows:
        rows.append(value)


def _bar_rows(packet: dict) -> list[dict[str, Any]]:
    raw = packet.get("bars") or packet.get("results") or packet.get("data") or []
    rows: list[dict[str, Any]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        close = _number(row.get("close", row.get("c")))
        if close is None:
            continue
        rows.append({
            "date": str(row.get("date") or row.get("datetime") or row.get("time") or row.get("t") or ""),
            "open": _number(row.get("open", row.get("o"))),
            "high": _number(row.get("high", row.get("h"))),
            "low": _number(row.get("low", row.get("l"))),
            "close": close,
            "volume": _number(row.get("volume", row.get("v"))),
        })
    rows.sort(key=lambda row: row["date"])
    return rows


def _intraday_context(run: Path, as_of: str | None) -> dict[str, Any]:
    candidates: list[Path] = []
    for pattern in ("*intraday*1m*.json", "market_ibkr*1m*.json"):
        candidates.extend(sorted(run.glob(pattern)))
    seen: set[Path] = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        rows = _bar_rows(load(path))
        if not rows:
            continue
        latest_date = rows[-1]["date"][:10]
        latest_rows = [row for row in rows if row["date"][:10] == latest_date]
        same_session = bool(as_of and latest_date == str(as_of)[:10])
        context: dict[str, Any] = {
            "source_artifact": path.name,
            "latest_date": latest_date,
            "same_session": same_session,
        }
        # Crucial: previous-session intraday data must not become CURRENT.
        if same_session and latest_rows:
            context["current_price"] = latest_rows[-1]["close"]
            first15 = latest_rows[:15]
            highs = [row["high"] for row in first15 if row["high"] is not None]
            lows = [row["low"] for row in first15 if row["low"] is not None]
            if highs:
                context["orh"] = max(highs)
            if lows:
                context["orl"] = min(lows)
            pv = 0.0
            total_volume = 0.0
            for row in latest_rows:
                if row["volume"] is None or row["volume"] <= 0:
                    continue
                values = [x for x in (row["high"], row["low"], row["close"]) if x is not None]
                if not values:
                    continue
                pv += (sum(values) / len(values)) * row["volume"]
                total_volume += row["volume"]
            if total_volume > 0:
                context["vwap"] = pv / total_volume
        return context
    return {}


def _completed_price_timestamp(stock: dict, generated_at: dt.datetime) -> str | None:
    technical_date = str((stock.get("technical", {}) or {}).get("as_of") or "")[:10]
    try:
        day = dt.date.fromisoformat(technical_date)
    except ValueError:
        return None
    close_local = dt.datetime.combine(day, dt.time(16, 0), tzinfo=NY)
    candidate = close_local.astimezone(dt.timezone.utc)
    # If a current-day partial daily bar is ever supplied, never label a future close.
    candidate = min(candidate, generated_at)
    return candidate.astimezone(NY).isoformat()


def _sanitize_long_term_text(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    # Split into semantically usable clauses; discard clauses whose causal test is
    # explicitly technical price action. Dollar-denominated operating figures are
    # allowed when the clause itself is fundamental.
    chunks = re.split(r"(?<=[。；;])|，且|，或|；或|; or ", text)
    kept: list[str] = []
    for chunk in chunks:
        cleaned = chunk.strip(" ，；;。")
        if not cleaned:
            continue
        if any(token in cleaned for token in LONG_TERM_TECHNICAL_TOKENS):
            continue
        kept.append(cleaned)
    if not kept:
        return None
    return "；".join(kept) + "。"


def _sanitize_long_term_context(context: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    if not isinstance(context, dict):
        return {}, False
    changed = False
    out: dict[str, Any] = {}
    watch = []
    for item in context.get("watch", []) if isinstance(context.get("watch"), list) else []:
        if isinstance(item, str) and any(token in item for token in LONG_TERM_TECHNICAL_TOKENS):
            changed = True
            continue
        watch.append(item)
    if watch:
        out["watch"] = watch
    for key in ("strengthen_trigger", "mixed_trigger", "weaken_trigger", "invalidation_trigger"):
        original = context.get(key)
        cleaned = _sanitize_long_term_text(original)
        if original and cleaned != original:
            changed = True
        if cleaned:
            out[key] = cleaned
    return out, changed


def _reconcile_options(module: dict, gamma: dict) -> None:
    quality = gamma.get("data_quality", {}) or {}
    positive = _number(quality.get("rows_with_positive_open_interest")) or 0
    if positive <= 0:
        return
    missing = list(module.get("missing_fields", []) or [])
    if "positive_open_interest" in missing:
        missing.remove("positive_open_interest")
        module["missing_fields"] = missing
    resolutions = [row for row in (module.get("evidence_resolution", []) or []) if isinstance(row, dict)]
    found = False
    for row in resolutions:
        if row.get("field") == "positive_open_interest":
            row.update({
                "status": "FOUND",
                "attempts": [{"artifact": "options_gamma_structure.json", "result": f"{int(positive)} positive-OI rows"}],
                "next_action": "none; deterministic Gamma quality artifact confirms positive OI",
            })
            found = True
    if not found:
        resolutions.append({
            "field": "positive_open_interest",
            "status": "FOUND",
            "attempts": [{"artifact": "options_gamma_structure.json", "result": f"{int(positive)} positive-OI rows"}],
            "next_action": "none; deterministic Gamma quality artifact confirms positive OI",
        })
    module["evidence_resolution"] = resolutions


def _kelly_edge_eligibility(kelly: dict) -> tuple[bool, list[str]]:
    full = kelly.get("full_sample", {}) or {}
    formula = kelly.get("full_sample_formula", {}) or {}
    trades = int(full.get("trades") or 0)
    reasons: list[str] = []
    if trades < 10:
        reasons.append(f"只有 {trades} 筆已完成交易；少於 10 筆僅可展示診斷，不可轉成倉位比例")
    if bool(full.get("at_grid_cap")) and formula.get("raw_formula_kelly_fraction") is None:
        reasons.append("empirical Kelly 撞到診斷網格上限，且 p/b Kelly 因缺少勝負兩側樣本無法計算")
    return not reasons, reasons


def _block_tiny_sample_position_guidance(report: dict, stock: dict, manifest: dict) -> None:
    risk = report.get("modules", {}).get("risk", {})
    metrics = risk.get("metrics", {}) or {}
    kelly = metrics.get("kelly", {}) or stock.get("kelly", {}) or {}
    eligible, reasons = _kelly_edge_eligibility(kelly)
    kelly["edge_eligibility"] = {"eligible_for_position_guidance": eligible, "reasons": reasons}
    if eligible:
        return
    kelly["guidance_status"] = "unavailable_severe_sample_gap"
    kelly["guidance_variant"] = None
    kelly["guidance_kelly_scenarios"] = {}
    metrics["kelly"] = kelly

    old = metrics.get("position_guidance", {}) or {}
    entry = _number((stock.get("technical", {}) or {}).get("last_price"))
    stop = _number((metrics.get("position", {}) or {}).get("stop")) or _number(old.get("stop"))
    portfolio = _number(old.get("portfolio_value")) or 10000.0
    risk_budget_pct = _number(old.get("risk_budget_pct")) or 0.005
    concentration_cap_pct = _number(old.get("concentration_cap_pct")) or 0.05
    explicit_account = any(key in manifest for key in ("portfolio_value", "account_value", "user_portfolio_value"))
    source = old.get("portfolio_value_source") if explicit_account else "default_10000_simulation"
    label = "USER PORTFOLIO" if explicit_account else "$10,000 SIMULATION"

    if entry and stop and 0 < stop < entry:
        stop_distance = (entry - stop) / entry
        stop_cap = risk_budget_pct / stop_distance
        final = min(stop_cap, concentration_cap_pct)
        binding = "stop_risk_cap" if stop_cap <= concentration_cap_pct else "concentration_cap"
        guidance = {
            "status": "risk_only_fallback",
            "guidance_status": "risk_only_tiny_sample_kelly_blocked",
            "guidance_variant": "risk_only",
            "portfolio_value": portfolio,
            "portfolio_value_source": source,
            "simulation_label": label,
            "entry": entry,
            "stop": stop,
            "risk_budget_pct": risk_budget_pct,
            "risk_budget_dollars": portfolio * risk_budget_pct,
            "concentration_cap_pct": concentration_cap_pct,
            "stop_distance_pct": stop_distance,
            "stop_risk_cap_fraction": stop_cap,
            "current_realized_vol_20d_annualized": old.get("current_realized_vol_20d_annualized"),
            "daily_sigma": old.get("daily_sigma"),
            "variants": {},
            "guidance_fraction": final,
            "guidance_notional_dollars": portfolio * final,
            "guidance_exact_fractional_shares": portfolio * final / entry,
            "guidance_binding_constraint": binding,
            "interpretation": "Kelly 樣本嚴重不足；此處只保留結構止損/集中度風險上限，不是 Kelly 倉位。",
        }
    else:
        guidance = {
            "status": "unavailable",
            "guidance_status": "severe_data_gap",
            "guidance_variant": None,
            "portfolio_value": portfolio,
            "portfolio_value_source": source,
            "simulation_label": label,
            "entry": entry,
            "stop": stop,
            "current_realized_vol_20d_annualized": old.get("current_realized_vol_20d_annualized"),
            "daily_sigma": old.get("daily_sigma"),
            "variants": {},
            "reason": "Kelly 樣本嚴重不足，且沒有可辯護的結構止損，因此不輸出數值倉位。",
            "diagnostic_only": {"full_sample": kelly.get("full_sample"), "full_sample_formula": kelly.get("full_sample_formula")},
        }
    metrics["position_guidance"] = guidance
    risk["metrics"] = metrics
    risk["charts"] = [chart for chart in risk.get("charts", []) if chart.get("kind") != "kelly_position_ladder"]
    notes = risk.get("knowledge_notes", []) or []
    for note in notes:
        if note.get("title") == "全 Kelly、半 Kelly、四分之一 Kelly 三種方案":
            note["applied_to_current_report"] = "目前 Kelly 僅有極小樣本診斷，不輸出 full/half/quarter 的可執行倉位比例。"


def finalize(report: dict, run: Path) -> dict:
    out = copy.deepcopy(report)
    manifest = load(run / "report_manifest.json")
    stock = load(run / "stock_eval.json")
    gamma = load(run / "options_gamma_structure.json")
    research_content = load(run / "research_content.json")

    generated = _parse_time(out.get("generated_at")) or dt.datetime.now(dt.timezone.utc)
    limitations = list(out.get("global_limitations", []) or [])

    cutoff = _parse_time(out.get("evidence_cutoff"))
    if cutoff and cutoff > generated:
        declared = out.get("evidence_cutoff")
        out["evidence_cutoff"] = generated.isoformat()
        _append_unique(limitations, f"PIT 修正：宣告證據截止 {declared} 晚於報告生成時間，已截斷至 generated_at；不得把未來時點當成已凍結證據。")

    price_time = _parse_time(out.get("price_timestamp"))
    if price_time and price_time > generated:
        declared = out.get("price_timestamp")
        repaired = _completed_price_timestamp(stock, generated)
        out["price_timestamp"] = repaired
        _append_unique(limitations, f"PIT 修正：宣告價格時間戳 {declared} 晚於報告生成時間，已改用 deterministic price artifact 的最近可用時點 {repaired or '未知'}。")

    tech = (stock.get("technical", {}) or {})
    tech_module = out.get("modules", {}).get("technical", {})
    tech_as_of = str(tech.get("as_of") or "")[:10]
    if tech_as_of:
        tech_module["module_as_of"] = tech_as_of
        if str(out.get("as_of") or "")[:10] != tech_as_of:
            tech_module["freshness_status"] = "previous_completed_session"
            _append_unique(tech_module.setdefault("limitations", []), f"最新 deterministic 日線證據截至 {tech_as_of}，不是報告日期 {str(out.get('as_of') or '')[:10]} 的已完成收盤。")

    options_module = out.get("modules", {}).get("options", {})
    _reconcile_options(options_module, gamma)

    intraday = _intraday_context(run, out.get("as_of"))
    long_raw = ((research_content.get("modules", {}) or {}).get("scenarios", {}) or {}).get("long_term_context", {})
    long_clean, long_changed = _sanitize_long_term_context(long_raw)
    if long_changed:
        _append_unique(limitations, "長期情景已移除支撐/阻力/VWAP/均線等技術價格條件；季度以上論點只由營運、資本效率、競爭與估值證據驅動。")
    scenario_module = out.get("modules", {}).get("scenarios", {})
    if scenario_module:
        scenario_module["scenario_trees"] = build_scenario_trees(tech, {}, intraday, long_clean)
        scenario_module.setdefault("metrics", {})["intraday_context"] = intraday

    _block_tiny_sample_position_guidance(out, stock, manifest)
    out["global_limitations"] = limitations
    out.setdefault("package_hints", {})["finalization_status"] = "PIT_AND_CONTRADICTION_CHECKED"
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--output")
    args = ap.parse_args()
    source = Path(args.report)
    target = Path(args.output) if args.output else source
    data = json.loads(source.read_text(encoding="utf-8"))
    finalized = finalize(data, Path(args.run_dir))
    target.write_text(json.dumps(finalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"written": str(target), "status": finalized.get("package_hints", {}).get("finalization_status")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
