#!/usr/bin/env python3
"""Deterministic risk-budget position sizing and P/L ladders."""
from __future__ import annotations

import math
from typing import Any

from stock_eval_core import f


def _floor_to_step(value: float, step: float) -> float:
    return math.floor(max(0.0, value) / step + 1e-12) * step


def pnl_ladder(entry: float, stops: list[float] | None = None, targets: list[float] | None = None,
               integer_shares: float = 0.0, half_shares: float = 0.0,
               risk_budget_dollars: float | None = None,
               exact_fractional_shares: float | None = None) -> dict[str, Any]:
    """Return transparent per-share and account P/L for stop/target levels."""
    if entry <= 0:
        return {"status": "not_calculated", "reason": "entry must be positive"}
    rows: list[dict[str, Any]] = []
    for kind, levels in (("stop", stops or []), ("target", targets or [])):
        for level in levels:
            price = f(level)
            if price is None or price <= 0:
                continue
            per_share = price - entry
            integer_pnl = per_share * integer_shares
            half_pnl = per_share * half_shares
            exact_shares = half_shares if exact_fractional_shares is None else exact_fractional_shares
            exact_pnl = per_share * exact_shares
            row = {"type": kind, "price": price, "per_share_pnl": per_share,
                   "integer_shares": integer_shares,
                   "integer_pnl": integer_pnl,
                   "half_shares": half_shares,
                   "half_pnl": half_pnl,
                   "exact_fractional_shares": exact_shares,
                   "exact_fractional_pnl": exact_pnl}
            if kind == "stop" and risk_budget_dollars is not None:
                row["integer_risk_cap_exceeded"] = abs(min(0.0, integer_pnl)) > risk_budget_dollars
                row["half_risk_cap_exceeded"] = abs(min(0.0, half_pnl)) > risk_budget_dollars
            rows.append(row)
    return {"status": "ok", "entry": entry, "rows": rows}


def position_size(portfolio_value: float, entry: float, stop: float | None, risk_budget_pct: float = 0.005,
                  concentration_cap_pct: float = 0.05, kelly_fraction: float | None = None,
                  share_step: float = 0.5, targets: list[float] | None = None,
                  stops: list[float] | None = None) -> dict[str, Any]:
    if stop is None or entry <= 0 or stop <= 0 or stop >= entry:
        return {"status": "not_sized", "reason": "provide a valid stop below entry; no stop is invented"}
    risk_dollars = portfolio_value * risk_budget_pct
    shares_by_risk = math.floor(risk_dollars / (entry - stop))
    shares_by_cap = math.floor(portfolio_value * concentration_cap_pct / entry)
    shares_by_kelly = math.floor(portfolio_value * kelly_fraction / entry) if kelly_fraction is not None else None
    constraints = [(shares_by_risk, "risk_budget"), (shares_by_cap, "concentration_cap")]
    if shares_by_kelly is not None:
        constraints.append((shares_by_kelly, "fractional_kelly"))
    notional_constraints = [(risk_dollars * entry / (entry - stop), "risk_budget"),
                            (portfolio_value * concentration_cap_pct, "concentration_cap")]
    if kelly_fraction is not None:
        notional_constraints.append((portfolio_value * kelly_fraction, "fractional_kelly"))
    allowed_notional, notional_binding = min(notional_constraints, key=lambda x: x[0])
    shares, _ = min(constraints, key=lambda x: x[0])
    integer_shares = math.floor(min(shares_by_risk, shares_by_cap, shares_by_kelly if shares_by_kelly is not None else float("inf")))
    half_shares = _floor_to_step(allowed_notional / entry, share_step)
    exact_fractional_shares = max(0.0, allowed_notional / entry)
    stop_levels = stops if stops is not None else [stop]
    pnl = pnl_ladder(entry, stop_levels, targets or [], integer_shares, half_shares,
                     risk_budget_dollars=risk_dollars,
                     exact_fractional_shares=exact_fractional_shares)
    return {"status": "sized", "entry": entry, "stop": stop,
            "stop_distance_pct": 1 - stop / entry, "risk_budget_pct": risk_budget_pct,
            "concentration_cap_pct": concentration_cap_pct, "shares": max(0, shares),
            "notional": max(0, shares) * entry, "max_loss_at_stop": max(0, shares) * (entry - stop),
            "binding_constraint": notional_binding, "shares_by_risk": shares_by_risk,
            "shares_by_concentration": shares_by_cap, "shares_by_kelly": shares_by_kelly,
            "allowed_notional": max(0.0, allowed_notional), "integer_shares": integer_shares,
            "half_share_quantity": half_shares, "exact_fractional_shares": exact_fractional_shares,
            "integer_notional": integer_shares * entry, "half_share_notional": half_shares * entry,
            "exact_fractional_notional": exact_fractional_shares * entry, "pnl_ladder": pnl,
            "kelly": "fractional Kelly cap applied" if kelly_fraction is not None else "Kelly unavailable; fixed-risk and concentration caps applied"}


