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
from stock_eval_kelly import backtest_rsi, kelly_analysis, realized_vol_reference
from stock_eval_position import kelly_position_guidance, pnl_ladder, position_size


def evaluate(symbol: str, bars_payload: Any, front_payload: Any | None = None,
             back_payload: Any | None = None, as_of: str | None = None,
             portfolio_value: float | None = None, stop: float | None = None,
             risk_budget_pct: float = 0.005, concentration_cap_pct: float = 0.05,
             current_setup_id: str | None = None,
             setup_match_status: str | None = None) -> dict[str, Any]:
    bars = normalize_bars(bars_payload)
    tech = technical_analysis(bars)
    backtest = backtest_rsi(bars)
    rv_context = realized_vol_reference(bars)
    out: dict[str, Any] = {
        "symbol": symbol.upper(),
        "as_of": as_of or tech["as_of"],
        "data": {"bars": len(bars), "last_price": tech["last_price"]},
        "technical": tech,
        "backtest": backtest,
        "volatility_context": rv_context,
    }
    if front_payload is not None:
        opt = option_analysis(front_payload, tech["last_price"], as_of or tech["as_of"])
        if back_payload is not None:
            opt["term_structure"] = term_structure(front_payload, back_payload, tech["last_price"], as_of or tech["as_of"])
        out["options"] = opt
    else:
        out["options"] = {"status": "not_requested"}

    setup_context = {
        "current_setup_id": current_setup_id,
        "backtest_setup_id": backtest.get("setup_id"),
        "setup_match_status": setup_match_status or ("exact" if current_setup_id and current_setup_id == backtest.get("setup_id") else "unknown"),
    }
    out["kelly"] = kelly_analysis(
        backtest,
        out.get("options") if front_payload is not None else None,
        tech.get("realized_vol_20d_annualized"),
        qualification={"concentration_cap_pct": concentration_cap_pct},
        realized_vol_reference=rv_context.get("reference_median_prior_windows") if rv_context.get("status") == "ok" else None,
        setup_context=setup_context,
    )

    simulation_value = portfolio_value if portfolio_value is not None else 10000.0
    portfolio_source = "user_provided" if portfolio_value is not None else "default_10000_simulation"
    out["position_guidance"] = kelly_position_guidance(
        out["kelly"], tech["last_price"], simulation_value, stop=stop,
        risk_budget_pct=risk_budget_pct, concentration_cap_pct=concentration_cap_pct,
        portfolio_value_source=portfolio_source,
    )

    if portfolio_value is not None:
        out["position"] = position_size(
            portfolio_value, tech["last_price"], stop,
            risk_budget_pct=risk_budget_pct,
            concentration_cap_pct=concentration_cap_pct,
            kelly_fraction=out["kelly"].get("fractional_kelly_fraction"),
        )
    else:
        out["position"] = {"status": "not_requested",
                           "note": "position_guidance still provides a labeled $10,000 simulation"}
    out["research_posture"] = {
        "evidence_completeness": "technical-only" if front_payload is None else "technical-plus-options",
        "underwriting_status": "preliminary; fundamentals, filings, catalysts, and valuation inputs are external evidence modules",
        "recommendation": "none",
    }
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
    ap.add_argument("--risk-budget-pct", type=float, default=0.005)
    ap.add_argument("--concentration-cap-pct", type=float, default=0.05)
    ap.add_argument("--current-setup-id")
    ap.add_argument("--setup-match-status", choices=["exact", "compatible", "proxy", "mismatch", "unknown"])
    ap.add_argument("--out")
    args = ap.parse_args()
    result = evaluate(
        args.symbol,
        load_json(args.data),
        load_json(args.options_front) if args.options_front else None,
        load_json(args.options_back) if args.options_back else None,
        args.as_of,
        args.portfolio_value,
        args.stop,
        args.risk_budget_pct,
        args.concentration_cap_pct,
        args.current_setup_id,
        args.setup_match_status,
    )
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)


if __name__ == "__main__":
    main()
