# Short-horizon timing and same-day scenario framework

Use this reference when the user asks for today's entry conditions, pre-market interpretation, opening-range timing, or a short holding horizon. Keep the long-horizon fundamental and scenario analysis; this is an additional tactical layer. It is decision support, not an order instruction. Never copy prices, probabilities, IVs, support levels, or position sizes from an example ticker.

## Two data regimes

| Regime | Available evidence | Supports | Does not support |
|---|---|---|---|
| A: bars only | Daily/intraday OHLCV, ATR, VWAP, opening range, support/resistance, bar count | Structure, momentum, range and conditional price paths | Forward distribution, option walls, implied event move |
| B: bars + options | Regime A plus aligned expiries, strikes, last/bid-ask, volume/OI where available | Implied volatility, total variance, skew, event premium and risk haircut | Certain direction, opening/closing intent or guaranteed support/resistance |

Always state which regime is active. If options have no executable bid/ask or OI, downgrade them to historical/model evidence and do not call a strike a hard wall.

## Session phases

1. `pre_market`: latest regular-session close, current gap if available, scheduled catalyst, and latest option evidence.
2. `opening_confirmation`: opening range and first stable price/volume response; the first print is not confirmation.
3. `intraday_follow_through`: price versus VWAP, opening-range high/low, prior close and dynamic support/resistance.
4. `close_or_overnight`: distinguish no position, intraday-only risk, and separately budgeted overnight risk.

Record retrieval timestamps and mark stale fields. If the current quote, session status, or catalyst result is missing, reduce confidence rather than inventing a current path.

## Dynamic levels

Derive levels from the current ticker:

- `S1/S2`: nearest and next support from pivots, recent lows, volume nodes, VWAP bands, or option strikes only when quote/OI quality supports that use.
- `R1/R2`: nearest and next resistance using the same rule.
- `ORH/ORL`: opening-range high/low over a declared 5-, 15-, or 30-minute window.
- `ATR_session`: intraday or daily ATR scaled to the intended holding horizon.
- `gap`: `(current_reference_price - prior_regular_close) / prior_regular_close`.

Never use a universal percentage for a stop or target. A same-day stop must reference a failed structural level, a declared volatility buffer, or both. A target must reference the next observed price/liquidity zone and show reward-to-risk.

## Today's minimum scenario tree

Every tactical inference must show these paths. Add an event-specific path when a catalyst is scheduled. Probabilities are assumptions; if they cannot be defended, use qualitative confidence and mark the numeric probability `not estimated`.

| Scenario | Evidence pattern | Entry condition to monitor | Invalidation | Risk action |
|---|---|---|---|---|
| Gap-up acceptance | Gap holds above prior close or R1; opening range builds above VWAP | Retest/hold of ORH, VWAP, or declared reclaim level | Loss of held level with expanding sell volume | Do not chase; use structural stop and reduced event size |
| Gap-up failure | Gap cannot hold; price returns below prior close/VWAP | No long confirmation until failed level is reclaimed | Continued lower highs or ORL break | Stand aside or reassess; gap alone is not direction |
| Gap-down acceptance | Gap holds below S1/prior close; price remains below VWAP | Failed retest of S1/VWAP before treating downside as confirmed | Recovery above failed level | Avoid catching a falling move; keep fixed risk |
| Gap-down reversal | Gap probes S1/S2 then reclaims VWAP or ORH | Reclaim plus a defined retest | Rejection below reclaimed level | Treat as reversal setup, not trend proof |
| Range/compression | Price remains between ORL and ORH; range contracts | Close/hold outside range or remain flat | False break back inside range | Do not force a directional position |
| Event/data invalidation | Filing, quote, option timestamp, entitlement, or cross-source conflict | Refresh missing field before acting on the path | Conflict remains unresolved | Confidence `very_low`; no Kelly-based sizing |

## Short-horizon Kelly as an auxiliary estimate

Estimate `p` and `b` only from historical occurrences of the same setup, timeframe, liquidity class, and exit rule. A daily RSI backtest is not interchangeable with an opening-range breakout setup.

```text
f_raw = (p*b - (1-p)) / b
f_quarter = 0.25 * f_raw
f_event_adjusted = f_quarter * event_or_volatility_haircut
f_final_cap = min(f_event_adjusted, fixed_risk_cap, concentration_cap, liquidity_cap)
```

The multiplier and caps are configuration, not facts. Options modify risk through IV, total variance, skew, and event premium; they do not create a directional `p`.

### Evidence tiers for short samples

| Tier | Evidence | Output | Interpretation |
|---|---|---|---|
| Exploratory | Any valid trade log below the conditional threshold | Full-sample estimate, confidence and uncertainty | Research diagnostic only; no validated Kelly claim |
| Conditional tactical | Declared smaller OOS block, preferably at least 20 total and 10 OOS occurrences | OOS range plus quarter-Kelly/event haircut | Auxiliary timing input; user decides whether it is usable |
| Standard validated | At least 60 total and 30 reserved OOS trades | OOS Kelly cap plus all risk caps | Qualified model output, still not an automatic trade |

These are governance tiers, not universal statistical laws. Do not manufacture occurrences by splitting one trade, changing timeframe after seeing results, or mixing unrelated setups.

## Confidence contract

Every short-horizon report must include:

- `data_confidence`: freshness, quote coverage, cross-source agreement and entitlement status;
- `setup_confidence`: match between current pattern and the backtested setup;
- `sample_confidence`: trade count, OOS count and regime coverage;
- `overall_confidence`: minimum or documented weighted combination of the above;
- `confidence_reasons`: exact missing or conflicting evidence;
- `action_boundary`: what requires confirmation and what invalidates the setup.

Use `very_low` for stale/conflicting current data, `low` for an identifiable setup with a small sample, `medium` when setup/source quality/modest OOS evidence agree, and `high` only for fresh, multi-source, historically stable evidence. Confidence is not certainty.

## Output contract

For a today's-timing report, present as-of time/session phase; facts, data results, model outputs, assumptions; Regime A/B evidence; dynamic S1/S2, R1/R2, ORH/ORL, VWAP and ATR; the scenario table; conditional entry/stop/target/no-trade criteria; exploratory/conditional/standard Kelly with confidence; and the next refresh trigger.

The correct fallback is not “cannot calculate.” Calculate the available diagnostic, label its confidence and tier, and prevent it from being presented as validated or automatic sizing.
