from __future__ import annotations

import asyncio
import math
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from ib_async import IB, Stock

from .analytics import (
    QuoteEvent,
    TradeEvent,
    absorption_scores,
    build_footprint,
    classify_trade,
    exhaustion_scores,
    flow_split,
    high_volume_levels,
    quote_imbalance,
    radar_activity_score,
    robust_large_trade_score,
    safe_float,
)
from .planner import SubscriptionPlan, build_plan
from .storage import RadarStore


GENERIC_TICKS = "233,293,294,295,375"  # RTVolume, trade count/rate, volume rate, RTTradeVolume
DEFAULT_SYMBOLS = ["TER", "KLAC", "AEHR", "COHU", "FORM"]


def _now() -> float:
    return time.time()


def _iso(epoch: float | None) -> str | None:
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace("+00:00", "Z")


def _status_market_data_type(value: int | None) -> str:
    if value == 1:
        return "LIVE"
    if value in (3, 4):
        return "DELAYED"
    if value == 2:
        return "FROZEN"
    return "WAITING"


@dataclass(slots=True)
class SymbolState:
    symbol: str
    contract: Any = None
    ticker: Any = None
    status: str = "STARTING"
    market_data_type: int | None = None
    last_price: float | None = None
    previous_close: float | None = None
    bid: float | None = None
    ask: float | None = None
    bid_size: float | None = None
    ask_size: float | None = None
    volume: float | None = None
    quote_time: float | None = None
    last_trade_time: float | None = None
    trade_rate: float | None = None
    volume_rate: float | None = None
    rt_volume_raw: str = ""
    rt_trade_volume_raw: str = ""
    last_tick_index: int = 0
    last_proxy_volume: float | None = None
    last_quote_signature: tuple[Any, ...] | None = None
    previous_trade_price: float | None = None
    previous_side: int = 0
    trades: deque[TradeEvent] = field(default_factory=lambda: deque(maxlen=40_000))
    quotes: deque[QuoteEvent] = field(default_factory=lambda: deque(maxlen=12_000))
    alerts: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=300))
    errors: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=30))
    last_alert_key: str | None = None
    last_alert_at: float = 0.0


