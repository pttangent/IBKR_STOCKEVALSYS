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

def position_size(portfolio_value: float, entry: float, stop: float | None, risk_budget_pct: float = 0.005, concentration_cap_pct: float = 0.05, kelly_fraction: float | None = None, share_step: float = 0.5, targets: list[float] | None = None, stops: list[float] | None = None) -> dict[str, Any]:
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
    return {"status": "sized", "entry": entry, "stop": stop, "stop_distance_pct": 1 - stop / entry, "risk_budget_pct": risk_budget_pct, "concentration_cap_pct": concentration_cap_pct, "shares": max(0, shares), "notional": max(0, shares) * entry, "max_loss_at_stop": max(0, shares) * (entry - stop), "binding_constraint": notional_binding, "shares_by_risk": shares_by_risk, "shares_by_concentration": shares_by_cap, "shares_by_kelly": shares_by_kelly, "allowed_notional": max(0.0, allowed_notional), "integer_shares": integer_shares, "half_share_quantity": half_shares, "exact_fractional_shares": exact_fractional_shares, "integer_notional": integer_shares * entry, "half_share_notional": half_shares * entry, "exact_fractional_notional": exact_fractional_shares * entry, "pnl_ladder": pnl, "kelly": "fractional Kelly cap applied" if kelly_fraction is not None else "Kelly unavailable; fixed-risk and concentration caps applied"}

