#!/usr/bin/env python3
"""Public deterministic façade for the stock-eval-system calculation layer."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from stock_eval_core import (
    atr, bs_price, ema_series, expiry_years, f, implied_vol, load_json,
    norm_options, normalize_bars, option_analysis, rsi, sma, technical_analysis,
    term_structure,
)
from stock_eval_kelly import backtest_rsi, kelly_analysis
from stock_eval_position import pnl_ladder, position_size

def evaluate(symbol: str, bars_payload: Any, front_payload: Any | None = None, back_payload: Any | None = None, as_of: str | None = None, portfolio_value: float | None = None, stop: float | None = None) -> dict[str, Any]:
    bars = normalize_bars(bars_payload)
    tech = technical_analysis(bars)
    out: dict[str, Any] = {"symbol": symbol.upper(), "as_of": as_of or tech["as_of"], "data": {"bars": len(bars), "last_price": tech["last_price"]}, "technical": tech, "backtest": backtest_rsi(bars)}
    if front_payload is not None:
        opt = option_analysis(front_payload, tech["last_price"], as_of or tech["as_of"])
        if back_payload is not None:
            opt["term_structure"] = term_structure(front_payload, back_payload, tech["last_price"], as_of or tech["as_of"])
        out["options"] = opt
    else:
        out["options"] = {"status": "not_requested"}
    out["kelly"] = kelly_analysis(out["backtest"], out.get("options") if front_payload is not None else None, tech.get("realized_vol_20d_annualized"))
    if portfolio_value is not None:
        out["position"] = position_size(portfolio_value, tech["last_price"], stop, kelly_fraction=out["kelly"].get("fractional_kelly_fraction"))
    else:
        out["position"] = {"status": "not_requested"}
    out["research_posture"] = {"evidence_completeness": "technical-only" if front_payload is None else "technical-plus-options", "underwriting_status": "preliminary; fundamentals, filings, catalysts, and valuation inputs are external evidence modules", "recommendation": "none"}
    return out

def main() -> None:
    ap = argparse.ArgumentParser(description="Read-only deterministic stock evaluation engine")
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--options-front")
    ap.add_argument("--options-back")
    ap.add_argument("--as-of")
    ap.add_argument("--portfolio-value", type=float)
    ap.add_argument("--stop", type=float)
    ap.add_argument("--out")
    args = ap.parse_args()
    result = evaluate(args.symbol, load_json(args.data), load_json(args.options_front) if args.options_front else None, load_json(args.options_back) if args.options_back else None, args.as_of, args.portfolio_value, args.stop)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)

if __name__ == "__main__":
    main()

