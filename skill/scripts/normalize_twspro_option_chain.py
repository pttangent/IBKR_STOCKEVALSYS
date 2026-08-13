#!/usr/bin/env python3
"""Normalize a tws-pro option-chain response into the stock-eval packet schema.

The tws-pro chain currently exposes last/high/low/volume/bars and a reference
price.  It does not expose bid/ask, open interest, or Greeks in this packet, so
the normalized rows deliberately keep those fields null and label the quote
quality as last-trade/aggregate evidence.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path
from typing import Any


def finite(value: Any):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def iso_expiry(value: Any):
    text = str(value or "")
    if len(text) >= 8 and text[:8].isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text[:10] or None


def unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    """Accept a direct result or common MCP wrappers."""
    for key in ("data", "result", "structuredContent"):
        value = payload.get(key)
        if isinstance(value, dict) and isinstance(value.get("chain"), list):
            return value
    return payload


def normalize(payload: dict[str, Any], symbol: str | None = None,
              expiration: str | None = None, as_of: str | None = None) -> dict[str, Any]:
    source = unwrap(payload)
    rows = source.get("chain")
    if not isinstance(rows, list):
        raise ValueError("tws-pro response must contain a chain array")
    out = []
    requested_expiry = expiration or source.get("expiration")
    expiry = iso_expiry(requested_expiry)
    for row in rows:
        if not isinstance(row, dict):
            continue
        right = str(row.get("right", "")).upper()
        option_type = {"C": "call", "P": "put"}.get(right)
        strike = finite(row.get("strike"))
        last = finite(row.get("last"))
        if option_type is None or strike is None:
            continue
        out.append({
            "type": option_type,
            "expiry": expiry,
            "strike": strike,
            "bid": None,
            "ask": None,
            "last": last,
            "high": finite(row.get("high")),
            "low": finite(row.get("low")),
            "close": last,
            "volume": finite(row.get("volume")),
            "open_interest": None,
            "iv": None,
            "delta": None,
            "bar_observations": finite(row.get("bars")),
            "quote_quality": "last_ohlcv_no_bid_ask",
            "source_right": right,
        })
    retrieved = as_of or source.get("retrieved_at") or dt.datetime.now(dt.timezone.utc).isoformat()
    return {
        "provider": "tws-pro-mcp",
        "source_role": "current_or_recent_option_chain",
        "retrieved_at": retrieved,
        "symbol": (symbol or source.get("symbol") or "").upper(),
        "spot": finite(source.get("_ref_price", source.get("spot"))),
        "chain_discovery": {
            "expiration": requested_expiry,
            "strike_count_returned": source.get("strikeCount", len({r["strike"] for r in out})),
            "reference_price_field": "_ref_price" if "_ref_price" in source else "spot",
        },
        "quote_coverage": {
            "contracts_returned": len(out),
            "bid_ask_rows": 0,
            "open_interest_rows": 0,
            "greeks_rows": 0,
        },
        "request": {"normalizer": "normalize_twspro_option_chain.py", "readonly": True},
        "warnings": [
            "tws-pro packet contains last/high/low/volume/bars, not bid/ask/open interest/Greeks",
            "bars is an observation-count field and is not open interest or a trade-direction signal",
            "_ref_price is a provider reference; premarket reports should use a separately timestamped stock close/quote when available",
        ],
        "options": out,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chain", required=True, help="JSON file containing the tws-pro chain response")
    ap.add_argument("--symbol")
    ap.add_argument("--expiration")
    ap.add_argument("--as-of", help="retrieval timestamp to record")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    payload = json.loads(Path(args.chain).read_text(encoding="utf-8"))
    packet = normalize(payload, args.symbol, args.expiration, args.as_of)
    Path(args.out).write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"written": args.out, "symbol": packet["symbol"], "options": len(packet["options"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
