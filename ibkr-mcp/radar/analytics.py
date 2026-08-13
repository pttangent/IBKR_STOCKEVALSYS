from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from statistics import median
from typing import Iterable, Mapping, Sequence


def clamp(value: float, low: float = -100.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def safe_float(value, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


@dataclass(slots=True)
class TradeEvent:
    time: float
    price: float
    size: float
    side: int = 0  # +1 aggressive buy, -1 aggressive sell, 0 unknown
    exchange: str = ""
    conditions: str = ""
    source: str = ""

    @property
    def notional(self) -> float:
        return self.price * self.size


@dataclass(slots=True)
class QuoteEvent:
    time: float
    bid: float | None
    ask: float | None
    bid_size: float | None
    ask_size: float | None
    last: float | None = None
    volume: float | None = None
    trade_rate: float | None = None
    volume_rate: float | None = None


def classify_trade(
    price: float,
    bid: float | None,
    ask: float | None,
    previous_trade_price: float | None = None,
    previous_side: int = 0,
    epsilon: float = 1e-9,
) -> int:
    """Classify a print with quote-rule first, then tick-rule fallback.

    This is inference. Even with true Time & Sales, an aggressor flag is not supplied
    directly by IBKR for equities, so the result must be treated as a classifier.
    """
    if ask is not None and ask > 0 and price >= ask - epsilon:
        return 1
    if bid is not None and bid > 0 and price <= bid + epsilon:
        return -1
    if bid is not None and ask is not None and ask >= bid > 0:
        mid = (bid + ask) / 2.0
        if price > mid + epsilon:
            return 1
        if price < mid - epsilon:
            return -1
    if previous_trade_price is not None:
        if price > previous_trade_price + epsilon:
            return 1
        if price < previous_trade_price - epsilon:
            return -1
    return previous_side if previous_side in (-1, 1) else 0


def _window(trades: Sequence[TradeEvent], now: float, seconds: float) -> list[TradeEvent]:
    cutoff = now - seconds
    return [trade for trade in trades if trade.time >= cutoff]


def flow_split(trades: Sequence[TradeEvent]) -> dict[str, float | int]:
    known = [trade for trade in trades if trade.side in (-1, 1) and trade.size > 0]
    buy = sum(trade.size for trade in known if trade.side > 0)
    sell = sum(trade.size for trade in known if trade.side < 0)
    buy_notional = sum(trade.notional for trade in known if trade.side > 0)
    sell_notional = sum(trade.notional for trade in known if trade.side < 0)
    total = buy + sell
    net = buy - sell
    pressure = 100.0 * net / total if total else 0.0
    return {
        "buyVolume": buy,
        "sellVolume": sell,
        "buyNotional": buy_notional,
        "sellNotional": sell_notional,
        "classifiedVolume": total,
        "delta": net,
        "pressure": clamp(pressure),
        "knownCount": len(known),
        "unknownCount": max(0, len(trades) - len(known)),
        "knownFraction": (len(known) / len(trades)) if trades else 0.0,
    }


def robust_large_trade_score(trades: Sequence[TradeEvent], lookback: int = 300) -> tuple[float, float | None]:
    """Return signed 0..100 score for latest print and its robust size z-score."""
    if not trades:
        return 0.0, None
    latest = trades[-1]
    if latest.side == 0 or latest.size <= 0:
        return 0.0, None
    sample = [math.log1p(t.size) for t in trades[-lookback:-1] if t.size > 0]
    robust_z = None
    magnitude = 0.0
    if len(sample) >= 10:
        center = median(sample)
        mad = median(abs(value - center) for value in sample) or 0.1
        robust_z = (math.log1p(latest.size) - center) / (1.4826 * mad)
        magnitude = clamp(max(0.0, (robust_z - 1.5) * 28.0), 0.0, 100.0)
    if latest.notional >= 250_000:
        magnitude = max(magnitude, 100.0)
    elif latest.notional >= 100_000:
        magnitude = max(magnitude, 78.0)
    elif latest.notional >= 50_000:
        magnitude = max(magnitude, 55.0)
    return latest.side * magnitude, robust_z


def price_move_bps(trades: Sequence[TradeEvent]) -> float:
    if len(trades) < 2 or trades[0].price <= 0:
        return 0.0
    return 10_000.0 * math.log(trades[-1].price / trades[0].price)


def absorption_scores(trades: Sequence[TradeEvent], reference_bps: float = 8.0) -> dict[str, float]:
    """Estimate bid/offer absorption from executed flow vs price response."""
    split = flow_split(trades)
    pressure = float(split["pressure"])
    move = price_move_bps(trades)
    sell_pressure = max(0.0, -pressure)
    buy_pressure = max(0.0, pressure)
    downside_progress = max(0.0, -move)
    upside_progress = max(0.0, move)
    bid_efficiency = clamp(100.0 * (1.0 - min(1.0, downside_progress / reference_bps)), 0.0, 100.0)
    ask_efficiency = clamp(100.0 * (1.0 - min(1.0, upside_progress / reference_bps)), 0.0, 100.0)
    bid_absorption = sell_pressure * bid_efficiency / 100.0
    ask_absorption = buy_pressure * ask_efficiency / 100.0
    return {
        "bidAbsorption": round(clamp(bid_absorption, 0.0, 100.0), 2),
        "offerAbsorption": round(clamp(ask_absorption, 0.0, 100.0), 2),
        "priceMoveBps": round(move, 3),
        "flowPressure": round(pressure, 2),
    }


def exhaustion_scores(trades: Sequence[TradeEvent], now: float) -> dict[str, float]:
    recent = _window(trades, now, 5.0)
    prior = [t for t in trades if now - 20.0 <= t.time < now - 5.0]
    r = flow_split(recent)
    p = flow_split(prior)

    def side_score(side: int) -> float:
        r_vol = float(r["buyVolume"] if side > 0 else r["sellVolume"])
        p_vol = float(p["buyVolume"] if side > 0 else p["sellVolume"])
        r_rate = r_vol / 5.0
        p_rate = p_vol / 15.0
        if p_rate <= 0:
            return 0.0
        return clamp((1.0 - min(1.0, r_rate / p_rate)) * 100.0, 0.0, 100.0)

    return {
        "buyerExhaustion": round(side_score(1), 2),
        "sellerExhaustion": round(side_score(-1), 2),
    }


def infer_tick_size(prices: Iterable[float], fallback: float = 0.01) -> float:
    unique = sorted({round(float(p), 8) for p in prices if p and p > 0})
    diffs = [round(b - a, 8) for a, b in zip(unique, unique[1:]) if b - a > 1e-8]
    if not diffs:
        return fallback
    candidate = min(diffs)
    return max(0.0001, min(candidate, fallback) if candidate < fallback else fallback)


def build_footprint(
    trades: Sequence[TradeEvent],
    *,
    tick_size: float | None = None,
    max_levels: int = 80,
) -> list[dict[str, float]]:
    if not trades:
        return []
    step = tick_size or infer_tick_size((trade.price for trade in trades))
    buckets: dict[float, dict[str, float]] = defaultdict(lambda: {"buy": 0.0, "sell": 0.0, "unknown": 0.0, "trades": 0.0})
    for trade in trades:
        level = round(round(trade.price / step) * step, 8)
        row = buckets[level]
        row["trades"] += 1.0
        if trade.side > 0:
            row["buy"] += trade.size
        elif trade.side < 0:
            row["sell"] += trade.size
        else:
            row["unknown"] += trade.size
    prices = sorted(buckets, reverse=True)
    if len(prices) > max_levels:
        last_price = trades[-1].price
        prices = sorted(prices, key=lambda price: abs(price - last_price))[:max_levels]
        prices.sort(reverse=True)
    result = []
    for price in prices:
        row = buckets[price]
        buy = row["buy"]
        sell = row["sell"]
        result.append({
            "price": price,
            "sellAtBid": round(sell, 2),
            "buyAtAsk": round(buy, 2),
            "unknown": round(row["unknown"], 2),
            "delta": round(buy - sell, 2),
            "volume": round(buy + sell + row["unknown"], 2),
            "trades": int(row["trades"]),
        })
    return result


def high_volume_levels(footprint: Sequence[Mapping[str, float]], limit: int = 6) -> list[dict[str, float | str]]:
    if not footprint:
        return []
    ranked = sorted(footprint, key=lambda row: float(row.get("volume", 0.0)), reverse=True)[: max(1, limit)]
    output = []
    for row in ranked:
        delta = float(row.get("delta", 0.0))
        volume = max(0.0, float(row.get("volume", 0.0)))
        bias = "BUY" if delta > 0 else "SELL" if delta < 0 else "NEUTRAL"
        output.append({"price": float(row.get("price", 0.0)), "volume": volume, "delta": delta, "bias": bias})
    return output


def quote_imbalance(bid_size: float | None, ask_size: float | None) -> float:
    bid = max(0.0, safe_float(bid_size, 0.0) or 0.0)
    ask = max(0.0, safe_float(ask_size, 0.0) or 0.0)
    total = bid + ask
    return clamp(100.0 * (bid - ask) / total) if total else 0.0


def radar_activity_score(
    quote_events: Sequence[QuoteEvent],
    now: float,
    *,
    recent_seconds: float = 5.0,
    baseline_seconds: float = 120.0,
) -> dict[str, float]:
    recent = [q for q in quote_events if q.time >= now - recent_seconds]
    baseline = [q for q in quote_events if now - baseline_seconds <= q.time < now - recent_seconds]
    recent_rate = median([q.trade_rate for q in recent if q.trade_rate is not None] or [0.0])
    base_rate = median([q.trade_rate for q in baseline if q.trade_rate is not None] or [0.0])
    recent_volume_rate = median([q.volume_rate for q in recent if q.volume_rate is not None] or [0.0])
    base_volume_rate = median([q.volume_rate for q in baseline if q.volume_rate is not None] or [0.0])
    trade_ratio = recent_rate / base_rate if base_rate > 0 else 0.0
    volume_ratio = recent_volume_rate / base_volume_rate if base_volume_rate > 0 else 0.0
    score = clamp(max(0.0, max(trade_ratio, volume_ratio) - 1.0) * 45.0, 0.0, 100.0)
    return {
        "score": round(score, 2),
        "tradeRate": round(recent_rate, 4),
        "volumeRate": round(recent_volume_rate, 4),
        "tradeRateRatio": round(trade_ratio, 3),
        "volumeRateRatio": round(volume_ratio, 3),
    }
