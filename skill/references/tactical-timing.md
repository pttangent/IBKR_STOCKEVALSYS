# Short-horizon timing and same-day scenario framework

Use this reference when the user asks for today's entry conditions, pre-market interpretation, opening-range timing, or a short holding horizon. Keep the long-horizon fundamental and scenario analysis; this is an additional tactical layer. It is decision support, not an order instruction. Never copy prices, probabilities, IVs, support levels, or position sizes from an example ticker.

For the canonical branching representation and the required intraday / short-term / long-term split, read [scenario-tree-reasoning.md](scenario-tree-reasoning.md). For position sizing inside those branches, read [kelly-positioning-knowledge.md](kelly-positioning-knowledge.md).

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

Record retrieval timestamps and mark stale fields. If the current quote, session status, or catalyst result is missing, reduce confidence rather than inventing a current path. If the report is generated before the new session has opened, label the tree `next_session_conditional`; ORH/ORL/VWAP are values to be formed, not already observed numbers.

## Dynamic levels

Derive levels from the current ticker:

- `S1/S2`: nearest and next support from pivots, recent lows, volume nodes, VWAP bands, or option strikes only when quote/OI quality supports that use.
- `R1/R2`: nearest and next resistance using the same rule.
- `ORH/ORL`: opening-range high/low over a declared 5-, 15-, or 30-minute window. The structured report defaults to a declared 15-minute opening range unless research content explicitly selects another interval.
- `ATR_session`: intraday or daily ATR scaled to the intended holding horizon.
- `gap`: `(current_reference_price - prior_regular_close) / prior_regular_close`.

Never use a universal percentage for a stop or target. A same-day stop must reference a failed structural level, a declared volatility buffer, or both. A target must reference the next observed price/liquidity zone and show reward-to-risk.

## Canonical intraday tree

The report must materialize the intraday logic as a branching tree, not only a flat table:

```text
OPEN / 開盤
├─ GAP UP / 高開
│  ├─ ACCEPTANCE / 衝高延續
│  └─ FADE / 衝高回落
├─ NEAR FLAT / 平開
│  ├─ UPSIDE BREAK / 向上突破
│  ├─ RANGE / 區間
│  └─ DOWNSIDE BREAK / 向下跌破
└─ GAP DOWN / 低開
   ├─ ACCEPTANCE / 弱勢延續
   └─ REVERSAL / 低開反轉
```

Each node must carry an observable `trigger`, current `price_reference` when available, `watch`, interpretation, `response`, `invalidation`, `action_boundary`, and a non-automatic `sizing_tier`. The tree answers: **price did X; what should I watch next and how should the posture change?**

A flat scenario table may still be emitted as a compact summary, but it is not the canonical scenario representation.

## Typical branch logic

| Scenario | Evidence pattern | Confirmation to monitor | Invalidation | Risk response |
|---|---|---|---|---|
| Gap-up acceptance | Gap holds above prior close or R1; opening range builds above VWAP | Retest/hold of ORH, VWAP, or declared reclaim level | Loss of held level with expanding sell pressure | Small confirmed setup may use quarter guidance; do not chase |
| Gap-up fade | Gap cannot hold; price returns below prior close/VWAP | No long confirmation until failed level is reclaimed | Successful reclaim and retest | Stand aside/reassess |
| Gap-down acceptance | Gap holds below S1/prior close; price remains below VWAP | Failed retest of S1/VWAP | Recovery above failed level and hold | Defensive/no new long confirmation |
| Gap-down reversal | Gap probes S1/S2 then reclaims VWAP or ORH | Reclaim plus defined retest | Rejection below reclaimed level | Small reversal candidate only after confirmation |
| Range/compression | Price remains between ORL and ORH | Close/hold outside range | False break back inside range | No forced direction |
| Evidence invalidation | Filing, quote, option timestamp, entitlement, or cross-source conflict unresolved | Refresh the exact field | Conflict remains unresolved | Confidence very low; no validated Kelly claim |

## Short-horizon Kelly as an auxiliary estimate

Estimate `p` and `b` from historical occurrences of the same setup, timeframe, liquidity class, and exit rule. A daily RSI backtest is not interchangeable with an opening-range breakout or reclaim/retest setup.

```text
f_raw = (p*b - (1-p)) / b
full    = 1.00 * selected_Kelly
half    = 0.50 * selected_Kelly
quarter = 0.25 * selected_Kelly
```

Current RV, option/event risk and portfolio limits are applied **after** the edge estimate. The default report account is a clearly labeled **$10,000 simulation** unless the user supplies another portfolio value. Every usable variant is translated into NAV %, dollar notional, shares and one-day one-sigma risk. A valid stop adds a stop-risk cap and stop-loss dollar amount.

The correct fallback is not “cannot calculate” merely because standard OOS is insufficient. Show exploratory/conditional/proxy guidance when the edge math is defined; if no positive Kelly edge exists but a valid stop exists, show a risk-only fixed-risk/concentration guide. Abstain numerically only when both paths are genuinely unavailable.

### Evidence tiers for short samples

| Tier | Evidence | Output | Interpretation |
|---|---|---|---|
| Exploratory | Any valid trade log below the conditional threshold | Full-sample estimate, full/half/quarter and confidence | Research diagnostic / guide only |
| Conditional tactical | Declared smaller OOS block, preferably at least 20 total and 10 OOS occurrences | OOS estimate plus RV/event overlays and full/half/quarter | Auxiliary timing input |
| Standard validated | At least 60 total and 30 reserved OOS trades | OOS Kelly ladder plus all risk caps | Qualified model output, still not an automatic trade |

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

For a current/next-session timing report, present as-of time/session phase; pre-market facts and overnight changes; Regime A/B evidence; dynamic S1/S2, R1/R2, ORH/ORL, VWAP and ATR where actually observed; the branching intraday tree; conditional entry/invalidation/no-trade criteria; Kelly full/half/quarter with current-RV and $10k risk translation; and the next refresh trigger.

A full report must then preserve separate **short-term** and **long-term** trees. Do not let an intraday gap branch replace the short-term repair/breakdown analysis or the long-term business/valuation thesis.
