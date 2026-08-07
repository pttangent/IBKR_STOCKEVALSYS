#!/usr/bin/env python3
"""Deterministic backtest and Kelly diagnostics."""
from __future__ import annotations

import math
from typing import Any

from stock_eval_core import f, rsi

def backtest_rsi(bars: list[dict[str, Any]], entry_rsi: float = 30, exit_rsi: float = 55, cost_bps: float = 5, max_hold: int = 10) -> dict[str, Any]:
    closes = [x["close"] for x in bars]
    if len(closes) < 40:
        return {"status": "unavailable", "reason": "needs at least 40 bars"}
    trades, entry = [], None
    for i in range(15, len(closes)):
        current_rsi = rsi(closes[: i + 1])
        if entry is None and current_rsi is not None and current_rsi < entry_rsi:
            entry = (i, closes[i])
        elif entry is not None:
            held = i - entry[0]
            if (current_rsi is not None and current_rsi > exit_rsi) or held >= max_hold or i == len(closes) - 1:
                gross = closes[i] / entry[1] - 1
                net = gross - 2 * cost_bps / 10000
                trades.append({"entry_date": bars[entry[0]]["date"], "exit_date": bars[i]["date"], "return": net, "hold_bars": held})
                entry = None
    returns = [x["return"] for x in trades]
    wins = [x for x in returns if x > 0]
    losses = [x for x in returns if x <= 0]
    return {"status": "ok", "rule": "RSI(14)<30 entry; RSI(14)>55, 10 bars, or end exit", "trades": len(trades), "win_rate": len(wins) / len(returns) if returns else None, "avg_win": sum(wins) / len(wins) if wins else None, "avg_loss": abs(sum(losses) / len(losses)) if losses else None, "total_return": math.prod(1 + x for x in returns) - 1 if returns else 0, "cost_bps_each_side": cost_bps, "trade_log": trades}

def _log_growth(fraction: float, returns: list[float]) -> float | None:
    if not returns or any(1 + fraction * r <= 0 for r in returns):
        return None
    return sum(math.log(1 + fraction * r) for r in returns) / len(returns)

def _grid_kelly(returns: list[float], upper: float = 1.0) -> dict[str, Any]:
    """Unlevered log-growth maximizer over a transparent fractional grid."""
    clean = [r for r in returns if math.isfinite(r) and r > -1]
    if not clean:
        return {"status": "unavailable", "reason": "no valid trade returns"}
    best_f, best_g = 0.0, _log_growth(0.0, clean) or 0.0
    for i in range(1, int(upper * 1000) + 1):
        candidate = i / 1000.0
        growth = _log_growth(candidate, clean)
        if growth is not None and growth > best_g:
            best_f, best_g = candidate, growth
    return {"status": "ok", "trades": len(clean), "kelly_fraction": best_f,
            "mean_log_growth": best_g, "grid_step": 0.001, "fraction_cap": upper,
            "at_grid_cap": best_f >= upper}

def _formula_kelly(returns: list[float]) -> dict[str, Any]:
    """Return the transparent p/b Kelly diagnostic alongside the log-growth grid."""
    clean = [r for r in returns if math.isfinite(r) and r > -1]
    wins = [r for r in clean if r > 0]
    losses = [abs(r) for r in clean if r <= 0]
    p = len(wins) / len(clean) if clean else None
    avg_win = sum(wins) / len(wins) if wins else None
    avg_loss = sum(losses) / len(losses) if losses else None
    b = avg_win / avg_loss if avg_win is not None and avg_loss and avg_loss > 0 else None
    f_raw = ((p * b) - (1 - p)) / b if p is not None and b is not None and b > 0 else None
    return {"trades": len(clean), "p_win_rate": p, "b_avg_win_over_avg_loss": b,
            "avg_win": avg_win, "avg_loss": avg_loss,
            "raw_formula_kelly_fraction": f_raw}

def _kelly_sample_confidence(total: int, oos: int, minimum_total: int, minimum_oos: int,
                             conditional_total: int, conditional_oos: int) -> dict[str, Any]:
    """Return a transparent sample-size confidence label, not a win probability."""
    if total >= minimum_total and oos >= minimum_oos:
        label, tier = "medium", "standard_validated"
    elif total >= conditional_total and oos >= conditional_oos:
        label, tier = "low", "conditional_tactical"
    elif total >= 10:
        label, tier = "low", "exploratory"
    else:
        label, tier = "very_low", "exploratory"
    reasons = [f"{total} total completed trades", f"{oos} reserved/observed OOS trades"]
    if total < minimum_total:
        reasons.append(f"standard tier needs {minimum_total} total trades")
    if oos < minimum_oos:
        reasons.append(f"standard tier needs {minimum_oos} OOS trades")
    return {"label": label, "tier": tier, "reasons": reasons,
            "is_validated": tier == "standard_validated"}

