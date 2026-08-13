from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Iterable


@dataclass(slots=True)
class SubscriptionPlan:
    symbols: list[str]
    requested_mode: str
    mode: str
    flow_quote_source: str
    market_data_lines: int
    market_data_lines_required: int
    tick_by_tick_slots: int
    tick_by_tick_requests_required: int
    max_flow_symbols: int
    quality: str
    warnings: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


def normalize_symbols(symbols: Iterable[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for raw in symbols:
        symbol = str(raw).strip().upper()
        if symbol and symbol not in seen:
            output.append(symbol)
            seen.add(symbol)
    if not output:
        raise ValueError("at least one symbol is required")
    return output


def build_plan(
    symbols: Iterable[str],
    *,
    mode: str = "auto",
    market_data_lines: int = 100,
    flow_quote_source: str = "mktdata",
    tick_by_tick_ratio: float = 0.05,
) -> SubscriptionPlan:
    symbols = normalize_symbols(symbols)
    requested_mode = mode.lower().strip()
    if requested_mode not in {"auto", "radar", "flow"}:
        raise ValueError("mode must be auto, radar, or flow")
    quote_source = flow_quote_source.lower().strip()
    if quote_source not in {"mktdata", "tick"}:
        raise ValueError("flow_quote_source must be mktdata or tick")
    lines = max(1, int(market_data_lines))
    tbt_slots = max(0, int(math.floor(lines * tick_by_tick_ratio)))
    tbt_per_symbol = 1 if quote_source == "mktdata" else 2
    max_flow = tbt_slots // tbt_per_symbol if tbt_per_symbol else 0

    if requested_mode == "auto":
        actual_mode = "flow" if len(symbols) <= max_flow and max_flow > 0 else "radar"
    else:
        actual_mode = requested_mode

    line_required = len(symbols)
    tbt_required = len(symbols) * tbt_per_symbol if actual_mode == "flow" else 0
    warnings: list[str] = []
    if line_required > lines:
        warnings.append(
            f"{line_required} reqMktData subscriptions exceed the configured {lines} market-data lines; "
            "TWS watchlists and other API subscriptions share the same line pool."
        )
    if actual_mode == "flow" and tbt_required > tbt_slots:
        warnings.append(
            f"Flow mode requires {tbt_required} tick-by-tick requests but the configured allocation permits {tbt_slots}."
        )
    if actual_mode == "flow" and quote_source == "mktdata":
        warnings.append(
            "Trade prints are true tick-by-tick, but aggressor classification uses the latest reqMktData top-of-book snapshot; "
            "this supports up to five symbols on a default 100-line account, but quote timing is not tick-by-tick."
        )
    if actual_mode == "flow" and quote_source == "tick":
        warnings.append(
            "Each fully enriched symbol consumes two tick-by-tick requests (AllLast + BidAsk); with 100 market-data lines, "
            "only two symbols fit while leaving one tick-by-tick slot spare."
        )
    if actual_mode == "radar":
        warnings.append(
            "Radar mode uses reqMktData/RTVolume-style snapshots. Order-flow and footprint fields are proxies, not complete Time & Sales."
        )

    quality = (
        "TBT_TRADES_TBT_QUOTES"
        if actual_mode == "flow" and quote_source == "tick"
        else "TBT_TRADES_MKTDATA_QUOTES"
        if actual_mode == "flow"
        else "MKTDATA_SNAPSHOT_PROXY"
    )
    return SubscriptionPlan(
        symbols=symbols,
        requested_mode=requested_mode,
        mode=actual_mode,
        flow_quote_source=quote_source,
        market_data_lines=lines,
        market_data_lines_required=line_required,
        tick_by_tick_slots=tbt_slots,
        tick_by_tick_requests_required=tbt_required,
        max_flow_symbols=max_flow,
        quality=quality,
        warnings=warnings,
    )
