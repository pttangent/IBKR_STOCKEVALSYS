#!/usr/bin/env python3
"""Compute deterministic gross gamma structure without pretending dealer position sign is known."""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

from options_chain_features import expiry_years, implied_vol, num


def normal_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def bs_gamma(spot: float, strike: float, years: float, sigma: float) -> float | None:
    if min(spot, strike, years, sigma) <= 0:
        return None
    root_t = math.sqrt(years)
    d1 = (math.log(spot / strike) + 0.5 * sigma * sigma * years) / (sigma * root_t)
    return normal_pdf(d1) / (spot * sigma * root_t)


def ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def pick_iv(row: dict, spot: float, years: float, provider: str | None = None) -> tuple[float | None, str | None]:
    provider_iv = num(row.get("iv"))
    last_iv = implied_vol(row.get("last"), spot, num(row.get("strike")), years, row.get("type"))
    bid, ask = num(row.get("bid")), num(row.get("ask"))
    executable_quote = bid is not None and ask is not None and bid > 0 and ask >= bid
    provider_iv_plausible = provider_iv is not None and 0.01 <= provider_iv <= 5.0
    # yfinance often exposes placeholder IVs without a timestamped quote. Do
    # not let a syntactically positive 0.00001 IV contaminate Gamma.
    if provider_iv_plausible and (provider != "yfinance" or executable_quote):
        if last_iv is None or provider_iv >= 0.05 or abs(provider_iv - last_iv) <= max(0.10, 0.50 * last_iv):
            return provider_iv, "provider_iv"
    if last_iv is not None and 0 < last_iv < 5:
        return last_iv, "last_iv_model"
    return None, None


