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
    "overview": "研究結論",
    "fundamentals": "基本面",
    "valuation": "估值",
    "technical": "技術結構",
    "options": "期權與波動",
    "governance": "證據與審查",
    "risk": "風險與倉位",
    "scenarios": "情景推演",
    "evidence": "證據鏈",
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


def _fmt_num(value: Any, digits: int = 2) -> str:
    number = _number(value)
    return "—" if number is None else f"{number:,.{digits}f}"


def _fmt_pct(value: Any, digits: int = 2) -> str:
    number = _number(value)
    return "—" if number is None else f"{number * 100:.{digits}f}%"


def _fmt_money(value: Any, digits: int = 2) -> str:
    number = _number(value)
    return "—" if number is None else f"${number:,.{digits}f}"


def _binding_label(value: Any) -> str:
    labels = {
        "concentration_cap": "組合集中度上限",
        "stop_risk_cap": "止損風險上限",
        "kelly_after_risk_overlay": "風險調整後 Kelly",
        "portfolio_risk_budget": "組合風險預算",
        "unavailable": "不可用",
    }
    return labels.get(str(value), str(value) if value else "—")


def _variant_label(value: Any) -> str:
    labels = {"full": "全 Kelly", "half": "半 Kelly", "quarter": "四分之一 Kelly"}
    return labels.get(str(value), str(value) if value else "—")


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
                "id": "price_structure", "kind": "price_structure", "title": "價格結構",
                "source_artifact": source,
                "interpretation": {
                    "what": "近一年價格、EMA20、SMA50、SMA200 與成交量放在同一時間軸。",
                    "read": "按短、中、長週期分開判讀，不把單一均線標籤當成整體趨勢。",
                    "why": "它用來辨識趨勢、回撤與長短週期衝突，決定 tactical setup 是否與長期 thesis 同向。",
                    "limit": "均線與價格結構是描述性證據，不自行證明未來方向；成交量口徑跨 provider 也可能不同。"
                }
            })
        charts.append({
            "id": "technical_snapshot", "kind": "technical_snapshot", "title": "技術狀態",
            "source_artifact": "stock_eval.json",
            "interpretation": {
                "what": "把 20D、90D 報酬、RSI 與 20D 實現波動集中展示。",
                "read": "同時看動量與風險，而不是用單一 RSI 或單一均線貼標籤。",
                "why": "同一股票可以短期轉弱、長期仍強；多週期衝突本身就是 timing 資訊。",
                "limit": "不同指標量綱不同，圖用於狀態掃描，不應把柱高直接互相比較。"
            }
        })
        charts.append({
            "id": "level_map", "kind": "level_map", "title": "觀察價位",
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
                "id": "options_variance", "kind": "options_variance", "title": "期權波動代理",
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
                "id": "gamma_structure", "kind": "gamma_structure", "title": "Gross Gamma 結構",
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
            "id": "kelly_position_ladder", "kind": "kelly_position_ladder", "title": "Kelly 倉位階梯",
            "source_artifact": "stock_eval.json",
            "interpretation": {
                "what": "同時顯示全 Kelly、半 Kelly、四分之一 Kelly 在當前實現波動率與事件風險調整後的理論比例，以及 1 萬美元帳戶套用集中度與止損上限後的最終比例。",
                "read": "先比較三種方案的差距，再看每一檔是否被集中度或止損風險上限截斷；四分之一 Kelly 是保守參考，不等於全 Kelly。",
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
            "what_observed": f"現價 {_fmt_money(price)}；EMA20 {_fmt_money(ma.get('ema20'))}；SMA50 {_fmt_money(ma.get('sma50'))}；SMA200 {_fmt_money(ma.get('sma200'))}；20 日報酬 {_fmt_pct(tech.get('return_20d'))}；90 日報酬 {_fmt_pct(tech.get('return_90d'))}。",
            "read_result": f"目前價格位於 EMA20 {'下方' if price is not None and ma.get('ema20') and price < ma.get('ema20') else '上方'}、SMA50 {'下方' if price is not None and ma.get('sma50') and price < ma.get('sma50') else '上方'}；90 日報酬為 {_fmt_pct(tech.get('return_90d'))}。",
            "why_now": "這支持把當前狀態讀成回撤/收復測試，而不是已確認的長期反轉。",
            "limit_effect": "沒有同日資金流確認；圖表不能單獨驗證下一個方向。"
        })
    elif chart.get("id") == "technical_snapshot":
        interpretation.update({
            "what_observed": f"20 日報酬 {_fmt_pct(tech.get('return_20d'))}；90 日報酬 {_fmt_pct(tech.get('return_90d'))}；RSI14 {_fmt_num(momentum.get('rsi14'))}；20 日實現波動率 {_fmt_pct(tech.get('realized_vol_20d_annualized'))}。",
            "read_result": f"RSI14 {_fmt_num(momentum.get('rsi14'))}，動能偏強但未達極端；20 日實現波動率 {_fmt_pct(tech.get('realized_vol_20d_annualized'))}，風險仍高。動能與風險要分開讀。",
            "why_now": "當前波動率會進入 Kelly 風險折扣與 1 萬美元模擬的一個標準差曝險表。",
            "limit_effect": "歷史指標不能建立當前訂單流方向，也不能單獨建立已驗證的交易優勢。"
        })
    elif chart.get("id") == "level_map":
        supports = sorted([x for x in sr.get("supports", []) if isinstance(x, (int, float)) and isinstance(price, (int, float)) and x < price], reverse=True)
        resistances = sorted([x for x in sr.get("resistances", []) if isinstance(x, (int, float)) and isinstance(price, (int, float)) and x > price])
        read_result = (f"現價 {_fmt_money(price)} 位於最近支撐 {_fmt_money(supports[0])} 與最近阻力 {_fmt_money(resistances[0])} 之間。"
                       if supports and resistances else f"現價 {_fmt_money(price)}；上下雙向結構尚未完整建立。")
        interpretation.update({
            "what_observed": f"現價 {_fmt_money(price)}；最近支撐：{', '.join(_fmt_money(x) for x in supports[:3]) or '—'}；最近阻力：{', '.join(_fmt_money(x) for x in resistances[:3]) or '—'}。",
            "read_result": read_result,
            "why_now": "這些是情景樹與結構止損討論使用的條件邊界。",
            "limit_effect": "沒有同日資金流時，只能把價位當候選反應區，不能寫成已確認支撐或阻力。"
        })
    elif chart.get("id") == "options_variance":
        rows = options.get("expiry_features", [])
        front = rows[0] if rows else {}
        back = rows[-1] if rows else {}
        ratio = (back.get("total_variance") / front.get("total_variance")) if front.get("total_variance") and back.get("total_variance") else None
        interpretation.update({
            "what_observed": f"前段到期日 {front.get('expiry') or '—'} 的總方差 {_fmt_num(front.get('total_variance'), 4)}；後段到期日 {back.get('expiry') or '—'} 的總方差 {_fmt_num(back.get('total_variance'), 4)}；可用報價列 {_fmt_num(front.get('quote_rows'), 0)}。",
            "read_result": f"後段/前段總方差比約 {_fmt_num(ratio, 2)}；這更接近歷史/收盤價代理，不是可執行的完整波動率曲面。",
            "why_now": "這些資料可以用來設定波動率折扣，但不能提供期權方向優勢。",
            "limit_effect": "缺少可辯護的可執行報價曲面，因此不能提出精確概率或成交價格判斷。"
        })
    elif chart.get("id") == "gamma_structure":
        quality = gamma.get("data_quality", {})
        status = gamma.get("gamma_status") or gamma.get("status")
        interpretation.update({
            "what_observed": f"狀態：{status}；合資格合約列 {quality.get('eligible_rows', '—')}；正 OI 列 {quality.get('rows_with_positive_open_interest', '—')}；IV 來源 {quality.get('iv_source_counts', '—')}。",
            "read_result": f"當前結果為 {status}；只有正 OI 與可辯護 IV 同時成立，才可驗證 Gamma 集中區。",
            "why_now": "目前正確判斷是抑制 Gamma wall，而不是把零值畫成牆，或推斷交易商方向。",
            "limit_effect": "未帶方向的 gross Gamma 不能建立交易商多空方向，也不能建立 Gamma flip。"
        })
    elif chart.get("id") == "kelly_position_ladder":
        variants = position_guidance.get("variants", {})
        compact = "；".join(
            f"{label}：最終比例 {_fmt_pct(item.get('final_fraction'))}、名義金額 {_fmt_money(item.get('notional_dollars'))}、"
            f"可買股數 {_fmt_num(item.get('exact_fractional_shares'))}、約束 {_binding_label(item.get('binding_constraint'))}"
            for label, item in variants.items()
        ) or "無可用方案"
        interpretation.update({
            "what_observed": f"模擬帳戶 {_fmt_money(position_guidance.get('portfolio_value'), 0)}；當前 20 日實現波動率 {_fmt_pct(position_guidance.get('current_realized_vol_20d_annualized'))}；日內一個標準差 {_fmt_pct(position_guidance.get('daily_sigma'))}；方案 {compact}。",
            "read_result": f"目前採用 {_variant_label(position_guidance.get('guidance_variant'))}，倉位比例 {_fmt_pct(position_guidance.get('guidance_fraction'))}，名義金額 {_fmt_money(position_guidance.get('guidance_notional_dollars'))}；主要約束為 {_binding_label(position_guidance.get('guidance_binding_constraint'))}。",
            "why_now": "這把抽象的 Kelly 比例轉換成當前實現波動率下，1 萬美元模擬帳戶真正承擔的風險。",
            "limit_effect": f"倉位狀態為 {position_guidance.get('guidance_status')}；設定與樣本不足仍然存在，因此不能把診斷值稱為已驗證。"
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
        "title": content.get("title") or f"{symbol} 證據鏈研究報告",
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
                {"title": "Kelly 是優勢，RV 是當前風險",
                 "explanation": "Kelly 由設定結果估算（經驗對數增長與 p/b 診斷）。當前實現波動率、期權/事件風險及組合上限會縮小曝險，但不會創造方向優勢。",
                 "applied_to_current_report": f"模擬帳戶={position_guidance.get('simulation_label', '$10,000 模擬')}; 倉位狀態={position_guidance.get('guidance_status')}; 當前 RV={_fmt_pct(position_guidance.get('current_realized_vol_20d_annualized'))}."},
                {"title": "全 Kelly、半 Kelly、四分之一 Kelly 三種方案",
                 "explanation": "全 Kelly 對估計誤差最敏感；半 Kelly 與四分之一 Kelly 是穩健性方案。報告同時展示三者，除非明確的已驗證策略治理另有選擇，否則以四分之一 Kelly 作為保守參考。",
                 "applied_to_current_report": f"目前方案={position_guidance.get('guidance_variant')}; 比例={_fmt_pct(position_guidance.get('guidance_fraction'))}; 名義金額={_fmt_money(position_guidance.get('guidance_notional_dollars'))}."},
            ]
        elif name == "scenarios":
            module["metrics"] = {"daily_context": daily_context, "intraday_context": intraday_context,
                                 "default_simulation_portfolio_value": 10000.0}
            module["scenario_trees"] = scenario_trees
            module["knowledge_notes"] = [
                {"title": "三個期限，三個問題",
                 "explanation": "日內看開盤後的價格事件如何被接受或拒絕；短期看結構是修復、消化還是破位；長期看商業經濟性與估值是強化還是否定主線。",
                 "applied_to_current_report": f"日內證據狀態={scenario_trees[0].get('evidence_status') if scenario_trees else '未知'}."}
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
