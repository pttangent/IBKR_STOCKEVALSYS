# Position, stop/target, and short-term scenario report contract

Organize the report by holding horizon, not by calculation module alone. The reader should be able to see all decisions relevant to one horizon together.

## Short-horizon block

When the user asks about today's or short-horizon timing, keep these items together and in this order:

1. `Today's short-horizon scenario tree`
2. `Entry confirmation and invalidation`
3. `Stop-loss / take-profit and P/L ladder`
4. `Short-horizon Kelly position plan`

The short-horizon block must use the same entry, stop, target, and account assumptions throughout. Do not place a long-term scenario between these sections.

## Long-horizon block

Keep these items together after the short-horizon block:

1. `Long-horizon multi-scenario analysis`
2. fundamental/valuation evidence and catalysts
3. option-implied event, tail, and volatility evidence
4. `Long-horizon position boundary`

Long-horizon Kelly or sizing must not silently reuse today's opening-range levels. If the holding horizon changes, recompute the stop, target, expected payoff `b`, volatility/event haircut, and share count.

## Simulation contract

Unless the user supplies different inputs, use a clearly labeled illustrative account of `$10,000`, a fixed-risk budget of `0.5%` of capital, a single-name concentration cap of `5%`, and the configured Kelly diagnostic cap. These are assumptions, not recommendations. Show the inputs in a table before calculating shares.

Use dollar amount as the primary reader-facing position output. Fractional shares may be shown only as an auxiliary conversion at the current entry price. Do not force a 0.5-share grid or round a fractional-share account down to 0.5 shares.

```text
integer_shares = floor(allowed_notional / entry_price)
exact_fractional_shares = allowed_notional / entry_price
```

Apply the minimum of known constraints to `allowed_notional`: diagnostic Kelly cap, concentration cap, and any portfolio/risk cap that can be computed from the stop. If the user has not supplied portfolio value, entry, stop, or risk budget, show the formula and mark the resulting field `needs_input`; do not invent a final position. When the user requests the default illustration, use `$10,000` only as a labeled simulation assumption.

## Required Kelly table

| Item | Value | Confidence/status | Notes |
|---|---:|---|---|
| Account value | | assumption | default $10,000 only when not supplied |
| `p` | | data result | same ticker, same setup and exit rule |
| `b` | | data result | average win / average loss |
| `f_raw` | | model output | `(p*b-(1-p))/b` |
| Full / half / quarter Kelly multipliers | `1.00 / 0.50 / 0.25` | assumption/config | always display all three scenarios; quarter is only the conservative default |
| Option/event haircut | | model output | IV/total variance/skew evidence only |
| Full Kelly diagnostic | | model output | `f_raw` after option/event haircut, before concentration/fixed-risk caps |
| Half Kelly diagnostic | | model output | `full Kelly × 0.50` |
| Quarter Kelly diagnostic | | model output | `full Kelly × 0.25` |
| `diagnostic_fractional_kelly_cap` | | model output | configured default cap, normally quarter Kelly; must be shown even with short OOS |
| `applied_fractional_kelly` | | qualification status | may be null when not validated |
| Allowed notional | | model output | minimum of known caps |
| Allowed position amount | | calculation | primary output in dollars |
| Integer shares | | optional conversion | round down only if useful |
| Exact fractional shares | | optional conversion | `allowed_notional / entry_price`; no 0.5-share rounding |

The report must explain why a diagnostic ratio is not automatically applied. “Not qualified” cannot replace the ratio display.

## Required P/L ladder

For every stop and target level, show per-share and account-level dollar P/L using the exact fractional quantity implied by the allowed amount. Integer-share P/L may be shown as a secondary comparison:

| Level | Type | Price | Per-share P/L | Allowed amount | Exact fractional shares | Dollar P/L | Integer-share comparison | R:R / eligibility |
|---|---|---:|---:|---:|---:|---:|---:|---|

Every setup must label three stop layers when the technical data support them: `S1` near/tactical stop, `S2` primary structural stop, and `S3` deeper trend-failure stop. Explain which layer is the default and show the dollar loss for all three. A single stop may be used only when the data genuinely provide only one defensible invalidation level.

Use `loss = (entry - stop) * shares`, `profit = (target - entry) * shares`, and `R:R = profit / loss` for the paired stop. Mark a quantity as `risk_cap_exceeded` when its stop loss exceeds the declared fixed-risk budget. Do not call a technical level a guaranteed stop; gap risk may bypass it.

## Required short-term section

Use current session phase and dynamic levels. Show a table with:

| Scenario | Facts/data pattern | Entry confirmation | Stop/target reference | Invalidation | Confidence | Action boundary |
|---|---|---|---|---|---|---|

At minimum include gap-up acceptance, gap-up failure, gap-down acceptance or reversal, range/compression, and data invalidation. ORH/ORL and VWAP must be marked `not yet observed` before the regular session. Replace the pre-market placeholders after the opening window is complete.

Keep the section conditional and non-prescriptive: it specifies what would confirm or invalidate a path, not an instruction to trade.

## Horizon separation checks

Before finalizing, verify:

- short-horizon entry, stop, target, Kelly cap, share count, and P/L all use one coherent trade setup;
- long-horizon scenarios are not used as same-day entry signals;
- each hidden numeric assumption appears in a table or formula block;
- a diagnostic Kelly fraction is displayed even when it is not validated, while `applied_fractional_kelly` remains separate;
- allowed dollar amounts are primary; exact fractional shares are only a conversion and are never rounded to a 0.5-share grid.