class RadarEngine:
    """Dual-mode IBKR realtime radar.

    radar mode:
        reqMktData + generic RT volume/rate fields; scalable to the user's market-data-line allocation.
    flow mode:
        reqMktData + true AllLast prints. Optionally also true BidAsk ticks, which costs a second
        tick-by-tick slot per symbol.
    """

    def __init__(
        self,
        symbols: list[str] | None = None,
        *,
        mode: str = "auto",
        market_data_lines: int = 100,
        flow_quote_source: str = "mktdata",
        storage_path: str | None = None,
        ib_factory: Callable[[], IB] = IB,
    ) -> None:
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._ib: IB | None = None
        self._ib_factory = ib_factory
        self._host = "127.0.0.1"
        self._port = 7497
        self._client_id = 4711
        self._connected = False
        self._connecting = False
        self._paused = False
        self._connection_error: str | None = None
        self._last_update = _now()
        self._last_snapshot_write = 0.0
        self._store = RadarStore(storage_path)
        self._plan = build_plan(
            symbols or DEFAULT_SYMBOLS,
            mode=mode,
            market_data_lines=market_data_lines,
            flow_quote_source=flow_quote_source,
        )
        self._states = {symbol: SymbolState(symbol=symbol) for symbol in self._plan.symbols}

    @property
    def plan(self) -> SubscriptionPlan:
        return self._plan

    def configure(
        self,
        *,
        symbols: list[str] | None = None,
        mode: str | None = None,
        market_data_lines: int | None = None,
        flow_quote_source: str | None = None,
    ) -> dict[str, Any]:
        if self._thread and self._thread.is_alive():
            raise RuntimeError("stop/pause radar before changing subscriptions")
        current = self._plan
        plan = build_plan(
            symbols or current.symbols,
            mode=mode or current.requested_mode,
            market_data_lines=market_data_lines or current.market_data_lines,
            flow_quote_source=flow_quote_source or current.flow_quote_source,
        )
        with self._lock:
            old = self._states
            self._states = {symbol: old.get(symbol, SymbolState(symbol=symbol)) for symbol in plan.symbols}
            self._plan = plan
        return self.plan_status()

    def set_connection(self, host: str, port: int, client_id: int) -> None:
        if self._thread and self._thread.is_alive():
            raise RuntimeError("stop radar before changing TWS connection")
        self._host = host
        self._port = int(port)
        self._client_id = int(client_id)

    def plan_status(self) -> dict[str, Any]:
        payload = self._plan.as_dict()
        payload["tws"] = {"host": self._host, "port": self._port, "clientId": self._client_id}
        return payload

    def start(self) -> dict[str, Any]:
        if self._plan.market_data_lines_required > self._plan.market_data_lines:
            raise RuntimeError("subscription plan exceeds configured market-data lines")
        if self._plan.mode == "flow" and self._plan.tick_by_tick_requests_required > self._plan.tick_by_tick_slots:
            raise RuntimeError("subscription plan exceeds configured tick-by-tick slots")
        with self._lock:
            if self._thread and self._thread.is_alive():
                return self.connection_status()
            self._store.begin_session(self._plan.symbols, self._plan.as_dict())
            self._stop_event.clear()
            self._connection_error = None
            self._paused = False
            self._thread = threading.Thread(target=self._run_thread, name="ibkr-realtime-radar", daemon=True)
            self._thread.start()
        return self.connection_status()

    def stop(self) -> dict[str, Any]:
        self._stop_event.set()
        ib = self._ib
        if ib is not None:
            try:
                ib.disconnect()
            except Exception:
                pass
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=5)
        self._store.end_session()
        return self.connection_status()

    def pause(self) -> dict[str, Any]:
        self.stop()
        with self._lock:
            self._paused = True
            for state in self._states.values():
                state.status = "PAUSED"
        return self.connection_status()

    def resume(self) -> dict[str, Any]:
        return self.start()

    def close(self) -> None:
        self.stop()
        self._store.close()

    def connection_status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "connected": self._connected,
                "connecting": self._connecting,
                "paused": self._paused,
                "running": bool(self._thread and self._thread.is_alive()),
                "host": self._host,
                "port": self._port,
                "clientId": self._client_id,
                "error": self._connection_error,
                "lastUpdate": _iso(self._last_update),
                "plan": self._plan.as_dict(),
                "recording": self._store.info(),
            }

    def _run_thread(self) -> None:
        try:
            asyncio.run(self._run_async())
        except Exception as exc:  # pragma: no cover - process boundary
            with self._lock:
                self._connected = False
                self._connecting = False
                self._connection_error = repr(exc)

    async def _qualify_in_batches(self, ib: IB, contracts: list[Any], batch_size: int = 20) -> list[Any]:
        qualified: list[Any] = []
        for start in range(0, len(contracts), batch_size):
            batch = contracts[start : start + batch_size]
            rows = await ib.qualifyContractsAsync(*batch)
            qualified.extend(rows)
            if start + batch_size < len(contracts):
                await asyncio.sleep(0.45)
        return qualified

    async def _run_async(self) -> None:
        ib = self._ib_factory()
        self._ib = ib
        ib.errorEvent += self._on_error
        with self._lock:
            self._connecting = True
        try:
            await ib.connectAsync(self._host, self._port, clientId=self._client_id, timeout=10, readonly=True)
            contracts = [Stock(symbol, "SMART", "USD") for symbol in self._plan.symbols]
            qualified = await self._qualify_in_batches(ib, contracts)
            with self._lock:
                self._connected = True
                self._connecting = False
            for contract in qualified:
                state = self._states.get(contract.symbol)
                if state is None:
                    continue
                state.contract = contract
                state.status = "WAITING"
                state.ticker = ib.reqMktData(contract, GENERIC_TICKS, False, False)
                await asyncio.sleep(0.025)  # stay below the socket API outbound message-rate ceiling
                if self._plan.mode == "flow":
                    ib.reqTickByTickData(contract, "AllLast", 0, False)
                    await asyncio.sleep(0.025)
                    if self._plan.flow_quote_source == "tick":
                        ib.reqTickByTickData(contract, "BidAsk", 0, False)
                        await asyncio.sleep(0.025)
            while not self._stop_event.is_set() and ib.isConnected():
                await asyncio.sleep(0.20)
                self._ingest()
        except Exception as exc:
            with self._lock:
                self._connection_error = repr(exc)
        finally:
            with self._lock:
                self._connected = False
                self._connecting = False
                for state in self._states.values():
                    if self._stop_event.is_set():
                        state.status = "PAUSED" if self._paused else "STOPPED"
            try:
                ib.disconnect()
            except Exception:
                pass
            self._ib = None

    def _on_error(self, *args: Any) -> None:
        code = args[1] if len(args) > 1 else None
        message = str(args[2]) if len(args) > 2 else "IBKR error"
        contract = args[3] if len(args) > 3 else None
        symbol = getattr(contract, "symbol", None)
        if code in (2104, 2106, 2158):
            return
        with self._lock:
            if symbol in self._states:
                state = self._states[symbol]
                state.errors.append({"time": _iso(_now()), "code": code, "message": message})
                if code in (10167, 10168):
                    state.status = "NO_SUBSCRIPTION"
            else:
                self._connection_error = f"IBKR {code}: {message}"

    @staticmethod
    def _parse_rt_volume(raw: Any) -> dict[str, float] | None:
        if raw is None:
            return None
        text = str(raw)
        parts = text.split(";")
        if len(parts) < 5:
            return None
        try:
            return {
                "price": float(parts[0]),
                "size": float(parts[1]),
                "time": float(parts[2]) / 1000.0,
                "totalVolume": float(parts[3]),
                "vwap": float(parts[4]),
            }
        except (TypeError, ValueError):
            return None

    def _ingest(self) -> None:
        now = _now()
        with self._lock:
            for state in self._states.values():
                ticker = state.ticker
                if ticker is None:
                    continue
                self._ingest_market_data(state, ticker, now)
                if self._plan.mode == "flow":
                    self._ingest_tick_by_tick(state, ticker, now)
                self._trim_state(state, now)
            self._last_update = now
            if now - self._last_snapshot_write >= 5.0:
                self._store.record_snapshot(self._build_snapshot(now))
                self._last_snapshot_write = now

    def _ingest_market_data(self, state: SymbolState, ticker: Any, now: float) -> None:
        state.last_price = safe_float(getattr(ticker, "last", None), state.last_price)
        state.previous_close = safe_float(getattr(ticker, "close", None), state.previous_close)
        state.bid = safe_float(getattr(ticker, "bid", None), state.bid)
        state.ask = safe_float(getattr(ticker, "ask", None), state.ask)
        state.bid_size = safe_float(getattr(ticker, "bidSize", None), state.bid_size)
        state.ask_size = safe_float(getattr(ticker, "askSize", None), state.ask_size)
        state.volume = safe_float(getattr(ticker, "volume", None), state.volume)
        state.trade_rate = safe_float(getattr(ticker, "tradeRate", None), state.trade_rate)
        state.volume_rate = safe_float(getattr(ticker, "volumeRate", None), state.volume_rate)
        state.market_data_type = getattr(ticker, "marketDataType", state.market_data_type)
        state.status = _status_market_data_type(state.market_data_type)
        quote_dt = getattr(ticker, "time", None)
        state.quote_time = quote_dt.timestamp() if hasattr(quote_dt, "timestamp") else now

        signature = (state.last_price, state.bid, state.ask, state.bid_size, state.ask_size, state.volume, state.trade_rate, state.volume_rate)
        if signature != state.last_quote_signature:
            quote = QuoteEvent(
                time=now,
                bid=state.bid,
                ask=state.ask,
                bid_size=state.bid_size,
                ask_size=state.ask_size,
                last=state.last_price,
                volume=state.volume,
                trade_rate=state.trade_rate,
                volume_rate=state.volume_rate,
            )
            state.quotes.append(quote)
            state.last_quote_signature = signature
            self._store.record_event(state.symbol, "quote", now, asdict(quote))

        if self._plan.mode != "radar":
            return
        raw = getattr(ticker, "rtTradeVolume", None) or getattr(ticker, "rtVolume", None)
        raw_text = str(raw or "")
        if raw_text and raw_text not in (state.rt_trade_volume_raw, state.rt_volume_raw):
            parsed = self._parse_rt_volume(raw)
            state.rt_trade_volume_raw = raw_text
            if parsed and parsed["price"] > 0 and parsed["size"] >= 0:
                self._append_trade(
                    state,
                    parsed["time"] or now,
                    parsed["price"],
                    parsed["size"],
                    exchange="",
                    conditions="",
                    source="MKTDATA_RT_VOLUME_PROXY",
                )
                state.last_proxy_volume = parsed["totalVolume"]
                return
        if state.volume is not None and state.last_price is not None:
            if state.last_proxy_volume is not None and state.volume > state.last_proxy_volume:
                size = max(0.0, state.volume - state.last_proxy_volume)
                self._append_trade(state, now, state.last_price, size, source="MKTDATA_VOLUME_DELTA_PROXY")
            state.last_proxy_volume = state.volume

    def _ingest_tick_by_tick(self, state: SymbolState, ticker: Any, now: float) -> None:
        rows = list(getattr(ticker, "tickByTicks", []) or [])
        for tick in rows[state.last_tick_index :]:
            price = safe_float(getattr(tick, "price", None))
            size = safe_float(getattr(tick, "size", None), 0.0) or 0.0
            tick_dt = getattr(tick, "time", None)
            stamp = tick_dt.timestamp() if hasattr(tick_dt, "timestamp") else now
            if price is not None and price > 0:
                self._append_trade(
                    state,
                    stamp,
                    price,
                    size,
                    exchange=str(getattr(tick, "exchange", "") or ""),
                    conditions=str(getattr(tick, "specialConditions", "") or ""),
                    source="TBT_ALL_LAST",
                )
                continue
            bid = safe_float(getattr(tick, "bidPrice", None))
            ask = safe_float(getattr(tick, "askPrice", None))
            if bid is not None or ask is not None:
                state.bid = bid if bid is not None else state.bid
                state.ask = ask if ask is not None else state.ask
                state.bid_size = safe_float(getattr(tick, "bidSize", None), state.bid_size)
                state.ask_size = safe_float(getattr(tick, "askSize", None), state.ask_size)
                quote = QuoteEvent(
                    time=stamp,
                    bid=state.bid,
                    ask=state.ask,
                    bid_size=state.bid_size,
                    ask_size=state.ask_size,
                    last=state.last_price,
                    volume=state.volume,
                    trade_rate=state.trade_rate,
                    volume_rate=state.volume_rate,
                )
                state.quotes.append(quote)
                self._store.record_event(state.symbol, "bidask_tbt", stamp, asdict(quote))
        state.last_tick_index = len(rows)

    def _append_trade(
        self,
        state: SymbolState,
        stamp: float,
        price: float,
        size: float,
        *,
        exchange: str = "",
        conditions: str = "",
        source: str,
    ) -> None:
        side = classify_trade(price, state.bid, state.ask, state.previous_trade_price, state.previous_side)
        trade = TradeEvent(time=stamp, price=price, size=max(0.0, size), side=side, exchange=exchange, conditions=conditions, source=source)
        state.trades.append(trade)
        state.last_trade_time = stamp
        state.last_price = price
        state.previous_trade_price = price
        if side:
            state.previous_side = side
        self._store.record_event(state.symbol, "trade", stamp, asdict(trade))

    @staticmethod
    def _trim_state(state: SymbolState, now: float) -> None:
        trade_cutoff = now - 1800.0
        while state.trades and state.trades[0].time < trade_cutoff:
            state.trades.popleft()
        quote_cutoff = now - 1800.0
        while state.quotes and state.quotes[0].time < quote_cutoff:
            state.quotes.popleft()

    def snapshot(self, symbol: str | None = None) -> dict[str, Any]:
        now = _now()
        with self._lock:
            if symbol:
                key = symbol.upper()
                if key not in self._states:
                    raise KeyError(symbol)
                rows = [self._snapshot_symbol(self._states[key], now)]
            else:
                rows = [self._snapshot_symbol(state, now) for state in self._states.values()]
            return self._build_snapshot(now, rows=rows)

    def _build_snapshot(self, now: float, rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        rows = rows if rows is not None else [self._snapshot_symbol(state, now) for state in self._states.values()]
        alerts = []
        for state in self._states.values():
            alerts.extend(state.alerts)
        alerts.sort(key=lambda item: item["time"], reverse=True)
        return {
            "generatedAt": _iso(now),
            "connection": self.connection_status(),
            "plan": self.plan_status(),
            "symbols": rows,
            "alerts": alerts[:60],
            "governance": {
                "radarMode": "reqMktData is a 250ms-style snapshot feed; footprint/order-flow fields are proxies.",
                "flowMode": "AllLast prints are tick-by-tick. Aggressor side is inferred from quotes/tick rule, not exchange-provided.",
                "l2": "No depth-of-book is used. Resting liquidity walls/cancellations are not observable in this module.",
            },
        }

    def _snapshot_symbol(self, state: SymbolState, now: float) -> dict[str, Any]:
        trades = list(state.trades)
        quotes = list(state.quotes)
        flow60 = [t for t in trades if t.time >= now - 60.0]
        flow15 = [t for t in trades if t.time >= now - 15.0]
        footprint_trades = [t for t in trades if t.time >= now - 300.0]
        split = flow_split(flow60)
        absorption = absorption_scores(flow15)
        exhaustion = exhaustion_scores(trades, now)
        large_score, large_z = robust_large_trade_score(trades)
        quote_score = quote_imbalance(state.bid_size, state.ask_size)
        activity = radar_activity_score(quotes, now)
        price_impulse = self._price_impulse(quotes, trades, now)
        activity_direction = 1.0 if price_impulse > 0 else -1.0 if price_impulse < 0 else 0.0
        composite = (
            0.34 * float(split["pressure"])
            + 0.24 * (float(absorption["bidAbsorption"]) - float(absorption["offerAbsorption"]))
            + 0.16 * large_score
            + 0.10 * quote_score
            + 0.16 * activity_direction * float(activity["score"])
        )
        composite = max(-100.0, min(100.0, composite))
        state_label = self._state_label(split, absorption, exhaustion, composite)
        footprint = build_footprint(footprint_trades, max_levels=60)
        levels = high_volume_levels(footprint, limit=8)
        self._maybe_alert(state, state_label, composite, absorption, now)
        change_pct = None
        if state.last_price is not None and state.previous_close and state.previous_close > 0:
            change_pct = (state.last_price / state.previous_close - 1.0) * 100.0
        spread_bps = None
        if state.bid and state.ask and state.ask >= state.bid:
            mid = (state.bid + state.ask) / 2.0
            spread_bps = 10_000.0 * (state.ask - state.bid) / mid if mid else None
        series_source = quotes[-300:] if quotes else []
        series = [
            {"time": _iso(q.time), "price": q.last if q.last is not None else state.last_price}
            for q in series_source
            if (q.last if q.last is not None else state.last_price) is not None
        ]
        if not series and trades:
            series = [{"time": _iso(t.time), "price": t.price} for t in trades[-300:]]
        return {
            "symbol": state.symbol,
            "status": state.status,
            "dataMode": self._plan.mode.upper(),
            "flowQuality": self._plan.quality,
            "price": state.last_price,
            "previousClose": state.previous_close,
            "changePct": round(change_pct, 3) if change_pct is not None else None,
            "bid": state.bid,
            "ask": state.ask,
            "bidSize": state.bid_size,
            "askSize": state.ask_size,
            "spreadBps": round(spread_bps, 3) if spread_bps is not None else None,
            "volume": state.volume,
            "tradeRate": state.trade_rate,
            "volumeRate": state.volume_rate,
            "flow": {
                **{key: round(value, 3) if isinstance(value, float) else value for key, value in split.items()},
                "cvd": round(sum(t.side * t.size for t in trades if t.side), 3),
                "last60sCvd": round(float(split["delta"]), 3),
                "priceImpulseBps30s": round(price_impulse, 3),
                "quoteImbalance": round(quote_score, 2),
                "largeTradeScore": round(large_score, 2),
                "largeTradeRobustZ": round(large_z, 3) if large_z is not None else None,
                **absorption,
                **exhaustion,
                "activityScore": activity["score"],
                "tradeRateRatio": activity["tradeRateRatio"],
                "volumeRateRatio": activity["volumeRateRatio"],
            },
            "signal": {
                "state": state_label,
                "score": round(composite, 2),
                "confidence": round(self._confidence(state, split), 2),
                "explanation": self._explain(state_label, split, absorption, price_impulse),
            },
            "footprint": footprint,
            "levels": levels,
            "series": series,
            "quality": {
                "lastTradeAt": _iso(state.last_trade_time),
                "quoteAt": _iso(state.quote_time),
                "tradeEvents30m": len(trades),
                "quoteEvents30m": len(quotes),
                "knownFraction60s": round(float(split["knownFraction"]), 3),
                "errors": list(state.errors),
            },
            "recentAlerts": list(state.alerts)[:10],
        }

    @staticmethod
    def _price_impulse(quotes: list[QuoteEvent], trades: list[TradeEvent], now: float) -> float:
        prices = [(q.time, q.last) for q in quotes if q.time >= now - 30.0 and q.last and q.last > 0]
        if len(prices) < 2:
            prices = [(t.time, t.price) for t in trades if t.time >= now - 30.0 and t.price > 0]
        if len(prices) < 2:
            return 0.0
        return 10_000.0 * math.log(prices[-1][1] / prices[0][1])

    @staticmethod
    def _confidence(state: SymbolState, split: dict[str, Any]) -> float:
        event_confidence = min(1.0, float(split["knownCount"]) / 20.0)
        quality = 1.0 if state.status == "LIVE" else 0.55 if state.status in ("FROZEN", "DELAYED") else 0.25
        return 100.0 * event_confidence * quality

    @staticmethod
    def _state_label(split: dict[str, Any], absorption: dict[str, float], exhaustion: dict[str, float], composite: float) -> str:
        if absorption["bidAbsorption"] >= 45 and float(split["pressure"]) <= -20:
            return "BID ABSORPTION"
        if absorption["offerAbsorption"] >= 45 and float(split["pressure"]) >= 20:
            return "OFFER ABSORPTION"
        if exhaustion["sellerExhaustion"] >= 65 and float(split["pressure"]) <= 0:
            return "SELLER EXHAUSTION"
        if exhaustion["buyerExhaustion"] >= 65 and float(split["pressure"]) >= 0:
            return "BUYER EXHAUSTION"
        if composite >= 30:
            return "BUY PRESSURE"
        if composite <= -30:
            return "SELL PRESSURE"
        return "NEUTRAL"

    @staticmethod
    def _explain(state_label: str, split: dict[str, Any], absorption: dict[str, float], price_impulse: float) -> str:
        return (
            f"{state_label}: 60s aggressor pressure {float(split['pressure']):+.1f}; "
            f"15s bid/offer absorption {absorption['bidAbsorption']:.1f}/{absorption['offerAbsorption']:.1f}; "
            f"30s price response {price_impulse:+.1f} bps."
        )

    def _maybe_alert(self, state: SymbolState, label: str, score: float, absorption: dict[str, float], now: float) -> None:
        material = abs(score) >= 55 or max(absorption["bidAbsorption"], absorption["offerAbsorption"]) >= 65
        if not material:
            return
        key = f"{label}:{1 if score >= 0 else -1}"
        if state.last_alert_key == key and now - state.last_alert_at < 45:
            return
        alert = {
            "time": _iso(now),
            "symbol": state.symbol,
            "state": label,
            "score": round(score, 2),
            "price": state.last_price,
            "message": self._explain(label, flow_split([t for t in state.trades if t.time >= now - 60]), absorption, self._price_impulse(list(state.quotes), list(state.trades), now)),
        }
        state.alerts.appendleft(alert)
        state.last_alert_key = key
        state.last_alert_at = now

    def alerts(self, limit: int = 40) -> dict[str, Any]:
        with self._lock:
            rows = []
            for state in self._states.values():
                rows.extend(state.alerts)
            rows.sort(key=lambda item: item["time"], reverse=True)
            return {"alerts": rows[: max(1, int(limit))]}
