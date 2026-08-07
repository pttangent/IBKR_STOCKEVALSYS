#!/usr/bin/env python3
"""Deterministic market/technical/options calculations for stock-eval-system."""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path
from statistics import median, pstdev
from typing import Any

def f(value: Any) -> float | None:
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None

def load_json(path: str | Path) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)

def _rows(payload: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in keys:
            if isinstance(payload.get(key), list):
                return [x for x in payload[key] if isinstance(x, dict)]
    return []

def normalize_bars(payload: Any) -> list[dict[str, Any]]:
    out = []
    for row in _rows(payload, ("bars", "results", "data")):
        close = f(row.get("close", row.get("c")))
        high = f(row.get("high", row.get("h", close)))
        low = f(row.get("low", row.get("l", close)))
        open_ = f(row.get("open", row.get("o", close)))
        volume = f(row.get("volume", row.get("v", 0))) or 0.0
        if close is None or high is None or low is None or open_ is None or close <= 0 or high < low:
            continue
        stamp = row.get("date", row.get("datetime", row.get("t", row.get("time"))))
        if isinstance(stamp, (int, float)):
            stamp = dt.datetime.fromtimestamp(float(stamp) / (1000 if stamp > 10_000_000_000 else 1), dt.timezone.utc).date().isoformat()
        out.append({"date": str(stamp or ""), "open": open_, "high": high, "low": low, "close": close, "volume": volume})
    out.sort(key=lambda x: x["date"])
    return out

def sma(values: list[float], n: int) -> float | None:
    return sum(values[-n:]) / n if len(values) >= n else None

def ema_series(values: list[float], n: int) -> list[float | None]:
    if not values:
        return []
    out: list[float | None] = [None] * len(values)
    if len(values) < n:
        return out
    prev = sum(values[:n]) / n
    out[n - 1] = prev
    alpha = 2 / (n + 1)
    for i in range(n, len(values)):
        prev = alpha * values[i] + (1 - alpha) * prev
        out[i] = prev
    return out

def rsi(values: list[float], n: int = 14) -> float | None:
    if len(values) <= n:
        return None
    gains = [max(values[i] - values[i - 1], 0.0) for i in range(1, len(values))]
    losses = [max(values[i - 1] - values[i], 0.0) for i in range(1, len(values))]
    avg_gain = sum(gains[:n]) / n
    avg_loss = sum(losses[:n]) / n
    for gain, loss in zip(gains[n:], losses[n:]):
        avg_gain = (avg_gain * (n - 1) + gain) / n
        avg_loss = (avg_loss * (n - 1) + loss) / n
    if avg_loss == 0:
        return 100.0
    return 100 - 100 / (1 + avg_gain / avg_loss)

def atr(bars: list[dict[str, Any]], n: int = 14) -> float | None:
    if len(bars) <= n:
        return None
    tr = []
    for i, bar in enumerate(bars):
        prev_close = bars[i - 1]["close"] if i else bar["close"]
        tr.append(max(bar["high"] - bar["low"], abs(bar["high"] - prev_close), abs(bar["low"] - prev_close)))
    value = sum(tr[1 : n + 1]) / n
    for x in tr[n + 1 :]:
        value = (value * (n - 1) + x) / n
    return value

def technical_analysis(bars: list[dict[str, Any]]) -> dict[str, Any]:
    if len(bars) < 30:
        raise ValueError(f"technical analysis needs at least 30 valid bars; got {len(bars)}")
    closes = [x["close"] for x in bars]
    highs = [x["high"] for x in bars]
    lows = [x["low"] for x in bars]
    volumes = [x["volume"] for x in bars]
    latest = closes[-1]
    ema5, ema10, ema20 = [ema_series(closes, n)[-1] for n in (5, 10, 20)]
    ma = {"ema5": ema5, "ema10": ema10, "ema20": ema20, "sma50": sma(closes, 50), "sma200": sma(closes, 200)}
    usable = [(k, v) for k, v in ma.items() if v is not None]
    asc = sum(1 for i in range(len(usable)) for j in range(i + 1, len(usable)) if usable[i][1] > usable[j][1])
    desc = sum(1 for i in range(len(usable)) for j in range(i + 1, len(usable)) if usable[i][1] < usable[j][1])
    spread = (max(v for _, v in usable) - min(v for _, v in usable)) / latest if latest else None
    compressed = spread is not None and spread < 0.08
    direction = "compressed/neutral" if compressed else "bullish" if asc > desc else "bearish" if desc > asc else "mixed"
    macd_line = ema_series(closes, 12)[-1] - ema_series(closes, 26)[-1] if len(closes) >= 26 else None
    macd_series = [(a - b) if a is not None and b is not None else None for a, b in zip(ema_series(closes, 12), ema_series(closes, 26))]
    signal_values = [x for x in macd_series if x is not None]
    signal = ema_series(signal_values, 9)[-1] if len(signal_values) >= 9 else None
    macd_state = "unavailable" if macd_line is None or signal is None else "bullish" if macd_line > signal else "bearish"
    bb_mid = sma(closes, 20)
    bb_std = (sum((x - bb_mid) ** 2 for x in closes[-20:]) / 20) ** 0.5 if bb_mid is not None else None
    bb = {"middle": bb_mid, "upper": bb_mid + 2 * bb_std if bb_mid is not None else None, "lower": bb_mid - 2 * bb_std if bb_mid is not None else None}
    recent = bars[-90:]
    hi, lo = max(x["high"] for x in recent), min(x["low"] for x in recent)
    fib = {"38.2": hi - (hi - lo) * 0.382, "50.0": hi - (hi - lo) * 0.5, "61.8": hi - (hi - lo) * 0.618}
    swing_support = sorted({x["low"] for i, x in enumerate(recent[2:-2], 2) if x["low"] <= min(recent[i - 2]["low"], recent[i - 1]["low"], recent[i + 1]["low"], recent[i + 2]["low"]) and x["low"] < latest}, reverse=True)[:3]
    swing_resistance = sorted({x["high"] for i, x in enumerate(recent[2:-2], 2) if x["high"] >= max(recent[i - 2]["high"], recent[i - 1]["high"], recent[i + 1]["high"], recent[i + 2]["high"]) and x["high"] > latest})[:3]
    lo_bin, hi_bin = min(closes), max(closes)
    width = (hi_bin - lo_bin) / 20 if hi_bin > lo_bin else 1.0
    nodes = []
    for bucket in range(20):
        lower, upper = lo_bin + bucket * width, lo_bin + (bucket + 1) * width
        weight = sum(vol for close, vol in zip(closes, volumes) if lower <= close < upper)
        if weight:
            nodes.append({"mid": round((lower + upper) / 2, 4), "volume": round(weight, 2)})
    nodes.sort(key=lambda x: x["volume"], reverse=True)
    up_vol = sum(b["volume"] for i, b in enumerate(bars[-10:]) if i == 0 or b["close"] >= bars[-10 + i - 1]["close"])
    down_vol = sum(b["volume"] for i, b in enumerate(bars[-10:]) if i > 0 and b["close"] < bars[-10 + i - 1]["close"])
    log_returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes)) if closes[i] > 0 and closes[i - 1] > 0]
    rv_window = log_returns[-20:] if len(log_returns) >= 20 else log_returns
    realized_vol_20d = (pstdev(rv_window) * math.sqrt(252)) if len(rv_window) >= 2 else None
    return {
        "as_of": bars[-1]["date"], "observations": len(bars), "last_price": latest,
        "return_20d": latest / closes[-21] - 1 if len(closes) > 21 else None,
        "return_90d": latest / closes[-91] - 1 if len(closes) > 91 else None,
        "ma": ma, "ma_alignment": {"direction": direction, "ascending_pairs": asc, "descending_pairs": desc, "spread_pct": spread, "compression": compressed},
        "momentum": {"rsi14": rsi(closes), "macd": macd_line, "macd_signal": signal, "macd_state": macd_state, "bollinger": bb, "atr14": atr(bars)},
        "support_resistance": {"supports": swing_support + [round(x, 4) for x in fib.values() if x < latest], "resistances": swing_resistance + [round(x, 4) for x in fib.values() if x > latest], "fib_range": {"high": hi, "low": lo, "levels": fib}},
        "close_weighted_volume_nodes": nodes[:5], "volume_up_down_ratio": up_vol / down_vol if down_vol else None,
        "realized_vol_20d_annualized": realized_vol_20d,
        "limitations": ["daily close-price weighted nodes are not a true intraday volume profile", "RSI and MA signals are descriptive, not directional recommendations"],
    }

