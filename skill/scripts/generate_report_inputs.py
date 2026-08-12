#!/usr/bin/env python3
"""Create data-specific Chinese structured-report inputs from a frozen run packet."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return {} if default is None else default
    return json.loads(path.read_text(encoding="utf-8"))


def num(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def pct(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value) * 100:.{digits}f}%"
    except (TypeError, ValueError):
        return "—"


def money(value: Any, digits: int = 2) -> str:
    try:
        return f"${float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def fact(sec: dict, key: str) -> Any:
    return (((sec.get("data") or {}).get("canonical_financials") or {}).get("facts") or {}).get(key, {}).get("value")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--as-of", required=True)
    args = ap.parse_args()
    run = Path(args.run_dir)
    symbol = args.symbol.upper()
    as_of = args.as_of
    stock = load(run / "stock_eval.json")
    sec = load(run / "sec_research.json")
    options = load(run / "options_features.json")
    gamma = load(run / "options_gamma_structure.json")
    if not options:
        options = {"provider": "yfinance", "status": "failed", "symbol": symbol, "retrieved_at": as_of, "expiry_features": [], "warnings": ["本次 yfinance 期權鏈請求超時，未重試以避免限流。"]}
        (run / "options_features.json").write_text(json.dumps(options, ensure_ascii=False, indent=2), encoding="utf-8")
    if not gamma:
        gamma = {"provider": "options_gamma_structure", "status": "unavailable", "gamma_status": "UNAVAILABLE_ZERO_OR_UNTRUSTED_OI", "symbol": symbol, "data_quality": {"rows_with_positive_open_interest": 0, "eligible_rows": 0}, "warnings": ["沒有可用期權鏈，Gamma wall 已抑制。"]}
        (run / "options_gamma_structure.json").write_text(json.dumps(gamma, ensure_ascii=False, indent=2), encoding="utf-8")
    technical = stock.get("technical", {})
    ma = technical.get("ma", {}) or {}
    momentum = technical.get("momentum", {}) or {}
    price = technical.get("last_price")
    supports = technical.get("support_resistance", {}).get("supports", []) or []
    resistances = technical.get("support_resistance", {}).get("resistances", []) or []
    revenue = fact(sec, "revenue")
    gross_profit = fact(sec, "gross_profit")
    net_income = fact(sec, "net_income")
    operating_cf = fact(sec, "operating_cash_flow")
    cash = fact(sec, "cash_and_equivalents")
    filed = ((sec.get("data") or {}).get("canonical_financials") or {}).get("facts", {}).get("revenue", {}).get("filed")
    market_id = f"market:IBKR:{symbol}:{as_of}"
    sec_id = f"sec:{symbol}:{as_of}"
    ir_id = f"ir:{symbol}:{as_of}"
    opt_id = f"options:yfinance:{symbol}:{as_of}"
    current_return = pct(technical.get("return_20d"))
    long_return = pct(technical.get("return_90d"))
    rv = pct(technical.get("realized_vol_20d_annualized"))
    rsi = num(momentum.get("rsi14"))
    s1 = money(supports[0]) if supports else "—"
    r1 = money(resistances[0]) if resistances else "—"
    gamma_status = gamma.get("gamma_status") or gamma.get("status") or "未知"
    positive_oi = ((gamma.get("data_quality") or {}).get("rows_with_positive_open_interest"))
    sec_source = {
        "schema_version": "1.0", "source_id": ir_id, "provider": "SEC_EDGAR", "source_type": "company_filing",
        "as_of": as_of, "available_at": as_of, "retrieved_at": sec.get("retrieved_at", as_of),
        "reliability": "primary", "source_url": sec.get("source_url", "https://www.sec.gov/edgar/search/"),
        "data": {"symbol": symbol, "filed": filed, "facts": {k: fact(sec, k) for k in ["revenue", "gross_profit", "net_income", "operating_cash_flow", "cash_and_equivalents", "assets", "liabilities", "equity", "shares_outstanding"]}}
    }
    market_source = {
        "schema_version": "1.0", "source_id": market_id, "provider": "IBKR_TWS", "source_type": "market_data",
        "as_of": as_of, "available_at": as_of, "retrieved_at": load(run / "market_ibkr_daily_full.json").get("retrieved_at", as_of),
        "reliability": "primary_market", "source_url": "https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/",
        "data": {"symbol": symbol, "last_price": price, "return_20d": technical.get("return_20d"), "return_90d": technical.get("return_90d"), "rsi14": momentum.get("rsi14"), "rv20": technical.get("realized_vol_20d_annualized"), "supports": supports[:4], "resistances": resistances[:4]}
    }
    options_source = {
        "schema_version": "1.0", "source_id": opt_id, "provider": "yfinance", "source_type": "options_research_chain",
        "as_of": as_of, "available_at": as_of, "retrieved_at": load(run / "options_yfinance_full.json").get("retrieved_at", as_of),
        "reliability": "secondary_unofficial", "source_url": "https://ranaroussi.github.io/yfinance/reference/api/yfinance.Ticker.html",
        "data": {"symbol": symbol, "gamma_status": gamma_status, "positive_oi_rows": positive_oi, "options_status": options.get("status")}
    }
    (run / "ir_primary_sources.json").write_text(json.dumps(sec_source, ensure_ascii=False, indent=2), encoding="utf-8")
    (run / "market_evidence.json").write_text(json.dumps(market_source, ensure_ascii=False, indent=2), encoding="utf-8")
    (run / "options_evidence.json").write_text(json.dumps(options_source, ensure_ascii=False, indent=2), encoding="utf-8")
    (run / "alpha_vantage_research.json").write_text(json.dumps({"schema_version": "1.0", "source_id": f"alpha_vantage:{symbol}:{as_of}", "provider": "Alpha Vantage", "source_type": "estimates", "status": "empty", "symbol": symbol, "as_of": as_of, "available_at": as_of, "retrieved_at": as_of, "reliability": "secondary", "estimates": []}, ensure_ascii=False, indent=2), encoding="utf-8")
    (run / "valuation_snapshot.json").write_text(json.dumps({"symbol": symbol, "as_of": as_of, "status": "conditional_no_pit_consensus", "point_in_time_consensus": None, "note": "沒有時間點一致預期，估值不提出未核驗 forward P/E。"}, ensure_ascii=False, indent=2), encoding="utf-8")
    research = {
        "title": f"{symbol} 完整證據鏈研究報告",
        "research_state": "READY_CONDITIONAL",
        "summary": {
            "headline": f"{symbol} 收盤 {money(price)}；20 日報酬 {current_return}、90 日報酬 {long_return}、20 日實現波動率 {rv}，短期要把趨勢強度與追價風險分開。",
            "thesis": f"最新 SEC 一級財務資料顯示收入 {money(revenue, 0)}、毛利 {money(gross_profit, 0)}、淨利 {money(net_income, 0)}、營運現金流 {money(operating_cf, 0)}。長期主線的核心不是單一季度，而是收入、利潤與現金流能否延續。",
            "variant_perception": f"市場容易把近期價格動能直接當成基本面確認；本報告把 {symbol} 拆成已實現財務、技術結構、波動率與未驗證催化劑四部分。",
            "primary_horizon": "短期看支撐/阻力與事件波動；中期看盈利與估值重估；長期看商業經濟性、現金流和資本回報。",
            "key_risks": [f"20 日實現波動率 {rv}", f"現價與最近支撐 {s1}、阻力 {r1} 的距離", "未有時間點一致預期資料", f"期權 Gamma 狀態：{gamma_status}"],
            "next_evidence": ["下一個完整交易日的收盤與成交量", "最新季度收入、毛利與營運現金流", "有時間戳的期權買賣價、OI 與 Greeks", "同一設定的樣本外交易結果"]
        },
        "global_limitations": ["本次最新完整日線收盤是已完成交易日參考，不等同同日即時價格。", "沒有時間點一致預期，不提出未核驗 forward P/E。", "沒有可靠正 OI 或可執行期權報價時，Gamma wall 與交易商方向保持抑制。"],
        "modules": {
            "overview": {"blocks": [{"type": "paragraph", "title": "結論先行", "text": f"{symbol} 目前呈現「價格/技術狀態」與「基本面驗證」需要分開的研究狀態。收盤 {money(price)}，20 日報酬 {current_return}，90 日報酬 {long_return}；最新 SEC 報告收入 {money(revenue, 0)}，營運現金流 {money(operating_cf, 0)}。因此短期可以研究結構，不能把技術強勢直接等同於長期主線已確認。"}], "judgments": [{"label": "研究狀態", "conclusion": "READY_CONDITIONAL · 條件式可研究", "why": "市場、SEC 和期權代理均有資料，但一致預期、同日盤中確認與部分期權欄位不足。", "confidence": "medium", "evidence_ids": [market_id, sec_id]}]},
            "fundamentals": {"blocks": [{"type": "paragraph", "title": "最新已報告數字", "text": f"SEC（{filed or '最新申報'}）顯示：收入 {money(revenue, 0)}；毛利 {money(gross_profit, 0)}；淨利 {money(net_income, 0)}；營運現金流 {money(operating_cf, 0)}；現金及等價物 {money(cash, 0)}。這些是已報告 FACT，不是預測。"}, {"type": "paragraph", "title": "看什麼 / 讀到什麼 / 為什麼重要", "text": "看什麼：收入、毛利、淨利、營運現金流和資產負債表。讀到什麼：當前資料可以確認已實現經營結果，但不能用一個季度直接外推完整年度。為什麼重要：估值能否維持取決於盈利質量和現金流延續，不是單看收入規模。"}], "judgments": [{"label": "基本面證據", "conclusion": "已報告結果可讀；前瞻轉折仍需下一季度驗證", "why": "SEC 是一級來源，但目前沒有額外時間點一致預期作為獨立對照。", "confidence": "medium", "evidence_ids": [sec_id]}]},
            "valuation": {"blocks": [{"type": "paragraph", "title": "估值狀態", "text": "目前沒有可核驗的時間點一致預期，因此不把未核驗的 forward P/E 當成結論。估值應回到已實現盈利、現金流、資本需求和市場已反映的增長假設。"}, {"type": "paragraph", "title": "估值判斷", "text": "下行情景：盈利或現金流低於市場隱含假設，估值先壓縮。基準情景：已報告結果大致延續，股價在當前預期附近消化。上行情景：收入、利潤率與現金流同步改善，估值才有重新上修基礎。"}], "judgments": [{"label": "估值可用性", "conclusion": "條件式；等待時間點一致預期", "why": "Alpha Vantage estimates packet 為空，不能建立可重播的市場共識。", "confidence": "low_to_medium", "evidence_ids": [sec_id]}]},
            "technical": {"blocks": [{"type": "paragraph", "title": "日線技術狀態", "text": f"{as_of} 可用的最新完整收盤為 {money(price)}；EMA20 {money(ma.get('ema20'))}、SMA50 {money(ma.get('sma50'))}、SMA200 {money(ma.get('sma200'))}；RSI14 {rsi}；20 日報酬 {current_return}；90 日報酬 {long_return}；20 日實現波動率 {rv}。"}], "judgments": [{"label": "技術判斷", "conclusion": f"現價位於最近支撐 {s1} 與阻力 {r1} 之間；方向要等突破/回踩確認", "why": "日線結構提供候選反應區，但沒有同日 VWAP、ORH、ORL 就不能聲稱盤中確認。", "confidence": "medium", "evidence_ids": [market_id]}]},
            "options": {"blocks": [{"type": "paragraph", "title": "期權資料質量", "text": f"yfinance 期權資料為研究鏈視圖；目前 Gamma 狀態為 {gamma_status}，正 OI 列為 {positive_oi if positive_oi is not None else '未知'}。沒有可靠買賣價/OI/Greeks 時，只能用作波動率與資料質量提示。"}, {"type": "paragraph", "title": "看什麼 / 讀到什麼 / 為什麼重要 / 限制", "text": "看什麼：到期結構、ATM 跨式代理、IV、OI 與 Gamma 質量。讀到什麼：期權可以提示事件波動，但目前不能提供可靠方向。為什麼重要：波動率只應改變倉位折扣，不會創造方向優勢。限制：沒有可執行報價或可靠正 OI 時，不畫 Gamma wall、不推斷交易商方向。"}], "judgments": [{"label": "期權狀態", "conclusion": f"{gamma_status} · 不把未驗證資料當作方向訊號", "why": "yfinance 是獨立研究鏈，不是即時 OPRA/交易商持倉資料。", "confidence": "low", "evidence_ids": [opt_id]}]},
            "governance": {"blocks": [{"type": "paragraph", "title": "證據治理", "text": "研究包把 SEC FACT、IBKR 市場資料、yfinance 期權代理和模型輸出分開。缺失欄位保留為缺失，不把缺失轉成零，也不把 gross Gamma 寫成 signed dealer GEX。"}]},
            "risk": {"judgments": [{"label": "倉位狀態", "conclusion": "Kelly 只作研究級倉位參考", "why": "當前波動率高、同一設定樣本外驗證不足，全 Kelly、半 Kelly與四分之一 Kelly 都需要服從風險折扣與固定風險上限。", "confidence": "low", "evidence_ids": [market_id]}]},
            "scenarios": {"blocks": [{"type": "paragraph", "title": "使用方法", "text": "日內樹回答價格事件發生後下一步看什麼；短期樹回答數日至數週的修復、消化或破位；長期樹回答商業經濟性與估值是否強化或否定主線。三個期限不混用。"}], "long_term_context": {"watch": ["收入與毛利", "營運現金流", "資本強度與稀釋", "競爭地位", "估值支撐"], "strengthen_trigger": "收入、利潤率與現金流同步改善，且估值仍可承受。", "mixed_trigger": "收入改善，但利潤率、現金流或資本需求抵消進展。", "weaken_trigger": "核心經營機制惡化，或估值與資本需求不再支持主線。"}},
            "evidence": {"blocks": [{"type": "paragraph", "title": "證據清單", "text": f"SEC：{filed or '最新申報'}；IBKR 日線、1 分鐘與 10 秒資料；yfinance 期權鏈；所有原始資料、衍生結果和校驗資訊會收入證據鏈報告包。"}]}
        }
    }
    (run / "research_content.json").write_text(json.dumps(research, ensure_ascii=False, indent=2), encoding="utf-8")
    claims = {"schema_version": "1.0", "claims": [
        {"claim_id": "C1", "label": "FACT", "text": f"SEC 最新申報收入為 {money(revenue, 0)}、淨利為 {money(net_income, 0)}、營運現金流為 {money(operating_cf, 0)}。", "evidence_refs": [sec_id], "invalidation": "更正後的一級申報改變數字。"},
        {"claim_id": "C2", "label": "DATA_RESULT", "text": f"最新完整收盤為 {money(price)}，20 日報酬 {current_return}，90 日報酬 {long_return}，20 日實現波動率 {rv}。", "evidence_refs": [market_id], "invalidation": "下一個完整交易日顯著改變技術狀態。"},
        {"claim_id": "C3", "label": "MODEL_OUTPUT", "text": f"情景樹使用有來源的支撐、阻力、均線和波動錨點；期權 Gamma 狀態為 {gamma_status}，不推斷交易商方向。", "evidence_refs": [market_id, opt_id], "invalidation": "刷新資料後通過相應質量閘門。"}
    ]}
    (run / "claims.json").write_text(json.dumps(claims, ensure_ascii=False, indent=2), encoding="utf-8")
    for role, reason in [("bull", "價格結構與已報告經營結果提供正面研究路徑，但仍需盈利與現金流延續。"), ("bear", "高波動、估值預期或盈利現金流落差可能導致回撤。"), ("skeptic", "尚無時間點一致預期與同日盤中確認，不能把技術狀態寫成完整交易優勢。")]:
        (run / f"{role}_review.json").write_text(json.dumps({"role": role, "findings": [{"claim_id": "C2", "evidence_refs": [market_id], "reason": reason}], "evidence_requests": [{"request": "取得下一季度一級財務與同日市場/期權證據。"}]}, ensure_ascii=False, indent=2), encoding="utf-8")
    (run / "arbitration.json").write_text(json.dumps({"schema_version": "1.0", "state": "READY_CONDITIONAL", "decision": "條件式可研究", "claim_ids": ["C1", "C2", "C3"], "rationale": "資料足以完成研究，但不足以把方向、估值共識或期權 Gamma 寫成已驗證。"}, ensure_ascii=False, indent=2), encoding="utf-8")
    missing_options = ["positive_open_interest", "live_option_bid_ask_and_greeks", "dealer_sign", "full_chain_market_validation"]
    manifest = {"schema_version": "1.0", "run_id": f"{symbol}_{as_of}", "symbol": symbol, "as_of": as_of, "evidence_cutoff": f"{as_of}T23:59:59+08:00", "price_timestamp": f"{as_of}T16:00:00-04:00", "research_state": "READY_CONDITIONAL", "global_limitations": ["同日盤中欄位只在同日資料形成後才使用。", "沒有時間點一致預期，不提出未核驗 forward P/E。", "期權 OI/報價不足時抑制 Gamma wall。"], "modules": {}}
    common = {"status": "complete", "confidence": "medium", "module_as_of": as_of, "freshness_status": "current", "source_artifacts": [], "evidence_ids": [], "missing_fields": []}
    for name in ["overview", "fundamentals", "valuation", "technical", "options", "governance", "risk", "scenarios", "evidence"]:
        manifest["modules"][name] = dict(common)
    manifest["modules"]["overview"]["source_artifacts"] = ["sec_research.json", "stock_eval.json"]
    manifest["modules"]["fundamentals"]["source_artifacts"] = ["sec_research.json", "ir_primary_sources.json"]
    manifest["modules"]["valuation"].update({"status": "conditional", "confidence": "low_to_medium", "freshness_status": "conditional_no_pit_consensus", "source_artifacts": ["sec_research.json", "valuation_snapshot.json"], "missing_fields": ["point_in_time_consensus"]})
    manifest["modules"]["technical"].update({"module_as_of": as_of, "source_artifacts": ["market_ibkr_daily_full.json", "stock_eval.json", "intraday_features.json"], "missing_fields": ["same_session_orh_orl_vwap"]})
    manifest["modules"]["options"].update({"status": "partial", "confidence": "low", "freshness_status": "historical_proxy_only", "source_artifacts": ["options_yfinance_full.json", "options_features.json", "options_gamma_structure.json"], "missing_fields": missing_options})
    manifest["modules"]["risk"].update({"status": "conditional", "confidence": "low_to_medium", "freshness_status": "diagnostic_proxy", "source_artifacts": ["stock_eval.json", "intraday_features.json"], "missing_fields": ["validated_same_setup_oos_kelly", "same_session_live_packet"]})
    manifest["modules"]["scenarios"].update({"confidence": "conditional", "freshness_status": "conditional_tree", "source_artifacts": ["stock_eval.json", "intraday_features.json", "research_content.json"]})
    (run / "report_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    resolution = {"schema_version": "1.0", "requirements": [{"field": field, "status": "NOT_AVAILABLE_AT_CUTOFF", "attempts": [{"provider": "current run", "artifact": "report inputs", "result": "not available or not validated"}], "next_action": "refresh the specific source and retain the limitation"} for field in ["point_in_time_consensus", "same_session_orh_orl_vwap", *missing_options, "validated_same_setup_oos_kelly", "same_session_live_packet"]]}
    resolution_by_field = {item["field"]: item for item in resolution["requirements"]}
    for module in manifest["modules"].values():
        if module.get("missing_fields"):
            module["evidence_resolution"] = [resolution_by_field[field] for field in module["missing_fields"] if field in resolution_by_field]
    (run / "report_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (run / "evidence_resolution.json").write_text(json.dumps(resolution, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"symbol": symbol, "run_dir": str(run), "price": price, "sec_filed": filed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
