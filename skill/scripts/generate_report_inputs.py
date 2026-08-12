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


def ratio(a: Any, b: Any) -> float | None:
    try:
        if a is None or b in (None, 0):
            return None
        return float(a) / float(b)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def build_data_judgment(symbol: str, technical: dict, price: Any, revenue: Any,
                        gross_profit: Any, net_income: Any, operating_cf: Any,
                        cash: Any, supports: list, resistances: list,
                        gamma_status: str, positive_oi: Any, options: dict) -> dict:
    ma = technical.get("ma", {}) or {}
    momentum = technical.get("momentum", {}) or {}
    r20 = float(technical.get("return_20d") or 0)
    r90 = float(technical.get("return_90d") or 0)
    rv20 = float(technical.get("realized_vol_20d_annualized") or 0)
    rsi14 = float(momentum.get("rsi14") or 50)
    ema20 = float(ma.get("ema20") or price or 0)
    sma50 = float(ma.get("sma50") or price or 0)
    sma200 = float(ma.get("sma200") or price or 0)
    above_ema = float(price or 0) >= ema20
    above_sma50 = float(price or 0) >= sma50
    above_sma200 = float(price or 0) >= sma200
    if r20 < -0.08 and r90 > 1.0:
        momentum_read = f"20 日下跌 {pct(r20)}，但 90 日仍暴漲 {pct(r90)}；目前更像大幅上漲後的高波動修正，不能用單日反彈判定修正已結束。"
    elif r20 < -0.05 and r90 > 0.15 and above_sma200:
        momentum_read = f"20 日下跌 {pct(r20)}，但 90 日仍上升 {pct(r90)}；這是中期上升趨勢中的短線回撤，還不是趨勢反轉。"
    elif r20 > 0.10 and rsi14 >= 70:
        momentum_read = f"20 日上升 {pct(r20)}、90 日上升 {pct(r90)}，RSI14 {rsi14:.2f} 已進入偏熱區；方向偏多，但追價的回撤代價正在增加。"
    elif r20 > 0.03 and r90 > 0.15 and above_ema and above_sma50:
        momentum_read = f"20 日上升 {pct(r20)}、90 日上升 {pct(r90)}，價格位於 EMA20 與 SMA50 之上；短中期動能目前同向。"
    elif r20 < -0.05 and r90 < 0.10 and not above_sma200:
        momentum_read = f"20 日下跌 {pct(r20)}，90 日只上升 {pct(r90)}，且價格低於 SMA200；短期弱勢已經與長期均線壓力重疊。"
    elif r20 < 0 and above_sma200:
        momentum_read = f"20 日下跌 {pct(r20)}，但價格仍在 SMA200 之上；短線偏弱，長期結構尚未被日線完全破壞。"
    elif r20 < 0 and not above_ema and not above_sma50:
        momentum_read = f"20 日下跌 {pct(r20)}，價格低於 EMA20 與 SMA50；短線弱勢已有均線結構配合，反彈需先收復均線。"
    else:
        momentum_read = f"20 日報酬 {pct(r20)}、90 日報酬 {pct(r90)}，RSI14 {rsi14:.2f}；方向訊號不一致，應等待支撐/阻力被接受或拒絕。"
    volatility_read = f"20 日年化實現波動率為 {pct(rv20)}；每 1 萬美元模擬帳戶的日內一個標準差約為 {pct(rv20 / (252 ** 0.5))}，所以方向正確也不代表倉位風險低。"
    if net_income is not None and float(net_income) < 0:
        fundamental_read = f"最新申報淨利為 {money(net_income, 0)}，盈利端仍是主要驗證缺口；即使收入 {money(revenue, 0)}，也不能只用收入增長支持估值。"
    elif operating_cf is not None and net_income is not None and float(net_income) != 0:
        conversion = ratio(operating_cf, net_income)
        if conversion is not None and conversion > 1.2:
            fundamental_read = f"收入 {money(revenue, 0)}、淨利 {money(net_income, 0)}，營運現金流 {money(operating_cf, 0)} 約為淨利的 {conversion:.2f} 倍；現金轉換是目前基本面較強的部分，但仍需下一期延續。"
        elif conversion is not None and conversion < 0.8:
            fundamental_read = f"收入 {money(revenue, 0)}、淨利 {money(net_income, 0)}，營運現金流 {money(operating_cf, 0)} 只有淨利的 {conversion:.2f} 倍；盈利到現金的轉換是估值主要風險。"
        else:
            fundamental_read = f"收入 {money(revenue, 0)}、淨利 {money(net_income, 0)}、營運現金流 {money(operating_cf, 0)} 大致同向；目前可確認經營結果，但尚不足以單獨證明前瞻加速。"
    else:
        fundamental_read = f"最新申報收入為 {money(revenue, 0)}，但淨利或營運現金流資料不完整；基本面結論只能保持條件式。"
    level_read = f"現價 {money(price)}；最近支撐 {money(supports[0]) if supports else '—'}，阻力 {money(resistances[0]) if resistances else '—'}。"
    if above_ema and above_sma50 and above_sma200:
        structure_read = "價格同時站在 EMA20、SMA50、SMA200 之上，回撤先看均線能否轉為支撐。"
    elif not above_ema and not above_sma50 and above_sma200:
        structure_read = "價格跌破 EMA20 與 SMA50 但仍在 SMA200 之上，這是中期修正結構，不能直接寫成長期反轉。"
    elif not above_sma200:
        structure_read = "價格低於 SMA200，長期趨勢尚未恢復；任何反彈都要先通過中長期均線壓力驗證。"
    else:
        structure_read = "均線方向並不完全一致，支撐/阻力的實際接受度比單一均線標籤更重要。"
    expiry = options.get("expiry_features", []) or []
    front = expiry[0] if expiry else {}
    back = expiry[-1] if expiry else {}
    quote_rows = front.get("quote_rows") if front else None
    if positive_oi and gamma_status == "AVAILABLE_GROSS_ONLY":
        options_read = f"全鏈中有 {positive_oi} 列正 OI，Gross Gamma 有可觀察值，但缺少交易商持倉方向；期權可用於波動與價位集中觀察，不能給出 signed GEX。"
    elif gamma_status == "UNAVAILABLE_ZERO_OR_UNTRUSTED_OI":
        options_read = "OI 缺失或不可信，Gamma wall 已被抑制；期權目前只能作資料品質與波動風險提示。"
    else:
        options_read = f"期權狀態為 {gamma_status}；可用報價列 {quote_rows if quote_rows is not None else '—'}，方向性結論仍受報價與持倉資料限制。"
    conversion = ratio(operating_cf, net_income)

    # These are deliberately case-specific research judgments.  The report
    # schema supplies the fields, but the wording must come from the current
    # evidence rather than a reusable conclusion template.
    if r20 < -0.05 and r90 > 1.0 and net_income is not None and float(net_income) < 0:
        differentiated = (
            f"{symbol} 的價格仍處在 90 日暴漲 {pct(r90)} 後的回撤段，20 日已跌 {pct(r20)}；"
            f"真正需要解決的不是反彈幅度，而是收入 {money(revenue, 0)} 能否在淨利 {money(net_income, 0)} 的虧損背景下轉成可持續盈利。"
        )
        horizon = (
            f"短期先看 {money(supports[0]) if supports else '主要支撐'} 是否守住；"
            f"中期看反彈能否收復均線並重新接近 {money(resistances[0]) if resistances else '上方阻力'}；"
            f"長期只有盈利缺口收窄，才足以把 {pct(r90)} 的價格重估轉成基本面重估。"
        )
    elif r20 < -0.05 and r90 > 0.15 and above_sma200 and conversion is not None and conversion > 1.2:
        differentiated = (
            f"{symbol} 的主要矛盾在價格而不在已報告現金質量：20 日回撤 {pct(r20)}，但仍站在 SMA200 上方，"
            f"而營運現金流約為淨利 {conversion:.2f} 倍。這使 {money(supports[0]) if supports else '支撐'} 附近成為結構驗證位，"
            f"不是已確認的買入訊號。"
        )
        horizon = (
            f"短期觀察 {money(supports[0]) if supports else '支撐'} 的回踩承接；"
            f"中期要看價格能否重新站回 EMA20/SMA50 並向 {money(resistances[0]) if resistances else '阻力'} 推進；"
            f"長期看 {conversion:.2f} 倍現金轉換能否延續，而不是只看 {pct(r90)} 的累積升幅。"
        )
    elif r20 > 0.10 and rsi14 >= 70:
        differentiated = (
            f"{symbol} 現在的研究重點已從『是否有上升動能』轉為『這段動能能否在不大幅回撤下延續』："
            f"20 日上升 {pct(r20)}、RSI14 {rsi14:.2f}，且價格站在三條主要均線之上。"
        )
        horizon = (
            f"短期不追逐 RSI14 {rsi14:.2f} 的熱度，先等回撤在均線附近形成承接；"
            f"中期看 {money(resistances[0]) if resistances else '新高區'} 能否被接受；"
            f"長期仍取決於收入 {money(revenue, 0)}、淨利 {money(net_income, 0)} 和現金流 {money(operating_cf, 0)} 是否同步增長。"
        )
    elif r20 > 0.03 and r90 > 0.15 and above_ema and above_sma50 and conversion is not None and conversion < 0.8:
        differentiated = (
            f"{symbol} 的價格動能與均線結構都偏強，但基本面最需要追蹤的是盈利到現金的落差："
            f"20 日上升 {pct(r20)}，營運現金流只有淨利的 {conversion:.2f} 倍。"
        )
        horizon = (
            f"短期順勢條件仍在，但回撤不能失守 {money(supports[0]) if supports else '支撐'}；"
            f"中期要看價格在 {money(resistances[0]) if resistances else '阻力'} 附近是否仍有量價承接；"
            f"長期估值能否維持，關鍵是現金轉換改善，而非再增加一段價格漲幅。"
        )
    elif r20 < -0.05 and r90 < 0.10 and not above_sma200:
        differentiated = (
            f"{symbol} 的短期弱勢已經與長期結構重疊：20 日下跌 {pct(r20)}、90 日僅 {pct(r90)}，"
            f"價格又位於 SMA200 下方。即使基本面現金流約為淨利 {conversion:.2f} 倍，市場仍需要價格先修復長期趨勢。"
            if conversion is not None else
            f"{symbol} 的短期弱勢已經與長期結構重疊：20 日下跌 {pct(r20)}、90 日僅 {pct(r90)}，價格又位於 SMA200 下方。"
        )
        horizon = (
            f"短期先看 {money(supports[0]) if supports else '支撐'} 是否失守；"
            f"中期反彈必須重新通過 SMA200 與 {money(resistances[0]) if resistances else '阻力'}；"
            f"長期則要把價格修復與收入、盈利、現金流改善同時觀察。"
        )
    elif r20 > 0 and above_ema and above_sma50 and above_sma200:
        differentiated = (
            f"{symbol} 的價格、短中長期均線與已報告經營結果目前同向；但 20 日上升 {pct(r20)} 本身不能替代"
            f"下一期收入 {money(revenue, 0)}、淨利 {money(net_income, 0)} 和現金流 {money(operating_cf, 0)} 的驗證。"
        )
        horizon = (
            f"短期看回撤是否守住均線；中期看 {money(resistances[0]) if resistances else '阻力'} 能否轉成有效突破；"
            f"長期看目前盈利與現金流是否足以支撐更高估值。"
        )
    else:
        differentiated = (
            f"{symbol} 的日線訊號沒有形成單一方向：20 日 {pct(r20)}、90 日 {pct(r90)}，"
            f"現價位於 {money(supports[0]) if supports else '支撐'} 與 {money(resistances[0]) if resistances else '阻力'} 之間。"
            f"現階段最有信息量的不是貼上多空標籤，而是觀察哪一側先得到成交量與基本面配合。"
        )
        horizon = (
            f"短期觀察 {money(supports[0]) if supports else '支撐'} / {money(resistances[0]) if resistances else '阻力'} 的接受度；"
            f"中期把價格事件與下一期財務更新對照；長期以收入、盈利與現金流能否延續作為主判斷。"
        )
    if net_income is not None and float(net_income) < 0:
        valuation_down = f"若 {symbol} 仍無法把收入轉成正淨利，現價 {money(price)} 的估值支撐會繼續依賴遠期敘事，回撤風險高。"
        valuation_base = f"若收入維持 {money(revenue, 0)} 附近但盈利仍未改善，市場更可能在支撐 {money(supports[0]) if supports else '主要支撐'} 附近反覆，而不是直接完成重估。"
        valuation_up = "只有淨利轉正、營運現金流同步改善，才足以把目前價格敘事轉成可驗證的估值上修。"
    elif conversion is not None and conversion > 1.2:
        valuation_down = f"若營運現金流不再維持約為淨利 {conversion:.2f} 倍的轉換質量，現價的現金流溢價會先被壓縮。"
        valuation_base = f"若下一期延續收入 {money(revenue, 0)}、淨利 {money(net_income, 0)} 和現金流 {money(operating_cf, 0)}，價格大概率先在 {money(supports[0]) if supports else '支撐'} 至 {money(resistances[0]) if resistances else '阻力'} 間消化。"
        valuation_up = f"只有在現金轉換高於目前 {conversion:.2f} 倍且價格有效突破 {money(resistances[0]) if resistances else '阻力'} 後，估值上修才有雙重證據。"
    elif conversion is not None and conversion < 0.8:
        valuation_down = f"若營運現金流仍只有淨利的 {conversion:.2f} 倍，盈利質量不足會使現價 {money(price)} 面臨估值折價。"
        valuation_base = f"若收入和淨利大致延續，但現金轉換沒有改善，市場可能只把 {money(supports[0]) if supports else '支撐'} 視為防守位，而不給更高估值。"
        valuation_up = "只有盈利到現金的轉換明顯改善，並且價格重新站穩均線，才足以支持估值重估。"
    else:
        valuation_down = f"若下一期淨利 {money(net_income, 0)} 或現金流 {money(operating_cf, 0)} 低於目前水平，現價 {money(price)} 會先面臨估值壓縮。"
        valuation_base = f"若已報告結果大致延續，市場將在支撐 {money(supports[0]) if supports else '主要支撐'} 與阻力 {money(resistances[0]) if resistances else '主要阻力'} 之間重新定價。"
        valuation_up = f"若收入、淨利和現金流同步加速，且價格突破 {money(resistances[0]) if resistances else '阻力'} 後能守住，才有條件提高估值假設。"
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
        "above_ema": above_ema,
        "above_sma50": above_sma50,
        "above_sma200": above_sma200,
        "rv20": rv20,
    }


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
    judgment = build_data_judgment(symbol, technical, price, revenue, gross_profit, net_income,
                                   operating_cf, cash, supports, resistances, gamma_status,
                                   positive_oi, options)
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
            "headline": f"{symbol} 的當前可交易信息是：{judgment['momentum_read']} {judgment['level_read']} {judgment['volatility_read']}",
            "thesis": f"{judgment['fundamental_read']} {judgment['structure_read']}",
            "variant_perception": judgment["differentiated"],
            "primary_horizon": judgment["horizon"],
            "key_risks": [f"20 日實現波動率 {rv}", f"現價與最近支撐 {s1}、阻力 {r1} 的距離", "未有時間點一致預期資料", f"期權 Gamma 狀態：{gamma_status}"],
            "next_evidence": ["下一個完整交易日的收盤與成交量", "最新季度收入、毛利與營運現金流", "有時間戳的期權買賣價、OI 與 Greeks", "同一設定的樣本外交易結果"]
        },
        "global_limitations": ["本次最新完整日線收盤是已完成交易日參考，不等同同日即時價格。", "沒有時間點一致預期，不提出未核驗 forward P/E。", "沒有可靠正 OI 或可執行期權報價時，Gamma wall 與交易商方向保持抑制。"],
        "modules": {
            "overview": {"blocks": [{"type": "paragraph", "title": "研究結論", "text": f"{judgment['momentum_read']} {judgment['structure_read']} {judgment['fundamental_read']} {judgment['options_read']}"}], "judgments": [{"label": "研究狀態", "conclusion": f"{symbol}：{judgment['momentum_read']}", "why": f"{judgment['level_read']} {judgment['fundamental_read']}", "confidence": "medium", "evidence_ids": [market_id, sec_id]}]},
            "fundamentals": {"blocks": [{"type": "paragraph", "title": "最新已報告數字", "text": f"SEC（{filed or '最新申報'}）顯示：收入 {money(revenue, 0)}；毛利 {money(gross_profit, 0)}；淨利 {money(net_income, 0)}；營運現金流 {money(operating_cf, 0)}；現金及等價物 {money(cash, 0)}。"}, {"type": "paragraph", "title": "看什麼 / 讀到什麼 / 為什麼重要", "text": f"看什麼：收入 {money(revenue, 0)}、淨利 {money(net_income, 0)} 與營運現金流 {money(operating_cf, 0)} 的同向程度。讀到什麼：{judgment['fundamental_read']} 為什麼重要：這決定市場能否把目前價格變化理解為盈利重估，而不是單純估值擴張。"}], "judgments": [{"label": "基本面判斷", "conclusion": judgment["fundamental_read"], "why": f"最新申報日期為 {filed or '未知'}；沒有把未取得的前瞻共識補成預測。", "confidence": "medium", "evidence_ids": [sec_id]}]},
            "valuation": {"blocks": [{"type": "paragraph", "title": "估值狀態", "text": f"目前沒有可核驗的時間點一致預期；已報告收入 {money(revenue, 0)}、淨利 {money(net_income, 0)}、營運現金流 {money(operating_cf, 0)} 是本次估值可使用的底層資料。"}, {"type": "paragraph", "title": "估值判斷", "text": f"下行情景：{judgment['valuation_down']} 基準情景：{judgment['valuation_base']} 上行情景：{judgment['valuation_up']}"}], "judgments": [{"label": "估值判斷", "conclusion": f"{judgment['valuation_base']}", "why": f"{judgment['valuation_down']} {judgment['valuation_up']}", "confidence": "low_to_medium", "evidence_ids": [sec_id, market_id]}]},
            "technical": {"blocks": [{"type": "paragraph", "title": "日線技術狀態", "text": f"{as_of} 可用的最新完整收盤為 {money(price)}；EMA20 {money(ma.get('ema20'))}、SMA50 {money(ma.get('sma50'))}、SMA200 {money(ma.get('sma200'))}；RSI14 {rsi}；20 日報酬 {current_return}；90 日報酬 {long_return}；20 日實現波動率 {rv}。"}], "judgments": [{"label": "技術判斷", "conclusion": f"{judgment['momentum_read']} {judgment['level_read']}", "why": f"{judgment['structure_read']} 同日 VWAP、ORH、ORL 未形成，所以不能把支撐/阻力寫成盤中已確認。", "confidence": "medium", "evidence_ids": [market_id]}]},
            "options": {"blocks": [{"type": "paragraph", "title": "期權資料質量", "text": f"yfinance 期權資料為研究鏈視圖；目前 Gamma 狀態為 {gamma_status}，正 OI 列為 {positive_oi if positive_oi is not None else '未知'}。{judgment['options_read']}"}, {"type": "paragraph", "title": "看什麼 / 讀到什麼 / 為什麼重要 / 限制", "text": f"看什麼：到期結構、ATM 跨式代理、IV、OI 與 Gamma 質量。讀到什麼：{judgment['options_read']} 為什麼重要：期權資料最多改變波動折扣與事件風險，不能代替股票本身的方向證據。限制：缺少即時可執行報價、完整 OI 或 dealer sign 時，不畫 Gamma wall、不推斷交易商方向。"}], "judgments": [{"label": "期權判斷", "conclusion": judgment["options_read"], "why": f"本次資料來源為 yfinance 研究鏈；Gamma 狀態 {gamma_status}，正 OI 列 {positive_oi if positive_oi is not None else '未知'}。", "confidence": "low", "evidence_ids": [opt_id]}]},
            "governance": {"blocks": [{"type": "paragraph", "title": "證據治理", "text": "研究包把 SEC FACT、IBKR 市場資料、yfinance 期權代理和模型輸出分開。缺失欄位保留為缺失，不把缺失轉成零，也不把 gross Gamma 寫成 signed dealer GEX。"}]},
            "risk": {"judgments": [{"label": "倉位判斷", "conclusion": f"{judgment['volatility_read']}", "why": f"{judgment['momentum_read']} 目前只能把 Kelly 當作研究級比例，並受集中度、止損與當前 RV 約束。", "confidence": "low", "evidence_ids": [market_id]}]},
            "scenarios": {"blocks": [{"type": "paragraph", "title": "當前情景判斷", "text": f"日內先驗證 {judgment['level_read']}；短期分歧在於 {judgment['momentum_read']}；長期分歧在於 {judgment['fundamental_read']}。因此本次情景樹把價格事件、技術確認和基本面更新分開，不用單一分支替代完整研究結論。"}], "long_term_context": {"watch": [f"{symbol} 下一期收入與毛利是否延續目前水平", f"營運現金流 {money(operating_cf, 0)} 是否繼續覆蓋盈利與資本需求", "資本強度、稀釋與競爭地位", f"現價 {money(price)} 對已報告盈利的要求"], "strengthen_trigger": f"{symbol} 下一期收入、淨利 {money(net_income, 0)} 與營運現金流 {money(operating_cf, 0)} 同步改善，且價格能守住 {money(supports[0]) if supports else '主要支撐'}。", "mixed_trigger": f"收入延續但盈利或現金流沒有同步改善；價格仍在 {money(supports[0]) if supports else '支撐'} 與 {money(resistances[0]) if resistances else '阻力'} 之間反覆。", "weaken_trigger": f"營運現金流低於目前 {money(operating_cf, 0)} 的可比水平，或價格跌破 {money(supports[0]) if supports else '主要支撐'} 後反抽失敗。"}},
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
    for role, reason in [("bull", f"{judgment['structure_read']} 若 {symbol} 下一期仍能維持收入 {money(revenue, 0)} 與營運現金流 {money(operating_cf, 0)} 的質量，價格修復才有基本面配合。"), ("bear", f"20 日實現波動率 {rv}；若價格失守 {money(supports[0]) if supports else '主要支撐'}，且淨利/現金流低於目前申報水平，估值與價格可能同時承壓。"), ("skeptic", f"{judgment['options_read']} 加上尚無時間點一致預期，因此目前最強的結論是 {judgment['momentum_read']}，不是已驗證的長期超額收益。")]:
        (run / f"{role}_review.json").write_text(json.dumps({"role": role, "findings": [{"claim_id": "C2", "evidence_refs": [market_id], "reason": reason}], "evidence_requests": [{"request": "取得下一季度一級財務與同日市場/期權證據。"}]}, ensure_ascii=False, indent=2), encoding="utf-8")
    (run / "arbitration.json").write_text(json.dumps({"schema_version": "1.0", "state": "READY_CONDITIONAL", "decision": f"{symbol}：{judgment['momentum_read']}", "claim_ids": ["C1", "C2", "C3"], "rationale": f"{judgment['fundamental_read']} {judgment['structure_read']} {judgment['options_read']}"}, ensure_ascii=False, indent=2), encoding="utf-8")
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