def norm_options(payload: Any) -> list[dict[str, Any]]:
    out = []
    for row in _rows(payload, ("options", "results", "data", "contracts")):
        typ = str(row.get("type", row.get("contract_type", row.get("right", "")))).lower()
        typ = "call" if typ in ("c", "call") else "put" if typ in ("p", "put") else typ
        strike = f(row.get("strike", row.get("strike_price")))
        if strike is None or strike <= 0 or typ not in ("call", "put"):
            continue
        bid, ask, last = f(row.get("bid")), f(row.get("ask")), f(row.get("last", row.get("last_price")))
        valid_mid = bid is not None and ask is not None and bid > 0 and ask >= bid
        mid = (bid + ask) / 2 if valid_mid else last
        expiry = str(row.get("expiration", row.get("expiration_date", row.get("expiry", ""))))
        if len(expiry) >= 8 and expiry[:8].isdigit():
            expiry = f"{expiry[:4]}-{expiry[4:6]}-{expiry[6:8]}"
        else:
            expiry = expiry[:10]
        raw_quality = str(row.get("quote_quality") or ("bid_ask_mid" if valid_mid else "last_fallback"))
        quote_quality = raw_quality if valid_mid or raw_quality in ("model_only", "last_ohlcv_no_bid_ask") else "last_fallback"
        provider_iv = f(row.get("iv", row.get("implied_volatility")))
        usable_iv = provider_iv if valid_mid or raw_quality == "model_only" else None
        out.append({"type": typ, "strike": strike, "bid": bid, "ask": ask, "last": last, "mid": mid, "expiry": expiry, "volume": f(row.get("volume", 0)) or 0.0, "open_interest": f(row.get("open_interest", row.get("oi", 0))) or 0.0, "iv": usable_iv, "delta": f(row.get("delta")), "quote_quality": quote_quality})
    return out

def norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))

def bs_price(spot: float, strike: float, t: float, vol: float, right: str, rate: float = 0.0, dividend: float = 0.0) -> float:
    if t <= 0 or vol <= 0:
        return max(0.0, (spot - strike) if right == "call" else (strike - spot))
    d1 = (math.log(spot / strike) + (rate - dividend + 0.5 * vol * vol) * t) / (vol * math.sqrt(t))
    d2 = d1 - vol * math.sqrt(t)
    if right == "call":
        return spot * math.exp(-dividend * t) * norm_cdf(d1) - strike * math.exp(-rate * t) * norm_cdf(d2)
    return strike * math.exp(-rate * t) * norm_cdf(-d2) - spot * math.exp(-dividend * t) * norm_cdf(-d1)

def implied_vol(price: float | None, spot: float, strike: float, t: float, right: str) -> float | None:
    if price is None or price <= 0 or spot <= 0 or strike <= 0 or t <= 0:
        return None
    intrinsic = bs_price(spot, strike, t, 1e-8, right)
    if price < intrinsic - 1e-6:
        return None
    low, high = 1e-6, 5.0
    if bs_price(spot, strike, t, high, right) < price:
        return None
    for _ in range(80):
        mid = (low + high) / 2
        if bs_price(spot, strike, t, mid, right) < price:
            low = mid
        else:
            high = mid
    return (low + high) / 2

def expiry_years(expiry: str, as_of: str | None) -> float | None:
    try:
        end = dt.date.fromisoformat(expiry)
        start = dt.date.fromisoformat(as_of) if as_of else dt.date.today()
        return max((end - start).days, 1) / 365.0
    except ValueError:
        return None