def kelly_analysis(backtest: dict[str, Any], options: dict[str, Any] | None = None,
                   realized_vol: float | None = None, fractional: float = 0.25,
                   qualification: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return exploratory, conditional, and standard Kelly diagnostics.

    The empirical edge comes from the supplied fixed-rule trade returns. Options
    only supply a conservative volatility/event haircut; they do not create
    directional edge or real-world probabilities. Small samples still receive
    a diagnostic number and confidence label, but only the standard tier is
    eligible to become an automatic position cap.
    """
    returns = [f(x.get("return")) for x in backtest.get("trade_log", []) if isinstance(x, dict)]
    returns = [x for x in returns if x is not None]
    full = _grid_kelly(returns)
    full_formula = _formula_kelly(returns)
    config = qualification or {}
    minimum_oos = int(config.get("minimum_oos", 30))
    minimum_total = int(config.get("minimum_total", 60))
    conditional_oos = int(config.get("conditional_oos", 10))
    conditional_total = int(config.get("conditional_total", 20))

    oos = {"status": "insufficient_oos", "trades": 0, "required_trades": minimum_oos,
           "reason": f"need at least {minimum_total} total trades to reserve a standard out-of-sample block"}
    oos_status = "insufficient_oos"
    if len(returns) >= minimum_total:
        oos_count = max(minimum_oos, math.ceil(len(returns) * 0.30))
        oos = _grid_kelly(returns[-oos_count:])
        oos_formula = _formula_kelly(returns[-oos_count:])
        oos_status = "qualified" if oos.get("trades", 0) >= minimum_oos else "insufficient_oos"
    elif len(returns) >= conditional_total:
        oos_count = max(conditional_oos, math.ceil(len(returns) * 0.30))
        oos = _grid_kelly(returns[-oos_count:])
        oos_formula = _formula_kelly(returns[-oos_count:])
        oos["tier"] = "conditional_tactical"
        oos_status = "conditional" if oos.get("trades", 0) >= conditional_oos else "insufficient_oos"
    else:
        oos_formula = {"trades": 0, "p_win_rate": None, "b_avg_win_over_avg_loss": None,
                       "avg_win": None, "avg_loss": None, "raw_formula_kelly_fraction": None}

    exploratory_fraction = full.get("kelly_fraction") if full.get("status") == "ok" else None
    conditional_fraction = oos.get("kelly_fraction") if oos_status in {"qualified", "conditional"} else None
    base_fraction = oos.get("kelly_fraction") if oos_status == "qualified" else None
    exploratory_formula_fraction = full_formula.get("raw_formula_kelly_fraction")
    conditional_formula_fraction = oos_formula.get("raw_formula_kelly_fraction") if oos_status in {"qualified", "conditional"} else None
    sample_confidence = _kelly_sample_confidence(len(returns), oos.get("trades", 0), minimum_total,
                                                 minimum_oos, conditional_total, conditional_oos)

    option_overlay = {"status": "not_applied", "reason": "no option evidence supplied"}
    adjusted_fraction = base_fraction
    exploratory_adjusted_fraction = exploratory_fraction
    conditional_adjusted_fraction = conditional_fraction
    exploratory_formula_adjusted = exploratory_formula_fraction
    conditional_formula_adjusted = conditional_formula_fraction
    if options is not None:
        iv = f(options.get("atm_iv"))
        event = ((options.get("term_structure") or {}).get("interpretation") == "event-rich/front-loaded")
        iv_haircut = min(1.0, realized_vol / iv) if realized_vol and iv and iv > 0 else None
        event_haircut = 0.50 if event else 1.0
        usable_haircuts = [x for x in (iv_haircut, event_haircut) if x is not None]
        overlay = min(usable_haircuts) if usable_haircuts else None
        if overlay is not None:
            if base_fraction is not None:
                adjusted_fraction = max(0.0, base_fraction * overlay)
            if conditional_fraction is not None:
                conditional_adjusted_fraction = max(0.0, conditional_fraction * overlay)
            if exploratory_fraction is not None:
                exploratory_adjusted_fraction = max(0.0, exploratory_fraction * overlay)
            if exploratory_formula_fraction is not None:
                exploratory_formula_adjusted = max(0.0, exploratory_formula_fraction * overlay)
            if conditional_formula_fraction is not None:
                conditional_formula_adjusted = max(0.0, conditional_formula_fraction * overlay)
        option_overlay = {"status": "applied" if overlay is not None else "partial",
                          "atm_iv": iv, "iv_status": options.get("atm_iv_status"),
                          "realized_vol_20d": realized_vol, "iv_to_realized_haircut": iv_haircut,
                          "event_front_loaded": event, "event_haircut": event_haircut,
                          "combined_haircut": overlay,
                          "interpretation": "risk haircut only; option IV is risk-neutral and does not supply directional alpha"}
    full_fraction = adjusted_fraction if adjusted_fraction is not None else None
    half_fraction = (full_fraction * 0.50) if full_fraction is not None else None
    quarter_fraction = (full_fraction * 0.25) if full_fraction is not None else None
    fractional_fraction = (adjusted_fraction * fractional) if adjusted_fraction is not None else None
    exploratory_fractional = (exploratory_adjusted_fraction * fractional) if exploratory_adjusted_fraction is not None else None
    conditional_fractional = (conditional_adjusted_fraction * fractional) if conditional_adjusted_fraction is not None else None
    exploratory_formula_fractional = (exploratory_formula_adjusted * fractional) if exploratory_formula_adjusted is not None else None
    conditional_formula_fractional = (conditional_formula_adjusted * fractional) if conditional_formula_adjusted is not None else None
    concentration_cap_pct = float(config.get("concentration_cap_pct", 0.05))
    diagnostic_fraction = conditional_formula_adjusted if conditional_formula_adjusted is not None else exploratory_formula_adjusted
    diagnostic_kelly_scenarios = {}
    if diagnostic_fraction is not None:
        for label, multiplier in (("full", 1.0), ("half", 0.50), ("quarter", 0.25)):
            fraction_value = diagnostic_fraction * multiplier
            diagnostic_kelly_scenarios[label] = {
                "multiplier": multiplier,
                "fraction": fraction_value,
                "concentration_capped_fraction": min(fraction_value, concentration_cap_pct),
            }
    diagnostic_final_cap = (diagnostic_kelly_scenarios.get("quarter", {}).get("concentration_capped_fraction")
                            if diagnostic_kelly_scenarios else None)
    limitations = [
        "Kelly edge is estimated from the deterministic RSI trade log, not from a fundamental or discretionary stock thesis",
        "standard validation requires at least 60 total trades and at least 30 reserved OOS trades",
        "short samples produce exploratory/conditional diagnostics with low confidence; they are not validated Kelly",
        "options IV changes the risk haircut only; it cannot identify direction, expected return, or real-world probability",
        "the result is an unlevered capital-fraction upper bound and must still be capped by stop loss, concentration, liquidity, and mandate",
    ]
    if options is not None and options.get("quote_quality_counts", {}).get("bid_ask_mid", 0) == 0:
        limitations.append("option overlay uses last/model IV because no executable bid/ask rows were available")
    if full.get("at_grid_cap") or oos.get("at_grid_cap"):
        limitations.append("Kelly optimizer reached its diagnostic grid cap; do not interpret the cap as a precise fraction")
    return {"status": "qualified" if oos_status == "qualified" else "conditional_insufficient_data",
            "method": "empirical log-growth Kelly on fixed-rule trade returns plus conservative option-risk haircut",
            "full_sample": full, "full_sample_formula": full_formula,
            "out_of_sample": oos, "out_of_sample_formula": oos_formula,
            "exploratory_full_sample_kelly_fraction": exploratory_fraction,
            "conditional_oos_kelly_fraction": conditional_fraction,
            "raw_oos_kelly_fraction": base_fraction,
            "exploratory_formula_kelly_fraction": exploratory_formula_fraction,
            "conditional_formula_kelly_fraction": conditional_formula_fraction,
            "option_risk_overlay": option_overlay, "fractional_kelly_multiplier": fractional,
            "full_kelly_fraction": full_fraction,
            "half_kelly_fraction": half_fraction,
            "quarter_kelly_fraction": quarter_fraction,
            "exploratory_fractional_kelly_fraction": exploratory_fractional,
            "conditional_fractional_kelly_fraction": conditional_fractional,
            "exploratory_formula_fractional_kelly_fraction": exploratory_formula_fractional,
            "conditional_formula_fractional_kelly_fraction": conditional_formula_fractional,
            "fractional_kelly_fraction": fractional_fraction,
            "diagnostic_fractional_kelly_cap": diagnostic_final_cap,
            "diagnostic_kelly_scenarios": diagnostic_kelly_scenarios,
            "diagnostic_cap_inputs": {"concentration_cap_pct": concentration_cap_pct,
                                      "source": "conditional OOS formula Kelly when available, else full-sample formula Kelly",
                                      "status": "diagnostic_only_until_standard_oos_qualified"},
            "sample_confidence": sample_confidence,
            "qualification": {"standard_total": minimum_total, "standard_oos": minimum_oos,
                               "conditional_total": conditional_total, "conditional_oos": conditional_oos},
            "applied_to_position": fractional_fraction is not None,
            "sizing_decision": "apply_validated_fractional_kelly_as_cap" if fractional_fraction is not None else "show_diagnostic_use_fixed_risk_by_default",
            "limitations": limitations}