def summarize(packet: dict, as_of: str | None = None, near_pct: float = 0.03) -> dict:
    options = packet.get("options", [])
    spot = num(packet.get("spot"))
    as_of = as_of or packet.get("as_of") or str(packet.get("retrieved_at", ""))[:10]
    if not options:
        return {"status": "unavailable", "gamma_status": "UNAVAILABLE_NO_OPTION_ROWS", "reason": "no option rows", "symbol": packet.get("symbol")}
    if spot is None or spot <= 0:
        return {"status": "unavailable", "gamma_status": "UNAVAILABLE_INVALID_SPOT", "reason": "valid spot required", "symbol": packet.get("symbol")}

    rows_out = []
    eligible_rows = 0
    gamma_rows = 0
    oi_rows = 0
    positive_oi_rows = 0
    gamma_oi_rows = 0
    positive_gamma_oi_rows = 0
    iv_source_counts = defaultdict(int)

    for row in options:
        strike = num(row.get("strike"))
        years = expiry_years(row.get("expiry"), as_of)
        option_type = row.get("type")
        if strike is None or years is None or option_type not in {"call", "put"}:
            continue
        eligible_rows += 1
        sigma, iv_source = pick_iv(row, spot, years, str(packet.get("provider") or ""))
        gamma = bs_gamma(spot, strike, years, sigma) if sigma is not None else None
        oi = num(row.get("open_interest"))
        if gamma is not None:
            gamma_rows += 1
            iv_source_counts[iv_source] += 1
        if oi is not None:
            oi_rows += 1
            if oi > 0:
                positive_oi_rows += 1
        gross_shares_1pct = None
        gross_notional_1pct = None
        if gamma is not None and oi is not None and oi >= 0:
            gamma_oi_rows += 1
            gross_shares_1pct = gamma * oi * 100.0 * (0.01 * spot)
            gross_notional_1pct = gross_shares_1pct * spot
            if oi > 0 and gross_notional_1pct > 0:
                positive_gamma_oi_rows += 1
        rows_out.append({
            "expiry": row.get("expiry"),
            "strike": strike,
            "type": option_type,
            "open_interest": oi,
            "iv_used": sigma,
            "iv_source": iv_source,
            "theoretical_gamma": gamma,
            "gross_hedge_shares_per_1pct_spot": gross_shares_1pct,
            "gross_gamma_notional_per_1pct_spot": gross_notional_1pct,
            "distance_pct": strike / spot - 1.0,
        })

    by_strike = defaultdict(lambda: {
        "call_open_interest_observed": 0.0,
        "put_open_interest_observed": 0.0,
        "call_oi_rows": 0,
        "put_oi_rows": 0,
        "call_rows": 0,
        "put_rows": 0,
        "call_gross_gamma_notional_per_1pct_spot": 0.0,
        "put_gross_gamma_notional_per_1pct_spot": 0.0,
        "gamma_oi_rows": 0,
    })
    for row in rows_out:
        bucket = by_strike[row["strike"]]
        side = row["type"]
        bucket[f"{side}_rows"] += 1
        if row["open_interest"] is not None:
            bucket[f"{side}_oi_rows"] += 1
            bucket[f"{side}_open_interest_observed"] += row["open_interest"]
        if row["gross_gamma_notional_per_1pct_spot"] is not None:
            bucket[f"{side}_gross_gamma_notional_per_1pct_spot"] += row["gross_gamma_notional_per_1pct_spot"]
            bucket["gamma_oi_rows"] += 1

    strikes = []
    for strike, bucket in sorted(by_strike.items()):
        call_total = bucket["call_gross_gamma_notional_per_1pct_spot"]
        put_total = bucket["put_gross_gamma_notional_per_1pct_spot"]
        strikes.append({
            "strike": strike,
            "distance_pct": strike / spot - 1.0,
            "call_open_interest_observed": bucket["call_open_interest_observed"] if bucket["call_oi_rows"] else None,
            "put_open_interest_observed": bucket["put_open_interest_observed"] if bucket["put_oi_rows"] else None,
            "call_oi_coverage": ratio(bucket["call_oi_rows"], bucket["call_rows"]),
            "put_oi_coverage": ratio(bucket["put_oi_rows"], bucket["put_rows"]),
            "call_gross_gamma_notional_per_1pct_spot": call_total if bucket["gamma_oi_rows"] else None,
            "put_gross_gamma_notional_per_1pct_spot": put_total if bucket["gamma_oi_rows"] else None,
            "total_gross_gamma_notional_per_1pct_spot": (call_total + put_total) if bucket["gamma_oi_rows"] else None,
            "gamma_oi_rows": bucket["gamma_oi_rows"],
        })

    computable_strikes = [x for x in strikes if x["total_gross_gamma_notional_per_1pct_spot"] is not None]
    positive_strikes = [x for x in computable_strikes if x["total_gross_gamma_notional_per_1pct_spot"] > 0]
    ranked = sorted(positive_strikes, key=lambda x: x["total_gross_gamma_notional_per_1pct_spot"], reverse=True)
    upper = [x for x in positive_strikes if x["strike"] >= spot]
    lower = [x for x in positive_strikes if x["strike"] <= spot]
    largest_upper = max(upper, key=lambda x: x["total_gross_gamma_notional_per_1pct_spot"], default=None)
    largest_lower = max(lower, key=lambda x: x["total_gross_gamma_notional_per_1pct_spot"], default=None)
    near = [x for x in positive_strikes if abs(x["distance_pct"]) <= near_pct]
    gross_near = sum(x["total_gross_gamma_notional_per_1pct_spot"] for x in near) if near else None
    gross_total = sum(x["total_gross_gamma_notional_per_1pct_spot"] for x in positive_strikes) if positive_strikes else None

    data_quality = {
        "eligible_rows": eligible_rows,
        "rows_with_iv_and_gamma": gamma_rows,
        "rows_with_open_interest": oi_rows,
        "rows_with_positive_open_interest": positive_oi_rows,
        "rows_with_gamma_and_open_interest": gamma_oi_rows,
        "rows_with_positive_gamma_and_open_interest": positive_gamma_oi_rows,
        "computable_strikes": len(computable_strikes),
        "positive_gamma_strikes": len(positive_strikes),
        "gamma_coverage_ratio": ratio(gamma_rows, eligible_rows),
        "oi_coverage_ratio": ratio(oi_rows, eligible_rows),
        "gamma_oi_coverage_ratio": ratio(gamma_oi_rows, eligible_rows),
        "positive_oi_ratio": ratio(positive_oi_rows, eligible_rows),
        "iv_source_counts": dict(iv_source_counts),
        "full_chain_requested": bool(packet.get("request", {}).get("full_chain")),
    }
    coverage = data_quality["gamma_oi_coverage_ratio"] or 0.0
    if not positive_strikes:
        evidence_grade = "D"
        gamma_status = "UNAVAILABLE_ZERO_OR_UNTRUSTED_OI"
    elif packet.get("provider") == "yfinance":
        evidence_grade = "C" if coverage >= 0.9 and data_quality["full_chain_requested"] else "D"
        gamma_status = "AVAILABLE_GROSS_ONLY"
    else:
        evidence_grade = "C" if coverage >= 0.8 else "D"
        gamma_status = "AVAILABLE_GROSS_ONLY"

    signed_scenarios = None
    if gross_total is not None and gross_total > 0:
        signed_scenarios = {
            "status": "ASSUMPTION_ONLY",
            "dealer_short_gamma_all_observed_oi": {
                "signed_gamma_notional_per_1pct_spot": -gross_total,
                "hedge_tendency": "procyclical: rising spot can require additional stock buying; falling spot can require selling",
            },
            "dealer_long_gamma_all_observed_oi": {
                "signed_gamma_notional_per_1pct_spot": gross_total,
                "hedge_tendency": "countercyclical: rising spot can induce stock selling; falling spot can induce buying",
            },
            "warning": "These are bounding scenarios, not dealer-position estimates. Open interest does not reveal customer/dealer side.",
        }

    return {
        "status": "ok" if positive_strikes else "partial",
        "gamma_status": gamma_status,
        "symbol": packet.get("symbol"),
        "provider": packet.get("provider"),
        "as_of": as_of,
        "spot": spot,
        "method": {
            "gamma": "Black-Scholes theoretical gamma using provider IV when valid, otherwise last-price IV inversion",
            "gross_gamma_notional_per_1pct_spot": "gamma * open_interest * 100 * spot^2 * 0.01",
            "sign_policy": "gross only; dealer sign is unknown unless independently inferred",
        },
        "data_quality": data_quality,
        "evidence_grade": evidence_grade,
        "summary": {
            "gross_gamma_notional_per_1pct_spot_observed": gross_total,
            "gross_gamma_within_near_band": gross_near,
            "near_band_pct": near_pct,
            "largest_upper_gamma_concentration": largest_upper,
            "largest_lower_gamma_concentration": largest_lower,
            "top_gamma_concentrations": ranked[:10],
            "distance_to_largest_upper_pct": largest_upper["distance_pct"] if largest_upper else None,
            "distance_to_largest_lower_pct": largest_lower["distance_pct"] if largest_lower else None,
        },
        "strike_structure": strikes,
        "signed_gex_scenarios": signed_scenarios,
        "gamma_flip": {
            "status": "UNAVAILABLE_WITHOUT_POSITION_SIGN",
            "reason": "A gamma flip requires a defensible signed dealer-exposure model; gross OI-weighted gamma cannot identify the sign transition.",
        },
        "squeeze_risk": {
            "status": "CONDITIONAL_ONLY" if positive_strikes else "UNAVAILABLE_WITHOUT_POSITIVE_GAMMA_STRUCTURE",
            "required_conditions": [
                "spot approaches a high gross-gamma concentration",
                "dealer/customer position sign is independently inferred or explicitly assumed",
                "stock flow/microstructure confirms directional pressure",
                "option and underlying timestamps are sufficiently aligned",
            ],
            "warning": "A gamma concentration is not automatically support/resistance and does not by itself confirm a gamma squeeze.",
        },
        "warnings": [
            "Open interest is not directional and does not identify dealer versus customer ownership.",
            "Missing open interest remains missing; zero OI is not promoted to a Gamma wall or concentration.",
            "Gross totals are observed-coverage totals and must be read with gamma_oi_coverage_ratio and positive_oi_ratio.",
            "Provider IV from yfinance can be stale; last-price inversion can be distorted by stale prints, spreads, dividends, rates, and American exercise.",
            "Use --full-chain for nightly concentration scans; bounded ATM slices can miss distant OI/gamma clusters.",
        ],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--options", required=True, help="Normalized/provider option packet JSON")
    ap.add_argument("--out", required=True)
    ap.add_argument("--as-of", help="Valuation date YYYY-MM-DD; defaults to packet as_of/retrieved_at")
    ap.add_argument("--near-pct", type=float, default=0.03, help="Spot-distance band for near-spot gross gamma, default 0.03")
    args = ap.parse_args()
    packet = json.loads(Path(args.options).read_text(encoding="utf-8"))
    result = summarize(packet, args.as_of, args.near_pct)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"written": args.out, "status": result.get("status"), "gamma_status": result.get("gamma_status"),
                      "symbol": result.get("symbol"), "grade": result.get("evidence_grade")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