def option_analysis(payload: Any, spot: float, as_of: str | None = None) -> dict[str, Any]:
    options = norm_options(payload)
    if not options:
        return {"status": "unavailable", "reason": "no valid option rows"}
    for row in options:
        t = expiry_years(row["expiry"], as_of)
        if row["iv"] is None and t and row["quote_quality"] != "model_only":
            row["iv"] = implied_vol(row["mid"], spot, row["strike"], t, row["type"])
    expiries = sorted({x["expiry"] for x in options if x["expiry"]})
    nearest_expiry = expiries[0] if expiries else ""
    near = [x for x in options if x["expiry"] == nearest_expiry]
    atm = sorted(near, key=lambda x: abs(x["strike"] - spot))[:4]
    market_atm_ivs = [x["iv"] for x in atm if x["iv"] is not None and x["quote_quality"] == "bid_ask_mid"]
    model_atm_ivs = [x["iv"] for x in atm if x["iv"] is not None and x["quote_quality"] in ("last_fallback", "last_ohlcv_no_bid_ask", "model_only")]
    atm_ivs = market_atm_ivs or model_atm_ivs
    calls = [x for x in options if x["type"] == "call"]
    puts = [x for x in options if x["type"] == "put"]
    call_vol, put_vol = sum(x["volume"] for x in calls), sum(x["volume"] for x in puts)
    call_oi, put_oi = sum(x["open_interest"] for x in calls), sum(x["open_interest"] for x in puts)
    atm_straddle = sum(x["mid"] or 0 for x in atm if x["strike"] == min(atm, key=lambda z: abs(z["strike"] - spot))["strike"])
    t_atm = expiry_years(nearest_expiry, as_of) if nearest_expiry else None
    approx = atm_straddle / spot * math.sqrt(math.pi / (2 * t_atm)) if atm_straddle and spot and t_atm else None
    return {"status": "ok", "contracts": len(options), "expiries": expiries, "front_expiry": nearest_expiry, "atm_iv": median(atm_ivs) if atm_ivs else None, "atm_iv_status": "market_quote" if market_atm_ivs else "model_only_no_market_quote" if model_atm_ivs else "unavailable", "atm_iv_method": "numerical_black_scholes_from_mid_or_provider_iv", "atm_straddle_approximation_diagnostic": approx, "put_call_volume_ratio": put_vol / call_vol if call_vol else None, "put_call_oi_ratio": put_oi / call_oi if call_oi else None, "activity_distribution_only": True, "quote_quality_counts": {"bid_ask_mid": sum(x["quote_quality"] == "bid_ask_mid" for x in options), "last_fallback": sum(x["quote_quality"] == "last_fallback" for x in options), "last_ohlcv_no_bid_ask": sum(x["quote_quality"] == "last_ohlcv_no_bid_ask" for x in options), "model_only": sum(x["quote_quality"] == "model_only" for x in options), "no_quote": sum(x["quote_quality"] == "no_quote" for x in options)}, "front_total_variance": (median(atm_ivs) ** 2 * t_atm) if atm_ivs and t_atm else None, "warnings": ["put/call totals do not identify buy/sell or open/close direction", "Greeks are not assumed when absent", "wide/stale quote checks require provider timestamps"]}

def term_structure(front_payload: Any, back_payload: Any, spot: float, as_of: str | None = None) -> dict[str, Any]:
    front = option_analysis(front_payload, spot, as_of)
    back = option_analysis(back_payload, spot, as_of)
    if front.get("atm_iv") is None or back.get("atm_iv") is None:
        return {"status": "unavailable", "front": front, "back": back}
    ft = expiry_years(front.get("front_expiry", ""), as_of)
    bt = expiry_years(back.get("front_expiry", ""), as_of)
    if not ft or not bt or bt <= ft:
        return {"status": "unavailable", "front": front, "back": back, "reason": "invalid comparable expiries"}
    w1, w2 = front["atm_iv"] ** 2 * ft, back["atm_iv"] ** 2 * bt
    return {"status": "ok", "front_expiry": front["front_expiry"], "back_expiry": back["front_expiry"], "front_iv": front["atm_iv"], "back_iv": back["atm_iv"], "front_total_variance": w1, "back_total_variance": w2, "forward_variance": (w2 - w1) / (bt - ft), "interpretation": "event-rich/front-loaded" if w1 / w2 > 1.15 else "normal/contango" if w1 / w2 < 0.95 else "flat"}