def kelly_position_guidance(kelly: dict[str, Any], entry: float, portfolio_value: float = 10000.0,
                            stop: float | None = None, risk_budget_pct: float = 0.005,
                            concentration_cap_pct: float = 0.05, share_step: float = 0.5,
                            portfolio_value_source: str = "default_10000_simulation") -> dict[str, Any]:
    """Translate Kelly/RV diagnostics into inspectable full/half/quarter $10k guidance.

    The function intentionally returns a guide even when Kelly is conditional or
    exploratory. Validation status stays visible. If Kelly is mathematically
    unavailable but a valid stop exists, it falls back to fixed-risk/concentration
    sizing and labels the result risk-only rather than Kelly.
    """
    if portfolio_value <= 0 or entry <= 0:
        return {"status": "unavailable", "reason": "portfolio_value and entry must be positive"}

    rv_overlay = kelly.get("rv_regime_overlay", {}) or {}
    current_rv = f(rv_overlay.get("current_realized_vol_20d_annualized"))
    daily_sigma = f(rv_overlay.get("daily_sigma"))
    if daily_sigma is None and current_rv is not None and current_rv > 0:
        daily_sigma = current_rv / math.sqrt(252)

    stop_distance_pct = None
    stop_risk_cap_fraction = None
    if stop is not None and stop > 0 and stop < entry:
        stop_distance_pct = (entry - stop) / entry
        stop_risk_cap_fraction = risk_budget_pct / stop_distance_pct if stop_distance_pct > 0 else None

    scenarios = kelly.get("guidance_kelly_scenarios", {}) or {}
    if not scenarios:
        legacy = kelly.get("diagnostic_kelly_scenarios", {}) or {}
        for label in ("full", "half", "quarter"):
            item = legacy.get(label, {}) if isinstance(legacy, dict) else {}
            fraction = f(item.get("fraction"))
            if fraction is not None and fraction > 0:
                scenarios[label] = {"multiplier": item.get("multiplier"), "base_edge_fraction": None,
                                    "combined_risk_haircut": None, "post_overlay_fraction": fraction,
                                    "source": "legacy_diagnostic"}

    variants: dict[str, Any] = {}
    for label in ("full", "half", "quarter"):
        item = scenarios.get(label, {}) if isinstance(scenarios, dict) else {}
        theoretical = f(item.get("post_overlay_fraction", item.get("fraction")))
        if theoretical is None or theoretical <= 0:
            continue
        caps = [(theoretical, "kelly_after_risk_overlay"), (concentration_cap_pct, "concentration_cap")]
        if stop_risk_cap_fraction is not None:
            caps.append((stop_risk_cap_fraction, "stop_risk_cap"))
        final_fraction, binding = min(caps, key=lambda pair: pair[0])
        notional = portfolio_value * final_fraction
        exact_shares = notional / entry
        variants[label] = {
            "multiplier": item.get("multiplier"),
            "theoretical_post_overlay_fraction": theoretical,
            "final_fraction": final_fraction,
            "binding_constraint": binding,
            "notional_dollars": notional,
            "exact_fractional_shares": exact_shares,
            "whole_shares": math.floor(exact_shares),
            "half_share_quantity": _floor_to_step(exact_shares, share_step),
            "one_day_one_sigma_nav_fraction": final_fraction * daily_sigma if daily_sigma is not None else None,
            "one_day_one_sigma_dollars": portfolio_value * final_fraction * daily_sigma if daily_sigma is not None else None,
            "stop_loss_dollars": exact_shares * (entry - stop) if stop_distance_pct is not None else None,
            "caps": {"concentration_cap_fraction": concentration_cap_pct,
                     "stop_risk_cap_fraction": stop_risk_cap_fraction},
        }

    if variants:
        guidance_variant = "quarter" if "quarter" in variants else min(variants, key=lambda key: variants[key]["final_fraction"])
        selected = variants[guidance_variant]
        guidance_status = kelly.get("guidance_status") or "diagnostic"
        return {
            "status": "guidance_available",
            "guidance_status": guidance_status,
            "guidance_variant": guidance_variant,
            "portfolio_value": portfolio_value,
            "portfolio_value_source": portfolio_value_source,
            "simulation_label": "$10,000 SIMULATION" if portfolio_value_source == "default_10000_simulation" else "USER PORTFOLIO",
            "entry": entry,
            "stop": stop,
            "risk_budget_pct": risk_budget_pct,
            "risk_budget_dollars": portfolio_value * risk_budget_pct,
            "concentration_cap_pct": concentration_cap_pct,
            "stop_distance_pct": stop_distance_pct,
            "stop_risk_cap_fraction": stop_risk_cap_fraction,
            "current_realized_vol_20d_annualized": current_rv,
            "daily_sigma": daily_sigma,
            "setup_match": kelly.get("setup_match", {}),
            "sample_confidence": kelly.get("sample_confidence", {}),
            "selected_edge": kelly.get("selected_edge", {}),
            "risk_overlay_combination": kelly.get("risk_overlay_combination", {}),
            "variants": variants,
            "guidance_fraction": selected["final_fraction"],
            "guidance_notional_dollars": selected["notional_dollars"],
            "guidance_exact_fractional_shares": selected["exact_fractional_shares"],
            "guidance_binding_constraint": selected["binding_constraint"],
            "interpretation": "quarter Kelly is the conservative report guide; full/half remain visible diagnostics. Portfolio caps can bind below every Kelly variant.",
        }

    if stop_risk_cap_fraction is not None:
        final_fraction = min(stop_risk_cap_fraction, concentration_cap_pct)
        binding = "stop_risk_cap" if stop_risk_cap_fraction <= concentration_cap_pct else "concentration_cap"
        notional = portfolio_value * final_fraction
        shares = notional / entry
        return {
            "status": "risk_only_fallback",
            "guidance_status": "risk_only_no_positive_kelly_edge",
            "guidance_variant": "risk_only",
            "portfolio_value": portfolio_value,
            "portfolio_value_source": portfolio_value_source,
            "simulation_label": "$10,000 SIMULATION" if portfolio_value_source == "default_10000_simulation" else "USER PORTFOLIO",
            "entry": entry,
            "stop": stop,
            "risk_budget_pct": risk_budget_pct,
            "risk_budget_dollars": portfolio_value * risk_budget_pct,
            "concentration_cap_pct": concentration_cap_pct,
            "stop_distance_pct": stop_distance_pct,
            "stop_risk_cap_fraction": stop_risk_cap_fraction,
            "current_realized_vol_20d_annualized": current_rv,
            "daily_sigma": daily_sigma,
            "variants": {},
            "guidance_fraction": final_fraction,
            "guidance_notional_dollars": notional,
            "guidance_exact_fractional_shares": shares,
            "guidance_binding_constraint": binding,
            "interpretation": "No positive Kelly edge was available; this is fixed-risk/concentration guidance only, not Kelly.",
        }

    return {
        "status": "unavailable",
        "guidance_status": "severe_data_gap",
        "portfolio_value": portfolio_value,
        "portfolio_value_source": portfolio_value_source,
        "simulation_label": "$10,000 SIMULATION" if portfolio_value_source == "default_10000_simulation" else "USER PORTFOLIO",
        "entry": entry,
        "stop": stop,
        "current_realized_vol_20d_annualized": current_rv,
        "daily_sigma": daily_sigma,
        "reason": "no positive Kelly diagnostic and no valid stop for risk-only sizing",
    }
