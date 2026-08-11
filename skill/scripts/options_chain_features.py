#!/usr/bin/env python3
"""Compute evidence-labelled option-chain structure from a provider packet."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


def num(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def median(values):
    values = [x for x in values if x is not None]
    return statistics.median(values) if values else None


def observed_sum(rows, key):
    values = [num(row.get(key)) for row in rows]
    observed = [value for value in values if value is not None]
    return sum(observed) if observed else None


def field_coverage(rows, key):
    total = len(rows)
    present = sum(1 for row in rows if num(row.get(key)) is not None)
    return {
        "rows": total,
        "present": present,
        "missing": total - present,
        "coverage_ratio": present / total if total else None,
    }


def complete_sum(rows, key):
    """Return a sum only when every row has the field; missing never becomes zero."""
    coverage = field_coverage(rows, key)
    if not rows or coverage["present"] != coverage["rows"]:
        return None
    return observed_sum(rows, key)


def expiry_years(expiry, as_of):
    try:
        text = str(expiry).replace("-", "")
        exp = dt.datetime.strptime(text[:8], "%Y%m%d").date()
        base = dt.date.fromisoformat(str(as_of)[:10])
        return max((exp - base).days / 365.0, 1.0 / 365.0)
    except (TypeError, ValueError):
        return None


def normal_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_price(spot, strike, years, sigma, option_type):
    if min(spot, strike, years, sigma) <= 0:
        return None
    d1 = (math.log(spot / strike) + 0.5 * sigma * sigma * years) / (sigma * math.sqrt(years))
    d2 = d1 - sigma * math.sqrt(years)
    if option_type == "call":
        return spot * normal_cdf(d1) - strike * normal_cdf(d2)
    return strike * normal_cdf(-d2) - spot * normal_cdf(-d1)


def implied_vol(price, spot, strike, years, option_type):
    price, spot, strike = num(price), num(spot), num(strike)
    if None in (price, spot, strike, years) or price <= 0 or years <= 0:
        return None
    intrinsic = max(spot - strike, 0.0) if option_type == "call" else max(strike - spot, 0.0)
    upper = spot if option_type == "call" else strike
    if price <= intrinsic + 1e-7 or price >= upper:
        return None
    lo, hi = 1e-6, 8.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        value = bs_price(spot, strike, years, mid, option_type)
        if value is None:
            return None
        if value > price:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2.0


def valid_quote(row):
    bid, ask = num(row.get("bid")), num(row.get("ask"))
    return bid is not None and ask is not None and bid > 0 and ask > 0 and ask >= bid


def summarize(packet, as_of=None):
    options = packet.get("options", [])
    if not options:
        return {"status": "unavailable", "reason": "no option quote/model rows", "symbol": packet.get("symbol")}
    by_expiry = defaultdict(list)
    for row in options:
        by_expiry[str(row.get("expiry"))].append(row)
    expiry_features = []
    as_of = as_of or packet.get("as_of") or str(packet.get("retrieved_at", ""))[:10]
    spot = num(packet.get("spot"))
    for expiry, rows in sorted(by_expiry.items()):
        calls = [x for x in rows if x.get("type") == "call"]
        puts = [x for x in rows if x.get("type") == "put"]
        quote_rows = [x for x in rows if valid_quote(x)]
        ivs = [num(x.get("iv")) for x in rows if num(x.get("iv")) is not None and 0 < num(x.get("iv")) < 5]
        quote_ivs = [num(x.get("iv")) for x in quote_rows if num(x.get("iv")) is not None and 0 < num(x.get("iv")) < 5]
        years = expiry_years(expiry, as_of)
        for row in rows:
            row["last_iv_model"] = implied_vol(row.get("last"), spot, num(row.get("strike")), years, row.get("type")) if years and spot else None
        last_ivs = [x.get("last_iv_model") for x in rows if x.get("last_iv_model") is not None and x.get("last_iv_model") < 5]
        volume_calls = observed_sum(calls, "volume")
        volume_puts = observed_sum(puts, "volume")
        call_volume_coverage = field_coverage(calls, "volume")
        put_volume_coverage = field_coverage(puts, "volume")
        call_oi_observed = observed_sum(calls, "open_interest")
        put_oi_observed = observed_sum(puts, "open_interest")
        call_oi_coverage = field_coverage(calls, "open_interest")
        put_oi_coverage = field_coverage(puts, "open_interest")
        oi_calls = complete_sum(calls, "open_interest")
        oi_puts = complete_sum(puts, "open_interest")
        spreads = [((num(x["ask"]) - num(x["bid"])) / ((num(x["ask"]) + num(x["bid"])) / 2)) for x in quote_rows
                   if (num(x["ask"]) + num(x["bid"])) > 0]
        atm_straddles = []
        if spot is not None:
            strikes = sorted({num(x.get("strike")) for x in rows if num(x.get("strike")) is not None})
            if strikes:
                atm = min(strikes, key=lambda strike: abs(strike - spot))
                c = next((x for x in calls if num(x.get("strike")) == atm), None)
                p = next((x for x in puts if num(x.get("strike")) == atm), None)
                if c and p:
                    c_has_quote = num(c.get("bid")) is not None and num(c.get("ask")) is not None and num(c.get("bid")) > 0 and num(c.get("ask")) > 0
                    p_has_quote = num(p.get("bid")) is not None and num(p.get("ask")) is not None and num(p.get("bid")) > 0 and num(p.get("ask")) > 0
                    cp = (num(c.get("bid")) + num(c.get("ask"))) / 2 if c_has_quote else num(c.get("last"))
                    pp = (num(p.get("bid")) + num(p.get("ask"))) / 2 if p_has_quote else num(p.get("last"))
                    if cp is not None and pp is not None and years:
                        atm_straddles.append({"strike": atm, "call_price_proxy": cp, "put_price_proxy": pp,
                                              "straddle_price_proxy": cp + pp, "straddle_pct_spot": (cp + pp) / spot,
                                              "price_source": "bid_ask_mid" if c_has_quote and p_has_quote else "last_trade_proxy",
                                              "years_to_expiry": years,
                                              "atm_straddle_approx_iv": (cp + pp) / spot * math.sqrt(math.pi / (2.0 * years))})
        otm_put = min((x for x in puts if x.get("last_iv_model") is not None),
                      key=lambda x: abs(num(x.get("strike")) - spot * 0.95), default=None) if spot else None
        otm_call = min((x for x in calls if x.get("last_iv_model") is not None),
                       key=lambda x: abs(num(x.get("strike")) - spot * 1.05), default=None) if spot else None
        atm = atm_straddles[0] if atm_straddles else None
        reference_iv = median(last_ivs) or (atm.get("atm_straddle_approx_iv") if atm else None)
        expiry_features.append({"expiry": expiry, "contracts": len(rows), "quote_rows": len(quote_rows),
                                "provider_iv_median": median(ivs), "market_quote_iv_median": median(quote_ivs),
                                "last_iv_model_median": median(last_ivs), "reference_iv_for_term": reference_iv,
                                "total_variance": reference_iv * reference_iv * years if reference_iv and years else None,
                                "years_to_expiry": years,
                                "call_volume": volume_calls, "put_volume": volume_puts,
                                "call_volume_coverage": call_volume_coverage, "put_volume_coverage": put_volume_coverage,
                                "put_call_volume_ratio": volume_puts / volume_calls if volume_calls not in (None, 0) and volume_puts is not None else None,
                                "call_open_interest": oi_calls, "put_open_interest": oi_puts,
                                "call_open_interest_observed_sum": call_oi_observed,
                                "put_open_interest_observed_sum": put_oi_observed,
                                "call_open_interest_coverage": call_oi_coverage,
                                "put_open_interest_coverage": put_oi_coverage,
                                "put_call_oi_ratio": oi_puts / oi_calls if oi_calls not in (None, 0) and oi_puts is not None else None,
                                "median_relative_spread": median(spreads), "atm_straddle": atm,
                                "otm_5pct_put_iv_last_model": otm_put.get("last_iv_model") if otm_put else None,
                                "otm_5pct_put_strike": otm_put.get("strike") if otm_put else None,
                                "otm_5pct_call_iv_last_model": otm_call.get("last_iv_model") if otm_call else None,
                                "otm_5pct_call_strike": otm_call.get("strike") if otm_call else None,
                                "otm_put_minus_call_iv": (otm_put.get("last_iv_model") - otm_call.get("last_iv_model")) if otm_put and otm_call else None})
    term = None
    valid_terms = [x for x in expiry_features if x.get("total_variance") is not None]
    if len(valid_terms) >= 2:
        front, back = valid_terms[0], valid_terms[-1]
        term = {"front_expiry": front["expiry"], "back_expiry": back["expiry"],
                "front_total_variance": front["total_variance"], "back_total_variance": back["total_variance"],
                "back_to_front_total_variance": back["total_variance"] / front["total_variance"] if front["total_variance"] else None}
    return {"status": "ok", "provider": packet.get("provider"), "source_role": packet.get("source_role"),
            "symbol": packet.get("symbol"), "spot": packet.get("spot"), "as_of": as_of,
            "chain_discovery": packet.get("chain_discovery", {}), "quote_coverage": packet.get("quote_coverage", {}),
            "expiry_features": expiry_features, "term_structure": term,
            "market_data_type_counts": {str(kind): sum(1 for row in options if str(row.get("market_data_type")) == str(kind)) for kind in sorted({row.get("market_data_type") for row in options})},
            "warnings": ["put/call volume and open interest are activity distributions, not buy/sell or opening/closing direction",
                         "missing volume/open_interest stays missing; observed sums are separate and complete totals are null unless coverage is 100%",
                         "modelGreeks/IV must be separated from market-quoted IV when bid/ask is absent or stale",
                         "last_iv_model_median is a European Black-Scholes approximation from last price; American exercise, dividends, rates, and stale last trades can bias it",
                         "atm_straddle_approx_iv is a diagnostic approximation, not a full implied-volatility surface",
                         "bounded strikes are a diagnostic slice, not a full option chain",
                         "wide spreads and zero OI reduce evidentiary weight"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--options", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--as-of", help="valuation date YYYY-MM-DD; defaults to packet as_of/retrieved_at")
    args = ap.parse_args()
    result = summarize(json.loads(Path(args.options).read_text(encoding="utf-8")), args.as_of)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"written": args.out, "status": result.get("status"), "expiries": len(result.get("expiry_features", []))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
