#!/usr/bin/env python3
"""Create PIT-safe, data-specific Traditional-Chinese report inputs from a frozen run packet.

This script prepares structured research synthesis and lightweight governance
artifacts. It deliberately keeps three semantic boundaries:
1. technical price levels are timing evidence, never fair value;
2. quarter+ scenarios use operating/valuation evidence, never intraday levels;
3. OCF/net-income cash-conversion ratios are only interpreted when net income is positive.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")


def load(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return {} if default is None else default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


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


def ratio(a: Any, b: Any) -> float | None:
    try:
        if a is None or b in (None, 0):
            return None
        return float(a) / float(b)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def positive_cash_conversion(operating_cf: Any, net_income: Any) -> float | None:
    """Cash-conversion multiple is interpretable only with positive net income."""
    try:
        if net_income is None or float(net_income) <= 0:
            return None
    except (TypeError, ValueError):
        return None
    return ratio(operating_cf, net_income)


def _price_timestamp(technical_as_of: str, now_utc: dt.datetime) -> str | None:
    try:
        day = dt.date.fromisoformat(str(technical_as_of)[:10])
    except ValueError:
        return None
    close_ny = dt.datetime.combine(day, dt.time(16, 0), tzinfo=NY)
    return min(close_ny.astimezone(dt.timezone.utc), now_utc).astimezone(NY).isoformat()


def _technical_judgment(technical: dict, price: Any) -> tuple[str, str, str]:
    ma = technical.get("ma", {}) or {}
    momentum = technical.get("momentum", {}) or {}
    r20 = float(technical.get("return_20d") or 0)
    r90 = float(technical.get("return_90d") or 0)
    rsi14 = float(momentum.get("rsi14") or 50)
    ema20 = float(ma.get("ema20") or price or 0)
    sma50 = float(ma.get("sma50") or price or 0)
    sma200 = float(ma.get("sma200") or price or 0)
    px = float(price or 0)
    above_ema, above_sma50, above_sma200 = px >= ema20, px >= sma50, px >= sma200

    if r20 < -0.08 and r90 > 1.0:
        momentum_read = f"20 日下跌 {pct(r20)}，但 90 日仍上升 {pct(r90)}；目前較像大幅上漲後的高波動修正，不能用單日反彈判定修正結束。"
    elif r20 < -0.05 and r90 > 0.15 and above_sma200:
        momentum_read = f"20 日下跌 {pct(r20)}，但 90 日仍上升 {pct(r90)}；屬中期上升結構中的短線回撤，尚不能直接定義為長期反轉。"
    elif r20 > 0.10 and rsi14 >= 70:
        momentum_read = f"20 日上升 {pct(r20)}、90 日上升 {pct(r90)}，RSI14 {rsi14:.2f} 已偏熱；方向仍強，但追價的回撤成本提高。"
    elif r20 > 0.03 and r90 > 0.15 and above_ema and above_sma50:
        momentum_read = f"20 日上升 {pct(r20)}、90 日上升 {pct(r90)}，價格位於 EMA20 與 SMA50 之上；短中期動能同向。"
    elif r20 < -0.05 and not above_sma200:
        momentum_read = f"20 日下跌 {pct(r20)}，且價格低於 SMA200；短期弱勢已與長期均線壓力重疊。"
    else:
        momentum_read = f"20 日報酬 {pct(r20)}、90 日報酬 {pct(r90)}、RSI14 {rsi14:.2f}；方向證據不足以只靠單一指標貼多空標籤。"

    if above_ema and above_sma50 and above_sma200:
        structure_read = "價格位於 EMA20、SMA50、SMA200 上方；回撤時先觀察均線與已計算支撐區是否形成承接。"
    elif not above_ema and not above_sma50 and above_sma200:
        structure_read = "價格低於 EMA20 與 SMA50、但仍高於 SMA200；這是中期修正結構，不等於長期趨勢已反轉。"
    elif not above_sma200:
        structure_read = "價格低於 SMA200；長期技術結構尚未修復，反彈需先通過中長期均線壓力。"
    else:
        structure_read = "均線方向不完全一致；實際支撐/阻力的接受或拒絕比單一均線標籤更重要。"

    rv20 = float(technical.get("realized_vol_20d_annualized") or 0)
    volatility_read = f"20 日年化實現波動率為 {pct(rv20)}；1 萬美元模擬帳戶的一日 1σ 尺度約 {pct(rv20 / (252 ** 0.5))}，因此方向判斷與倉位風險必須分開。"
    return momentum_read, structure_read, volatility_read


def _fundamental_judgment(revenue: Any, net_income: Any, operating_cf: Any) -> tuple[str, float | None]:
    conversion = positive_cash_conversion(operating_cf, net_income)
    if net_income is not None and float(net_income) < 0:
        if operating_cf is not None and float(operating_cf) < 0:
            text = (f"最新申報淨利 {money(net_income, 0)}、營運現金流 {money(operating_cf, 0)} 皆為負；"
                    f"不使用 OCF/淨利倍數解讀現金轉換，應追蹤虧損與現金流缺口能否同步收窄。收入為 {money(revenue, 0)}。")
        else:
            text = f"最新申報淨利 {money(net_income, 0)} 仍為負；即使收入 {money(revenue, 0)}，盈利端仍是主要驗證缺口。"
    elif conversion is not None and conversion > 1.2:
        text = f"收入 {money(revenue, 0)}、淨利 {money(net_income, 0)}；營運現金流 {money(operating_cf, 0)} 約為淨利 {conversion:.2f} 倍，現金轉換目前較強，但仍需後續期間延續。"
    elif conversion is not None and conversion < 0.8:
        text = f"收入 {money(revenue, 0)}、淨利 {money(net_income, 0)}；營運現金流 {money(operating_cf, 0)} 約為淨利 {conversion:.2f} 倍，盈利到現金的轉換仍需改善。"
    elif net_income is not None and operating_cf is not None:
        text = f"收入 {money(revenue, 0)}、淨利 {money(net_income, 0)}、營運現金流 {money(operating_cf, 0)} 大致同向；目前可確認已報告經營結果，但不能由此補出未取得的前瞻成長率。"
    else:
        text = f"最新申報收入 {money(revenue, 0)}，但淨利或營運現金流資料不完整；基本面結論維持條件式。"
    return text, conversion


def _valuation_judgment(symbol: str, revenue: Any, net_income: Any, operating_cf: Any, conversion: float | None) -> tuple[str, str, str]:
    """Financial scenario language only; no technical level is allowed to become fair value."""
    if net_income is not None and float(net_income) < 0:
        down = f"若 {symbol} 收入無法轉成正淨利、且營運現金流仍為負，遠期敘事需要承擔更高折現與融資風險。"
        base = "若收入維持但盈利與現金流尚未轉正，本次只能維持條件式估值，不輸出沒有模型支持的價格目標。"
        up = "只有淨利轉正、營運現金流同步改善，並有可核驗預期或估值模型承接，才足以建立可重現的估值上修。"
    elif conversion is not None and conversion > 1.2:
        down = f"若營運現金流不再維持目前約 {conversion:.2f} 倍的正向現金轉換，現金流品質溢價應下修。"
        base = "若收入、盈利與現金流大致延續，目前只能維持基本面基準情景；價格區間需另由 DCF、可比公司或 PIT 預期模型推導。"
        up = "若盈利與現金流同步加速，且可重現估值模型支持更高倍數或現金流現值，才建立估值上行情景。"
    elif conversion is not None and conversion < 0.8:
        down = f"若營運現金流仍只有淨利約 {conversion:.2f} 倍，盈利品質折價可能維持。"
        base = "若收入與淨利延續、但現金轉換沒有改善，估值先維持條件式；技術支撐不能替代 fair value。"
        up = "若盈利到現金的轉換明顯改善，且可比公司/DCF/PIT 預期支持，才提高估值假設。"
    else:
        down = f"若下一期淨利 {money(net_income, 0)} 或營運現金流 {money(operating_cf, 0)} 明顯弱於目前水準，估值假設應下修。"
        base = "若已報告結果大致延續，本次維持條件式估值；沒有可重現估值模型時不給價格型 fair value。"
        up = "若收入、淨利與現金流同步加速，且可重現估值模型支持，才提高估值假設。"
    return down, base, up


def build_data_judgment(symbol: str, technical: dict, price: Any, revenue: Any,
                        gross_profit: Any, net_income: Any, operating_cf: Any,
                        cash: Any, supports: list, resistances: list,
                        gamma_status: str, positive_oi: Any, options: dict) -> dict:
    momentum_read, structure_read, volatility_read = _technical_judgment(technical, price)
    fundamental_read, conversion = _fundamental_judgment(revenue, net_income, operating_cf)
    level_read = f"最近完整日線參考價 {money(price)}；候選支撐 {money(supports[0]) if supports else '—'}，候選阻力 {money(resistances[0]) if resistances else '—'}。"
    quote_rows = (options.get("expiry_features", [{}]) or [{}])[0].get("quote_rows")
    if positive_oi and gamma_status == "AVAILABLE_GROSS_ONLY":
        options_read = f"全鏈有 {positive_oi} 列正 OI，Gross Gamma 可觀察，但缺少 dealer/customer 方向；可用於波動與集中度研究，不能稱為 signed dealer GEX。"
    elif gamma_status == "UNAVAILABLE_ZERO_OR_UNTRUSTED_OI":
        options_read = "OI 缺失或不可信，Gamma wall 應抑制；期權只保留資料品質與波動風險提示。"
    else:
        options_read = f"期權狀態 {gamma_status}；可用報價列 {quote_rows if quote_rows is not None else '—'}，方向性結論仍受報價與持倉資料限制。"

    r20 = float(technical.get("return_20d") or 0)
    r90 = float(technical.get("return_90d") or 0)
    if net_income is not None and float(net_income) < 0:
        differentiated = (f"{symbol} 的價格動能與基本面仍有落差：20 日 {pct(r20)}、90 日 {pct(r90)}，"
                          f"但淨利 {money(net_income, 0)} 仍為負。核心驗證不是再多一段漲幅，而是收入能否轉成盈利與正營運現金流。")
    elif conversion is not None:
        differentiated = (f"{symbol} 的價格與營運要分開驗證：20 日 {pct(r20)}、90 日 {pct(r90)}；"
                          f"正淨利條件下，營運現金流/淨利約 {conversion:.2f} 倍，後續需確認此現金品質能否延續。")
    else:
        differentiated = f"{symbol} 的日線與基本面沒有形成可由單一指標概括的方向；下一個高資訊量事件是財務更新與價格結構是否同向。"

    horizon = (f"短期使用候選支撐/阻力與均線判斷 timing；中期把價格結構與下一期財務更新對照；"
               f"長期只看收入、毛利、盈利、現金流、資本需求、競爭與可重現估值，不用技術價位證明長期論點。")
    valuation_down, valuation_base, valuation_up = _valuation_judgment(symbol, revenue, net_income, operating_cf, conversion)
    return {
        "differentiated": differentiated,
        "momentum_read": momentum_read,
        "volatility_read": volatility_read,
        "fundamental_read": fundamental_read,
        "level_read": level_read,
        "structure_read": structure_read,
        "options_read": options_read,
        "valuation_down": valuation_down,
        "valuation_base": valuation_base,
        "valuation_up": valuation_up,
        "horizon": horizon,
        "conversion": conversion,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--as-of", required=True)
    args = ap.parse_args()
    run = Path(args.run_dir)
    symbol = args.symbol.upper()
    report_as_of = args.as_of
    now_utc = dt.datetime.now(dt.timezone.utc)

    stock = load(run / "stock_eval.json")
    sec = load(run / "sec_research.json")
    options = load(run / "options_features.json")
    gamma = load(run / "options_gamma_structure.json")
    if not options:
        options = {"provider": "yfinance", "status": "failed", "symbol": symbol, "retrieved_at": now_utc.isoformat(), "expiry_features": [], "warnings": ["本次期權鏈不可用。"]}
        (run / "options_features.json").write_text(json.dumps(options, ensure_ascii=False, indent=2), encoding="utf-8")
    if not gamma:
        gamma = {"provider": "options_gamma_structure", "status": "unavailable", "gamma_status": "UNAVAILABLE_ZERO_OR_UNTRUSTED_OI", "symbol": symbol, "data_quality": {"rows_with_positive_open_interest": 0, "eligible_rows": 0}, "warnings": ["沒有可用期權鏈，Gamma wall 已抑制。"]}
        (run / "options_gamma_structure.json").write_text(json.dumps(gamma, ensure_ascii=False, indent=2), encoding="utf-8")

    technical = stock.get("technical", {}) or {}
    technical_as_of = str(technical.get("as_of") or report_as_of)[:10]
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

    market_candidates = [
        (run / "market_ibkr_daily_full.json", "IBKR_TWS", "https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/"),
        (run / "market_massive_daily.json", "Massive_REST", "https://massive.com/docs/rest/stocks/aggregates"),
        (run / "market_yfinance_daily.json", "yfinance", "https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html"),
    ]
    market_path, market_provider, market_url = next(((p, provider, url) for p, provider, url in market_candidates if p.exists()), market_candidates[1])
    market_packet = load(market_path)
    market_id = f"market:{market_provider}:{symbol}:{technical_as_of}"
    sec_id = f"sec:{symbol}:{filed or report_as_of}"
    opt_id = f"options:yfinance:{symbol}:{report_as_of}"
    gamma_status = gamma.get("gamma_status") or gamma.get("status") or "未知"
    positive_oi = (gamma.get("data_quality") or {}).get("rows_with_positive_open_interest")
    judgment = build_data_judgment(symbol, technical, price, revenue, gross_profit, net_income, operating_cf, cash,
                                   supports, resistances, gamma_status, positive_oi, options)

    sec_source = {
        "schema_version": "1.0", "source_id": sec_id, "provider": "SEC_EDGAR", "source_type": "company_filing",
        "as_of": filed or report_as_of, "available_at": filed or report_as_of, "retrieved_at": sec.get("retrieved_at", now_utc.isoformat()),
        "reliability": "primary", "source_url": sec.get("source_url", "https://www.sec.gov/edgar/search/"),
        "data": {"symbol": symbol, "filed": filed, "facts": {k: fact(sec, k) for k in ["revenue", "gross_profit", "net_income", "operating_cash_flow", "cash_and_equivalents", "assets", "liabilities", "equity", "shares_outstanding"]}},
    }
    market_source = {
        "schema_version": "1.0", "source_id": market_id, "provider": market_provider, "source_type": "market_data",
        "as_of": technical_as_of, "available_at": technical_as_of, "retrieved_at": market_packet.get("retrieved_at", now_utc.isoformat()),
        "reliability": "primary_market" if market_provider != "yfinance" else "secondary_unofficial", "source_url": market_url,
        "data": {"symbol": symbol, "last_price": price, "return_20d": technical.get("return_20d"), "return_90d": technical.get("return_90d"), "rsi14": momentum.get("rsi14"), "rv20": technical.get("realized_vol_20d_annualized"), "supports": supports[:4], "resistances": resistances[:4]},
    }
    options_source = {
        "schema_version": "1.0", "source_id": opt_id, "provider": "yfinance", "source_type": "options_research_chain",
        "as_of": report_as_of, "available_at": report_as_of, "retrieved_at": load(run / "options_yfinance_full.json").get("retrieved_at", now_utc.isoformat()),
        "reliability": "secondary_unofficial", "source_url": "https://ranaroussi.github.io/yfinance/reference/api/yfinance.Ticker.html",
        "data": {"symbol": symbol, "gamma_status": gamma_status, "positive_oi_rows": positive_oi, "options_status": options.get("status")},
    }
    (run / "ir_primary_sources.json").write_text(json.dumps(sec_source, ensure_ascii=False, indent=2), encoding="utf-8")
    (run / "market_evidence.json").write_text(json.dumps(market_source, ensure_ascii=False, indent=2), encoding="utf-8")
    (run / "options_evidence.json").write_text(json.dumps(options_source, ensure_ascii=False, indent=2), encoding="utf-8")
    (run / "alpha_vantage_research.json").write_text(json.dumps({"schema_version": "1.0", "provider": "Alpha Vantage", "source_type": "estimates", "status": "empty", "symbol": symbol, "as_of": report_as_of, "retrieved_at": now_utc.isoformat(), "reliability": "secondary", "estimates": []}, ensure_ascii=False, indent=2), encoding="utf-8")
    (run / "valuation_snapshot.json").write_text(json.dumps({"symbol": symbol, "as_of": report_as_of, "status": "conditional_no_pit_consensus", "point_in_time_consensus": None, "fair_value": None, "note": "沒有 PIT 預期或可重現估值模型；不使用技術價位替代 fair value。"}, ensure_ascii=False, indent=2), encoding="utf-8")

    current_return = pct(technical.get("return_20d")); long_return = pct(technical.get("return_90d"))
    rv = pct(technical.get("realized_vol_20d_annualized")); rsi = num(momentum.get("rsi14"))
    s1 = money(supports[0]) if supports else "—"; r1 = money(resistances[0]) if resistances else "—"
    research = {
        "title": f"{symbol} 完整證據鏈研究報告",
        "research_state": "READY_CONDITIONAL",
        "summary": {
            "headline": f"{symbol}：{judgment['momentum_read']} {judgment['level_read']} {judgment['volatility_read']}",
            "thesis": f"{judgment['fundamental_read']} {judgment['structure_read']}",
            "variant_perception": judgment["differentiated"],
            "primary_horizon": judgment["horizon"],
            "key_risks": [f"20 日實現波動率 {rv}", f"候選支撐 {s1} / 阻力 {r1} 僅屬 timing 結構", "未有 PIT 一致預期或可重現 fair-value model", f"期權 Gamma 狀態：{gamma_status}"],
            "next_evidence": ["下一個完整交易日的收盤與成交量", "下一期收入、毛利、盈利與營運現金流", "有時間戳的期權 bid/ask、OI 與 Greeks", "同一 setup 的樣本外交易結果"],
        },
        "global_limitations": [f"最新 deterministic 日線截至 {technical_as_of}，不是自動等同報告日期 {report_as_of} 的已完成收盤。", "沒有 PIT 一致預期或可重現估值模型，不提出價格型 fair value。", "沒有 dealer sign 時 Gross Gamma 不等於 signed GEX。"],
        "modules": {
            "overview": {"blocks": [{"type": "paragraph", "title": "研究結論", "text": f"{judgment['momentum_read']} {judgment['structure_read']} {judgment['fundamental_read']} {judgment['options_read']}"}], "judgments": [{"label": "研究狀態", "conclusion": f"{symbol}：{judgment['momentum_read']}", "why": f"{judgment['level_read']} {judgment['fundamental_read']}", "confidence": "medium", "evidence_ids": [market_id, sec_id]}]},
            "fundamentals": {"blocks": [{"type": "paragraph", "title": "最新已報告數字", "text": f"SEC（{filed or '最新申報'}）：收入 {money(revenue, 0)}；毛利 {money(gross_profit, 0)}；淨利 {money(net_income, 0)}；營運現金流 {money(operating_cf, 0)}；現金及等價物 {money(cash, 0)}。"}, {"type": "paragraph", "title": "看什麼 / 讀到什麼 / 為什麼重要", "text": f"看什麼：收入、盈利、營運現金流是否同向。讀到什麼：{judgment['fundamental_read']} 為什麼重要：這決定價格重估是否有盈利/現金流承接。限制：未取得的前瞻數字不補成共識。"}], "judgments": [{"label": "基本面判斷", "conclusion": judgment["fundamental_read"], "why": f"最新申報日期 {filed or '未知'}。", "confidence": "medium", "evidence_ids": [sec_id]}]},
            "valuation": {"blocks": [{"type": "paragraph", "title": "估值狀態", "text": "目前沒有可核驗 PIT 一致預期或可重現 DCF/可比公司/倍數模型，因此不把技術價位改名成 fair value。"}, {"type": "paragraph", "title": "估值判斷", "text": f"下行情景：{judgment['valuation_down']} 基準情景：{judgment['valuation_base']} 上行情景：{judgment['valuation_up']}"}], "judgments": [{"label": "估值判斷", "conclusion": judgment["valuation_base"], "why": f"{judgment['valuation_down']} {judgment['valuation_up']}", "confidence": "low", "evidence_ids": [sec_id]}]},
            "technical": {"blocks": [{"type": "paragraph", "title": "日線技術狀態", "text": f"{technical_as_of} 可用的最新完整收盤參考為 {money(price)}；EMA20 {money(ma.get('ema20'))}、SMA50 {money(ma.get('sma50'))}、SMA200 {money(ma.get('sma200'))}；RSI14 {rsi}；20 日報酬 {current_return}；90 日報酬 {long_return}；20 日實現波動率 {rv}。"}], "judgments": [{"label": "技術判斷", "conclusion": f"{judgment['momentum_read']} {judgment['level_read']}", "why": f"{judgment['structure_read']}；沒有 same-session VWAP/ORH/ORL 時只輸出 next-session conditional tree。", "confidence": "medium", "evidence_ids": [market_id]}]},
            "options": {"blocks": [{"type": "paragraph", "title": "期權資料質量", "text": f"目前 Gamma 狀態 {gamma_status}；正 OI 列 {positive_oi if positive_oi is not None else '未知'}。{judgment['options_read']}"}], "judgments": [{"label": "期權判斷", "conclusion": judgment["options_read"], "why": "OI/IV 可建立 unsigned concentration，但沒有 dealer/customer side 時不能推 signed GEX。", "confidence": "low", "evidence_ids": [opt_id]}]},
            "governance": {"blocks": [{"type": "paragraph", "title": "證據治理", "text": f"研究包分離 SEC FACT、{market_provider} 市場資料、期權代理與 deterministic model output；缺失不轉成零。"}]},
            "risk": {"judgments": [{"label": "倉位判斷", "conclusion": judgment["volatility_read"], "why": "Kelly 只有在 setup/sample gate 通過時才能轉成 full/half/quarter 倉位；極小樣本僅保留診斷。", "confidence": "low", "evidence_ids": [market_id]}]},
            "scenarios": {"blocks": [{"type": "paragraph", "title": "當前情景判斷", "text": f"日內使用 {judgment['level_read']}；短期看 {judgment['momentum_read']}；長期只看 {judgment['fundamental_read']} 及估值/資本效率更新。"}], "long_term_context": {
                "watch": [f"{symbol} 下一期收入與毛利", "淨利與營運現金流是否改善", "資本強度/融資/稀釋", "競爭地位、需求與產能", "可重現估值模型與資本成本"],
                "strengthen_trigger": f"{symbol} 收入、毛利、盈利與營運現金流同步改善，且資本需求沒有吞噬價值創造。",
                "mixed_trigger": "收入或產品採用改善，但盈利、現金流、資本強度或競爭使價值創造仍不清楚。",
                "weaken_trigger": "盈利/現金流惡化、資本需求明顯升高、競爭位置轉弱，或可重現估值模型無法支持原 thesis。",
            }},
            "evidence": {"blocks": [{"type": "paragraph", "title": "證據清單", "text": f"SEC 申報、{market_provider} 日線、1 分鐘 evidence、期權鏈、deterministic outputs、reviews 與 checksums 一併納入 evidence-chain package。"}]},
        },
    }
    (run / "research_content.json").write_text(json.dumps(research, ensure_ascii=False, indent=2), encoding="utf-8")

    claims = {"schema_version": "1.0", "claims": [
        {"claim_id": "C1", "label": "FACT", "text": f"SEC 最新申報收入 {money(revenue, 0)}、淨利 {money(net_income, 0)}、營運現金流 {money(operating_cf, 0)}。", "evidence_refs": [sec_id], "invalidation": "一級申報更正。"},
        {"claim_id": "C2", "label": "DATA_RESULT", "text": f"最近完整日線參考價 {money(price)}，20 日報酬 {current_return}，90 日報酬 {long_return}，RV20 {rv}。", "evidence_refs": [market_id], "invalidation": "下一個完整交易日更新。"},
        {"claim_id": "C3", "label": "MODEL_OUTPUT", "text": f"情景樹只使用有 provenance 的 timing anchors；Gamma 狀態 {gamma_status} 不推斷 dealer sign。", "evidence_refs": [market_id, opt_id], "invalidation": "資料品質閘門刷新。"},
    ]}
    (run / "claims.json").write_text(json.dumps(claims, ensure_ascii=False, indent=2), encoding="utf-8")
    for role, reason in [
        ("bull", f"若下一期收入/毛利與營運現金流改善，且風險折扣下降，{symbol} 的基本面可能開始承接價格重估。"),
        ("bear", f"RV20 {rv}；若盈利/現金流惡化或資本需求升高，估值與價格可能同時承壓。"),
        ("skeptic", f"{judgment['options_read']} 且沒有 PIT 一致預期，因此不能把動能直接外推成長期超額收益。"),
    ]:
        (run / f"{role}_review.json").write_text(json.dumps({"role": role, "findings": [{"claim_id": "C2", "evidence_refs": [market_id], "reason": reason}], "evidence_requests": [{"request": "取得下一季度一級財務與同時點市場/期權證據。"}]}, ensure_ascii=False, indent=2), encoding="utf-8")
    (run / "arbitration.json").write_text(json.dumps({"schema_version": "1.0", "state": "READY_CONDITIONAL", "decision": f"{symbol}：{judgment['momentum_read']}", "claim_ids": ["C1", "C2", "C3"], "rationale": f"{judgment['fundamental_read']} {judgment['structure_read']} {judgment['options_read']}"}, ensure_ascii=False, indent=2), encoding="utf-8")

    missing_options = ["live_option_bid_ask_and_greeks", "dealer_sign", "full_chain_market_validation"]
    if not (isinstance(positive_oi, (int, float)) and positive_oi > 0):
        missing_options.insert(0, "positive_open_interest")
    price_ts = _price_timestamp(technical_as_of, now_utc)
    manifest = {
        "schema_version": "1.0", "run_id": f"{symbol}_{report_as_of}", "symbol": symbol, "as_of": report_as_of,
        "evidence_cutoff": now_utc.isoformat(), "price_timestamp": price_ts,
        "research_state": "READY_CONDITIONAL",
        "global_limitations": [f"最新 deterministic 日線截至 {technical_as_of}。", "沒有 PIT 一致預期，不提出未核驗 fair value。", "期權資料品質不足時抑制 dealer-direction inference。"],
        "modules": {},
    }
    common = {"status": "complete", "confidence": "medium", "module_as_of": technical_as_of, "freshness_status": "current" if technical_as_of == report_as_of else "previous_completed_session", "source_artifacts": [], "evidence_ids": [], "missing_fields": []}
    for name in ["overview", "fundamentals", "valuation", "technical", "options", "governance", "risk", "scenarios", "evidence"]:
        manifest["modules"][name] = dict(common)
    manifest["modules"]["overview"]["source_artifacts"] = ["sec_research.json", "stock_eval.json"]
    manifest["modules"]["fundamentals"]["source_artifacts"] = ["sec_research.json", "ir_primary_sources.json"]
    manifest["modules"]["valuation"].update({"status": "conditional", "confidence": "low", "freshness_status": "conditional_no_pit_consensus", "source_artifacts": ["sec_research.json", "valuation_snapshot.json"], "missing_fields": ["point_in_time_consensus", "reproducible_valuation_model"]})
    manifest["modules"]["technical"].update({"module_as_of": technical_as_of, "source_artifacts": [market_path.name, "stock_eval.json", "intraday_features.json"], "missing_fields": ["same_session_orh_orl_vwap"]})
    manifest["modules"]["options"].update({"status": "partial", "confidence": "low", "freshness_status": "historical_proxy_only", "source_artifacts": ["options_yfinance_full.json", "options_features.json", "options_gamma_structure.json"], "missing_fields": missing_options})
    manifest["modules"]["risk"].update({"status": "conditional", "confidence": "low", "freshness_status": "diagnostic_proxy", "source_artifacts": ["stock_eval.json", "intraday_features.json"], "missing_fields": ["validated_same_setup_oos_kelly", "same_session_live_packet"]})
    manifest["modules"]["scenarios"].update({"confidence": "conditional", "freshness_status": "conditional_tree", "source_artifacts": ["stock_eval.json", "intraday_features.json", "research_content.json"]})

    unresolved = ["point_in_time_consensus", "reproducible_valuation_model", "same_session_orh_orl_vwap", *missing_options, "validated_same_setup_oos_kelly", "same_session_live_packet"]
    resolution = {"schema_version": "1.0", "requirements": [{"field": field, "status": "NOT_AVAILABLE_AT_CUTOFF", "attempts": [{"provider": "current run", "artifact": "report inputs", "result": "not available or not validated"}], "next_action": "refresh the specific source and retain the limitation"} for field in unresolved]}
    if isinstance(positive_oi, (int, float)) and positive_oi > 0:
        resolution["requirements"].append({"field": "positive_open_interest", "status": "FOUND", "attempts": [{"artifact": "options_gamma_structure.json", "result": f"{int(positive_oi)} positive-OI rows"}], "next_action": "none"})
    resolution_by_field = {item["field"]: item for item in resolution["requirements"]}
    for module in manifest["modules"].values():
        if module.get("missing_fields"):
            module["evidence_resolution"] = [resolution_by_field[field] for field in module["missing_fields"] if field in resolution_by_field]

    (run / "report_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (run / "evidence_resolution.json").write_text(json.dumps(resolution, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"symbol": symbol, "run_dir": str(run), "price": price, "technical_as_of": technical_as_of, "evidence_cutoff": manifest["evidence_cutoff"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
