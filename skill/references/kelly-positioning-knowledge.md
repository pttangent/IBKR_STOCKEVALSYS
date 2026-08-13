# Kelly sizing and current-volatility positioning knowledge

Use this reference whenever a report turns historical edge evidence into a capital-fraction or share-count guide. The objective is not to manufacture a precise percentage. The objective is to expose the whole chain from observed trade outcomes to Kelly, then shrink it for uncertainty, current volatility, stop risk, concentration and liquidity.

## 1. Separate edge from risk

Kelly has two distinct layers that must not be conflated.

**Edge layer** estimates whether the setup historically paid:

- `p`: win probability estimated from completed occurrences of the same declared setup;
- `b`: average win divided by average absolute loss;
- binary diagnostic: `f_raw = (p*b - (1-p)) / b`;
- empirical log-growth Kelly: maximize mean `log(1 + f*r_i)` over the observed trade-return distribution.

The empirical grid and the `p/b` formula are complementary diagnostics. Variable-return trade logs are not exactly binary bets, so prefer the empirical log-growth estimate for the underlying distribution and keep the `p/b` formula visible because it makes the source of the edge interpretable. When both exist, a conservative guide may use the smaller positive estimate rather than choosing the larger one after seeing the result.

**Risk layer** asks how much of that theoretical fraction survives current conditions. Current realized volatility, option/event risk, stop distance, concentration and liquidity do not create directional edge; they only reduce or cap the position.

## 2. Setup identity matters

The historical occurrences used for `p` and `b` should match the current setup in entry logic, horizon, exit rule and liquidity regime. Examples:

- an `RSI14 < 30` mean-reversion backtest is not the same setup as an EMA20 reclaim/retest;
- a daily breakout is not interchangeable with a 5-minute opening-range breakout;
- a post-earnings gap trade is not interchangeable with an ordinary pullback.

Record `current_setup_id`, `backtest_setup_id` and `setup_match_status` (`exact`, `compatible`, `proxy`, `mismatch`, or `unknown`). A mismatch does not make the historical calculation useless: show it as a **proxy diagnostic**, normally at a more conservative fractional Kelly, but do not call it validated or automatically apply it.

## 3. Full, half and quarter Kelly

Always show the ladder when a positive diagnostic Kelly can be computed:

```text
full    = 1.00 * selected_Kelly
half    = 0.50 * selected_Kelly
quarter = 0.25 * selected_Kelly
```

`full` is the theoretical growth-maximizing exposure under the estimated distribution. It is the most estimation-error-sensitive value and should almost never be the sole reader-facing recommendation. `half` and `quarter` are robustness variants, not different forecasts.

Default reporting policy: display all three, and use quarter Kelly as the conservative guidance variant unless the strategy's own governance explicitly selects another multiplier. A validated same-setup OOS result can justify presenting half Kelly as an additional operational candidate, but full Kelly remains a diagnostic upper bound rather than a default action.

## 4. Current RV must change the risk interpretation

Let annualized current realized volatility be `RV_current`.

```text
daily_sigma = RV_current / sqrt(252)
```

For a NAV fraction `f`, the approximate one-day one-sigma NAV contribution is:

```text
NAV_1sigma ≈ f * daily_sigma
```

This makes a 4% position in an 80% RV stock visibly different from a 4% position in a 20% RV stock even when both have the same historical Kelly estimate.

When enough history exists, estimate a point-in-time reference regime such as the median rolling 20-day annualized RV over the available history. A conservative no-upsize volatility overlay is:

```text
h_RV = min(1, RV_reference / RV_current)
```

Use it only when both current and reference RV are defensible. This overlay shrinks a position when current volatility is above the historical reference but never increases Kelly merely because current volatility is unusually low. Label it `rv_regime_haircut`; it is a volatility-targeting overlay, not part of the mathematical Kelly edge estimate.

If no reference RV is available, still show `daily_sigma` and each Kelly variant's implied NAV one-sigma contribution. Do not invent a reference volatility.

## 5. Option and event overlays

Options may shrink risk but may not create `p` or expected return. Useful overlays include:

- `h_IV = min(1, RV_current / IV_ATM)` when ATM IV is timestamped and defensible;
- a declared event haircut when a binary/event-rich front expiry materially raises gap risk;
- skew/term-structure warnings when the data quality supports them.

If several volatility/event haircuts describe overlapping risk, using the most conservative valid haircut is often preferable to multiplying all of them and double-counting the same risk. The report must disclose the chosen combination policy.

## 6. Capital constraints after Kelly

For each full/half/quarter variant, compute the theoretical fraction after risk overlays, then cap it by every applicable portfolio constraint.

For a long position with entry `E`, stop `S`, portfolio risk budget `R`, and stop distance `d = (E-S)/E`:

```text
stop_risk_cap_fraction = R / d
```

Other caps:

```text
concentration_cap_fraction = configured concentration cap
rv_sigma_cap_fraction = daily_sigma_budget / daily_sigma      # only when a daily sigma budget is configured
liquidity_cap_fraction = configured liquidity/capacity cap    # when available
```

The usable variant is:

```text
variant_final = min(variant_after_overlay,
                    stop_risk_cap_fraction,
                    concentration_cap_fraction,
                    rv_sigma_cap_fraction,
                    liquidity_cap_fraction)
```

Only include caps for which inputs exist. The binding constraint must be named. For a supplied portfolio value and current/entry price, translate the final fraction into notional and shares, but keep NAV fraction as the primary cross-account output.

## 7. Give a guide unless the data gap is genuinely severe

Do not respond with a blank Kelly section merely because standard validation is not reached.

- Standard same-setup OOS: show empirical and formula estimates, full/half/quarter, current-RV translation and the validated/applied policy fraction.
- Conditional OOS: show the same ladder with lower confidence and mark it `conditional`.
- Small full-sample trade log: show an `exploratory` ladder if the math is defined; use it as a research guide only.
- Setup mismatch: show a `proxy` ladder and explicitly state the mismatch; do not silently use it as validated sizing.
- No valid edge estimate but valid entry/stop/portfolio risk data: show fixed-risk/concentration sizing as a **risk-only fallback**, not as Kelly.
- Abstain from a numeric guide only when the inputs are too incomplete to support either an edge fraction or a defensible risk-only cap.

A cap is not automatically a recommendation. For example, a 5% concentration cap only says the position may not exceed 5%; it does not prove that 5% is appropriate.

## 8. HTML/report fields

The reader-facing risk module should make the calculation inspectable. Prefer these fields:

- setup IDs and match status;
- total/OOS trade counts and confidence tier;
- `p`, `b`, average win, average loss;
- full-sample and OOS empirical log-growth Kelly;
- full-sample and OOS `p/b` formula Kelly;
- selected diagnostic source and base Kelly;
- current RV, reference RV, daily sigma and RV regime haircut;
- option/event haircut and combination policy;
- full / half / quarter theoretical fractions;
- the same three fractions after caps;
- binding cap for each variant;
- approximate NAV one-sigma contribution for each variant;
- notional/shares when an account size is supplied;
- `guidance_status`, `guidance_variant`, `guidance_fraction`, and why it is or is not validated.

The HTML should visually show all three variants, not bury them in prose. A bar or ladder chart should distinguish the theoretical post-overlay fraction from the final fraction after portfolio caps.
