#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent))
from research_http import request_json, source_packet, write_json

SEARCH_URL = "https://gamma-api.polymarket.com/public-search"


def _maybe_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def normalize_market(market: dict[str, Any]) -> dict[str, Any]:
    outcomes = _maybe_json(market.get("outcomes"))
    prices = _maybe_json(market.get("outcomePrices"))
    paired = []
    if isinstance(outcomes, list) and isinstance(prices, list):
        for outcome, price in zip(outcomes, prices):
            try:
                p = float(price)
            except (TypeError, ValueError):
                p = None
            paired.append({"outcome": outcome, "market_implied_probability": p})
    return {
        "id": market.get("id"),
        "question": market.get("question"),
        "slug": market.get("slug"),
        "active": market.get("active"),
        "closed": market.get("closed"),
        "end_date": market.get("endDate") or market.get("endDateIso"),
        "outcomes": paired,
        "last_trade_price": market.get("lastTradePrice"),
        "best_bid": market.get("bestBid"),
        "best_ask": market.get("bestAsk"),
        "liquidity": market.get("liquidityNum") or market.get("liquidity"),
        "volume": market.get("volumeNum") or market.get("volume"),
        "spread": market.get("spread"),
        "label": "MARKET_IMPLIED_EXPECTATION",
    }


def normalize_search(payload: dict[str, Any], limit: int) -> dict[str, Any]:
    events = []
    for event in (payload.get("events") or [])[:limit]:
        events.append(
            {
                "id": event.get("id"),
                "title": event.get("title"),
                "slug": event.get("slug"),
                "description": event.get("description"),
                "active": event.get("active"),
                "closed": event.get("closed"),
                "end_date": event.get("endDate"),
                "liquidity": event.get("liquidity"),
                "volume": event.get("volume"),
                "open_interest": event.get("openInterest"),
                "markets": [normalize_market(m) for m in (event.get("markets") or [])],
            }
        )
    return {"events": events, "pagination": payload.get("pagination")}


def main() -> None:
    ap = argparse.ArgumentParser(description="Search public Polymarket events for optional catalyst context.")
    ap.add_argument("--query", required=True)
    ap.add_argument("--as-of", help="Metadata only; current Polymarket search is not historical PIT replay data")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    params = {
        "q": args.query,
        "limit_per_type": max(1, min(args.limit, 50)),
        "keep_closed_markets": 0,
        "search_profiles": "false",
    }
    url = f"{SEARCH_URL}?{urlencode(params)}"
    payload = request_json(url)
    as_of = args.as_of or date.today().isoformat()
    packet = source_packet(
        provider="POLYMARKET",
        source_type="prediction_market_search",
        source_id=f"polymarket:{args.query}:{as_of}",
        as_of=as_of,
        available_at=None,
        reliability="market_implied_secondary",
        source_url=url,
        data={"query": args.query, **normalize_search(payload, args.limit)},
        warnings=[
            "Prediction-market prices are market-implied beliefs, not factual probabilities or company fundamentals.",
            "Current search results are not PIT-safe for historical replay unless separately snapshotted at decision time.",
            "Only use markets whose resolution question is materially linked to the stock thesis; skip irrelevant search matches.",
        ],
    )
    write_json(args.output, packet)
    print(f"OK Polymarket query={args.query!r} events={len(packet['data']['events'])} -> {args.output}")


if __name__ == "__main__":
    main()
