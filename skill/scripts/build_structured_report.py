#!/usr/bin/env python3
"""Build the canonical structured report from deterministic artifacts plus structured research content.

Production report renderers consume only the resulting JSON. Markdown is never
used as a semantic input. `research_content.json` is intentionally structured so
LLM/research synthesis is explicit and auditable before presentation.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from stock_eval_position import kelly_position_guidance
from stock_eval_scenarios import build_scenario_trees

MODULE_TITLES = {
    "overview": "RESEARCH POSTURE / 研究結論",
    "fundamentals": "FUNDAMENTALS / 基本面",
    "valuation": "VALUATION / 估值",
    "technical": "TECHNICAL / 技術結構",
    "options": "OPTIONS / 期權與波動",
    "governance": "GOVERNANCE / 證據與審查",
    "risk": "RISK / 風險與倉位",
    "scenarios": "SCENARIOS / 情景",
    "evidence": "EVIDENCE / 證據鏈",
}


def load(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return {} if default is None else default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def merge(a: dict, b: dict) -> dict:
    out = copy.deepcopy(a)
    for key, value in b.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _number(value: Any) -> float | None:
    try:
        x = float(value)
        return x if x == x and abs(x) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _bar_rows(packet: dict) -> list[dict]:
    raw = packet.get("bars") or packet.get("results") or packet.get("data") or []
    rows = []
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


def _daily_context(run: Path) -> dict[str, Any]:
    candidates = [run / "market_ibkr_daily_full.json", run / "market_massive_daily.json"]
    for path in candidates:
        if not path.exists():
            continue
        rows = _bar_rows(load(path))
        if rows:
            return {
                "source_artifact": path.name,
                "latest_close": rows[-1]["close"],
                "latest_date": rows[-1]["date"][:10],
                "prior_close": rows[-2]["close"] if len(rows) >= 2 else None,
                "prior_date": rows[-2]["date"][:10] if len(rows) >= 2 else None,
            }
    return {}


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
            "current_price": latest_rows[-1]["close"] if latest_rows else rows[-1]["close"],
            "same_session": same_session,
        }
        if same_session and latest_rows:
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
                typical_values = [x for x in (row["high"], row["low"], row["close"]) if x is not None]
                if not typical_values:
                    continue
                typical = sum(typical_values) / len(typical_values)
                pv += typical * row["volume"]
                total_volume += row["volume"]
            if total_volume > 0:
                context["vwap"] = pv / total_volume
        return context
    return {}


def _backfill_position_guidance(stock: dict) -> dict:
    existing = stock.get("position_guidance")
    if isinstance(existing, dict) and existing:
        return existing
    kelly = stock.get("kelly", {}) or {}
    tech = stock.get("technical", {}) or {}
    entry = _number(tech.get("last_price"))
    if entry is None:
        return {}
    position = stock.get("position", {}) or {}
    stop = _number(position.get("stop"))
    return kelly_position_guidance(
        kelly,
        entry,
        portfolio_value=10000.0,
        stop=stop,
        risk_budget_pct=_number(position.get("risk_budget_pct")) or 0.005,
        concentration_cap_pct=_number(position.get("concentration_cap_pct")) or 0.05,
        portfolio_value_source="default_10000_simulation",
    )


def default_charts(name: str, run: Path, stock: dict, options: dict, gamma: dict,
                   position_guidance: dict | None = None) -> list[dict]:
    charts: list[dict] = []
    tech = stock.get("technical", {})
    position_guidance = position_guidance or {}
    if name == "technical":
        if (run / "market_ibkr_daily_full.json").exists() or (run / "market_massive_daily.json").exists():
            source = "market_ibkr_daily_full.json" if (run / "market_ibkr_daily_full.json").exists() else "market_massive_daily.json"
            charts.append({
                "id": "price_structure", "kind": "price_structure", "title": "PRICE STRUCTURE / 價格結構",
                "source_artifact": source,
                "interpretation": {
                    "what": "近一年價格、EMA20、SMA50、SMA200 與成交量放在同一時間軸。",
                    "read": "按短、中、長週期分開判讀，不把單一均線標籤當成整體趨勢。",
                    "why": "它用來辨識趨勢、回撤與長短週期衝突，決定 tactical setup 是否與長期 thesis 同向。",
                    "limit": "均線與價格結構是描述性證據，不自行證明未來方向；成交量口徑跨 provider 也可能不同。"
                }
            })
        charts.append({
            "id": "technical_snapshot", "kind": "technical_snapshot", "title": "TECHNICAL STATE / 技術狀態",
            "source_artifact": "stock_eval.json",
            "interpretation": {
                "what": "把 20D、90D 報酬、RSI 與 20D 實現波動集中展示。",
                "read": "同時看動量與風險，而不是用單一 RSI 或單一均線貼標籤。",
                "why": "同一股票可以短期轉弱、長期仍強；多週期衝突本身就是 timing 資訊。",
                "limit": "不同指標量綱不同，圖用於狀態掃描，不應把柱高直接互相比較。"
            }
        })
        charts.append({
            "id": "level_map", "kind": "level_map", "title": "OBSERVED LEVELS / 結構價位",
            "source_artifact": "stock_eval.json",
            "interpretation": {
                "what": "顯示 deterministic engine 找到的最近支撐、阻力與當前價格。",
                "read": "把價位視為候選反應區，而不是精確單點。",
                "why": "可用於設計 entry / invalidation / stop 的結構基準。",
                "limit": "swing/Fibonacci 等是啟發式結構；沒有當日 order flow 時不能稱為已確認支撐或壓力。"
            }
        })
    if name == "options":
        if options:
            charts.append({
                "id": "options_variance", "kind": "options_variance", "title": "OPTION VARIANCE PROXY / 期權波動代理",
                "source_artifact": "options_features.json",
                "interpretation": {
                    "what": "比較可用到期日的 ATM straddle/IV/總變異診斷。",
                    "read": "重點是前後到期日風險是否集中，而不是把少量合約稱為完整 volatility surface。",
                    "why": "事件風險前置時，短期期權通常承擔更高的時間密度風險，可影響 position haircut。",
                    "limit": "歷史 last 或缺 bid/ask 時只是 proxy；不能視為可成交即時 IV。"
                }
            })
        if gamma:
            status = gamma.get("gamma_status") or gamma.get("status")
            charts.append({
                "id": "gamma_structure", "kind": "gamma_structure", "title": "GROSS GAMMA STRUCTURE / Gamma 結構",
                "source_artifact": "options_gamma_structure.json",
                "interpretation": {
                    "what": "以可用 IV 與 OI 計算的 unsigned gross gamma concentration。",
                    "read": f"目前 Gamma 狀態：{status or 'unknown'}。只有 OI/IV 品質足夠且有經濟量級時才解讀 concentration。",
                    "why": "高 gross gamma 區可能改變 hedging sensitivity，但只有在 dealer sign 可辯護時才能談正/負 dealer GEX。",
                    "limit": "OI 不告訴 dealer/customer side；零或不可信 OI 必須 suppress wall，不能硬選最大值。"
                }
            })
    if name == "risk" and position_guidance.get("variants"):
        charts.append({
            "id": "kelly_position_ladder", "kind": "kelly_position_ladder", "title": "KELLY POSITION LADDER / Kelly 倉位階梯",
            "source_artifact": "stock_eval.json",
            "interpretation": {
                "what": "同時顯示 full / half / quarter Kelly 在 current-RV / option-event overlay 後的理論比例，以及 $10k 帳戶套用 concentration/stop caps 後的最終比例。",
                "read": "先看 full/half/quarter 的差距，再看每一檔是否被 concentration 或 stop-risk cap 截斷；quarter 是保守指引，不等於 full Kelly。",
                "why": "Kelly 描述 edge 對資本比例的含義；current RV 與 portfolio caps 決定今天實際能承受多少，而不是重新創造 directional edge。",
                "limit": "若 setup 只是不完全匹配或樣本偏少，這仍是 proxy/conditional guidance；只有嚴重缺失才不給數值。"
            }
        })
    for chart in charts:
        chart["interpretation"] = _enrich_interpretation(chart, tech, options, gamma, position_guidance)
    return charts


def _enrich_interpretation(chart: dict, tech: dict, options: dict, gamma: dict,
                           position_guidance: dict | None = None) -> dict:
    interpretation = copy.deepcopy(chart.get("interpretation", {}))
    position_guidance = position_guidance or {}
    ma = tech.get("ma", {})
    momentum = tech.get("momentum", {})
    sr = tech.get("support_resistance", {})
    price = tech.get("last_price")
    if chart.get("id") == "price_structure":
        interpretation.update({
            "what_observed": f"Price={price}; EMA20={ma.get('ema20')}; SMA50={ma.get('sma50')}; SMA200={ma.get('sma200')}; 20D={tech.get('return_20d')}; 90D={tech.get('return_90d')}.",
            "read_result": f"Observed short/medium structure is {'below' if price is not None and ma.get('ema20') and price < ma.get('ema20') else 'above'} EMA20 and {'below' if price is not None and ma.get('sma50') and price < ma.get('sma50') else 'above'} SMA50, while 90D return is {tech.get('return_90d')}.",
            "why_now": "Current evidence supports a pullback/reclaim test, not an already-confirmed long-term reversal.",
            "limit_effect": "No same-session flow confirmation; the chart cannot validate the next directional move."
        })
    elif chart.get("id") == "technical_snapshot":
        interpretation.update({
            "what_observed": f"20D={tech.get('return_20d')}; 90D={tech.get('return_90d')}; RSI14={momentum.get('rsi14')}; RV20={tech.get('realized_vol_20d_annualized')}.",
            "read_result": f"RSI14={momentum.get('rsi14')}; current RV20={tech.get('realized_vol_20d_annualized')}. Read momentum and risk separately.",
            "why_now": "Current RV is carried into the Kelly risk overlay and $10k one-sigma exposure table.",
            "limit_effect": "Historical indicators do not establish current order-flow direction or a validated trade edge."
        })
    elif chart.get("id") == "level_map":
        supports = sorted([x for x in sr.get("supports", []) if isinstance(x, (int, float)) and isinstance(price, (int, float)) and x < price], reverse=True)
        resistances = sorted([x for x in sr.get("resistances", []) if isinstance(x, (int, float)) and isinstance(price, (int, float)) and x > price])
        read_result = (f"Current price {price} is between nearest support {supports[0]} and resistance {resistances[0]}."
                       if supports and resistances else f"Current price {price}; a two-sided bracket is not fully established.")
        interpretation.update({
            "what_observed": f"Current={price}; supports={supports[:3]}; resistances={resistances[:3]}.",
            "read_result": read_result,
            "why_now": "These are the conditional boundaries used by the scenario tree and any structural stop discussion.",
            "limit_effect": "Without same-session flow, treat levels as candidate reaction zones rather than confirmed support/resistance."
        })
    elif chart.get("id") == "options_variance":
        rows = options.get("expiry_features", [])
        front = rows[0] if rows else {}
        back = rows[-1] if rows else {}
        ratio = (back.get("total_variance") / front.get("total_variance")) if front.get("total_variance") and back.get("total_variance") else None
        interpretation.update({
            "what_observed": f"Front={front.get('expiry')} variance={front.get('total_variance')}; back={back.get('expiry')} variance={back.get('total_variance')}; quote_rows={front.get('quote_rows')}.",
            "read_result": f"Observed back/front total-variance ratio={ratio}; this may be a historical/last-price proxy rather than an executable surface.",
            "why_now": "The data can inform a volatility haircut, but do not provide directional option alpha.",
            "limit_effect": "No defensible executable quote surface means no precise probability or trade-price claim."
        })
    elif chart.get("id") == "gamma_structure":
        quality = gamma.get("data_quality", {})
        status = gamma.get("gamma_status") or gamma.get("status")
        interpretation.update({
            "what_observed": f"Status={status}; eligible_rows={quality.get('eligible_rows')}; positive_OI_rows={quality.get('rows_with_positive_open_interest')}; iv_sources={quality.get('iv_source_counts')}.",
            "read_result": f"Current result={status}; validated concentrations require positive OI and defensible IV together.",
            "why_now": "The correct current judgment may be Gamma-wall suppression rather than a zero-valued wall or dealer-flow inference.",
            "limit_effect": "Unsigned gross Gamma cannot establish dealer sign or a Gamma flip."
        })
    elif chart.get("id") == "kelly_position_ladder":
        variants = position_guidance.get("variants", {})
        compact = {label: {"final_fraction": item.get("final_fraction"), "notional": item.get("notional_dollars"),
                           "shares": item.get("exact_fractional_shares"), "binding": item.get("binding_constraint")}
                   for label, item in variants.items()}
        interpretation.update({
            "what_observed": f"Account={position_guidance.get('portfolio_value')}; current_RV={position_guidance.get('current_realized_vol_20d_annualized')}; daily_sigma={position_guidance.get('daily_sigma')}; variants={compact}.",
            "read_result": f"Guidance={position_guidance.get('guidance_variant')} at fraction={position_guidance.get('guidance_fraction')} / notional=${position_guidance.get('guidance_notional_dollars')}; binding={position_guidance.get('guidance_binding_constraint')}.",
            "why_now": "This converts an abstract Kelly fraction into the actual $10k risk footprint under current realized volatility.",
            "limit_effect": f"Guidance status={position_guidance.get('guidance_status')}; setup/sample weakness remains visible and prevents a diagnostic from being called validated."
        })
    return interpretation


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--research-content", help="structured analyst synthesis JSON; optional for diagnostic scaffold")
    ap.add_argument("--out", default="structured_report.json")
    args = ap.parse_args()
    run = Path(args.run_dir)

    manifest = load(run / "report_manifest.json")
    evidence = load(run / "evidence.json")
    stock = load(run / "stock_eval.json")
    valuation = load(run / "valuation_snapshot.json")
    options = load(run / "options_features.json")
    gamma = load(run / "options_gamma_structure.json")
    evidence_resolution = load(run / "evidence_resolution.json")
    content = load(Path(args.research_content), {}) if args.research_content else {}

    run_id = manifest.get("run_id") or evidence.get("run_id") or run.name
    symbol = manifest.get("symbol") or evidence.get("symbol") or stock.get("symbol") or run_id.split("_")[0]
    as_of = manifest.get("as_of") or evidence.get("as_of") or stock.get("as_of")
    position_guidance = _backfill_position_guidance(stock)
    daily_context = _daily_context(run)
    intraday_context = _intraday_context(run, as_of)

    report = {
        "schema_version": "2.1",
        "run_id": run_id,
        "symbol": symbol,
        "title": content.get("title") or f"{symbol} STOCK EVALUATION / 證據鏈研究報告",
        "as_of": as_of,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "evidence_cutoff": manifest.get("evidence_cutoff") or evidence.get("evidence_cutoff"),
        "price_timestamp": manifest.get("price_timestamp"),
        "research_state": manifest.get("research_state") or content.get("research_state") or "NEEDS_EVIDENCE",
        "summary": content.get("summary", {}),
        "global_limitations": manifest.get("global_limitations", []) + content.get("global_limitations", []),
        "evidence_resolution": evidence_resolution,
        "modules": {},
        "package_hints": {
            "evidence_packet": "evidence.json",
            "reader_outputs": ["markdown", "html"],
            "package_type": "evidence_chain_report_package",
            "default_simulation_portfolio_value": 10000.0,
        }
    }

    manifest_modules = manifest.get("modules", {})
    content_modules = content.get("modules", {})
    long_term_context = content_modules.get("scenarios", {}).get("long_term_context", {}) if isinstance(content_modules.get("scenarios", {}), dict) else {}
    scenario_trees = build_scenario_trees(stock.get("technical", {}), daily_context, intraday_context, long_term_context)

    for name in MODULE_TITLES:
        base = copy.deepcopy(manifest_modules.get(name, {}))
        resolution_items = (evidence_resolution.get("requirements", []) if isinstance(evidence_resolution, dict) else []) if name == "fundamentals" else []
        resolution_by_field = {item.get("field"): item for item in resolution_items if isinstance(item, dict)}
        base_missing = base.get("missing_fields", [])
        effective_missing = [field for field in base_missing if resolution_by_field.get(field, {}).get("status") != "FOUND"]
        module = {
            "title": MODULE_TITLES[name],
            "status": base.get("status", "not_run"),
            "confidence": base.get("confidence"),
            "module_as_of": base.get("module_as_of"),
            "freshness_status": base.get("freshness_status", "unknown"),
            "source_artifacts": base.get("source_artifacts", []),
            "evidence_ids": base.get("evidence_ids", []),
            "missing_fields": effective_missing,
            "evidence_resolution": base.get("evidence_resolution", []) or resolution_items,
            "metrics": {},
            "blocks": [],
            "judgments": [],
            "knowledge_notes": [],
            "charts": [],
            "tables": [],
            "scenario_trees": [],
            "limitations": []
        }
        if name == "technical":
            module["metrics"] = stock.get("technical", {})
        elif name == "valuation":
            module["metrics"] = valuation
        elif name == "options":
            module["metrics"] = {"features": options, "gamma": gamma}
        elif name == "risk":
            module["metrics"] = {
                "kelly": stock.get("kelly", {}),
                "position_guidance": position_guidance,
                "position": stock.get("position", {}),
                "volatility_context": stock.get("volatility_context", {}),
            }
            module["knowledge_notes"] = [
                {"title": "KELLY = EDGE, RV = CURRENT RISK",
                 "explanation": "Kelly is estimated from setup outcomes (empirical log-growth plus p/b diagnostic). Current realized volatility, option/event risk and portfolio caps shrink the exposure; they do not create directional edge.",
                 "applied_to_current_report": f"Default account={position_guidance.get('simulation_label', '$10,000 SIMULATION')}; guidance status={position_guidance.get('guidance_status')}; current RV={position_guidance.get('current_realized_vol_20d_annualized')}."},
                {"title": "FULL / HALF / QUARTER",
                 "explanation": "Full Kelly is the most estimation-sensitive theoretical fraction. Half and quarter are robustness variants. The report shows all three and uses quarter as the conservative guidance variant unless explicit validated strategy governance selects otherwise.",
                 "applied_to_current_report": f"Current guidance variant={position_guidance.get('guidance_variant')}; fraction={position_guidance.get('guidance_fraction')}; notional=${position_guidance.get('guidance_notional_dollars')}."},
            ]
        elif name == "scenarios":
            module["metrics"] = {"daily_context": daily_context, "intraday_context": intraday_context,
                                 "default_simulation_portfolio_value": 10000.0}
            module["scenario_trees"] = scenario_trees
            module["knowledge_notes"] = [
                {"title": "THREE HORIZONS, THREE QUESTIONS",
                 "explanation": "Intraday asks how the opening auction is accepted or rejected; short term asks whether structure repairs, digests or breaks; long term asks whether business economics and valuation strengthen or invalidate the thesis.",
                 "applied_to_current_report": f"Intraday evidence status={scenario_trees[0].get('evidence_status') if scenario_trees else 'unknown'}."}
            ]

        module["charts"] = default_charts(name, run, stock, options, gamma, position_guidance)
        module = merge(module, content_modules.get(name, {}))
        for chart in module.get("charts", []):
            chart["interpretation"] = _enrich_interpretation(chart, stock.get("technical", {}), options, gamma, position_guidance)
        report["modules"][name] = module

    out = run / args.out if not Path(args.out).is_absolute() else Path(args.out)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"written": str(out), "run_id": run_id, "modules": len(report["modules"]),
                      "default_simulation_portfolio_value": 10000.0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
