# Reusable reasoning framework

This reference distills the supplied VST report method into a reusable, parameterized workflow. Do not copy VST prices, dates, weights, score cutoffs, peer multiples, or conclusions into another ticker. Replace them with the current ticker's observed data and disclose the replacement.

## Evidence labels

Tag every material statement as one of:

- `FACT`: directly observed from a filing, provider packet, official company release, or cited public source.
- `DATA_RESULT`: deterministic calculation from named inputs, such as MA, RSI, realized volatility, IV, P/C ratio, or backtest statistics.
- `MODEL_OUTPUT`: a formula, score, scenario probability, sizing adjustment, or sensitivity generated from the data.
- `INFERENCE`: analyst interpretation linking evidence to an investment thesis.
- `ASSUMPTION`: an explicit input that is not directly observed, such as scenario probability, holding horizon, or forecast multiple.
- `UNVERIFIED`: a missing, stale, conflicting, or entitlement-limited claim that must not be presented as fact.

Never collapse these labels in prose. A report should make the chain visible:

`FACT -> DATA_RESULT -> MODEL_OUTPUT -> INFERENCE -> ACTION CONDITION`

## Reusable pipeline

1. Acquire raw packets without interpretation. Record `as_of`, provider, endpoint/tool, session, publication/observation time, retrieval/received time, quote type, and missing fields.
2. Normalize symbols, dates, currency, adjusted/unadjusted status, option keys, source quality, and evidence IDs.
3. **Freeze the evidence set** for the run. In a historical run, exclude anything not observable by the evidence cutoff. Reviewers do not independently reacquire data after this point.
4. Calculate deterministic features from the normalized packets.
5. Generate independent technical, fundamental, valuation, options, catalyst/macro/expectation, and risk signals. Do not let one module overwrite another.
6. Convert material conclusions into a **Claim Graph** using `FACT`, `DATA_RESULT`, `MODEL_OUTPUT`, `INFERENCE`, `ASSUMPTION`, or `UNVERIFIED`, with supporting/counterevidence IDs and invalidation conditions.
7. Build at least four scenarios: `base`, `bull`, `bear`, and `invalidated/unknown`. Add an `event` scenario when a dated catalyst can change the distribution.
8. Assign probabilities only as labeled assumptions. Make them sum to 100% and keep a change log showing which evidence/claim moved each scenario.
9. For `full-research` or thesis underwriting, run the constrained **Bull / Bear / Skeptic** review passes from `distilled-research-governance.md` against the same frozen Claim Graph. Reviewers may request evidence but may not silently fetch new sources.
10. Run the **Research Arbiter**. It may strengthen/weaken/leave unresolved existing claims and scenarios, but it cannot create facts. Output a research state such as `READY_CONDITIONAL`, `WAIT_CONFIRMATION`, `NEEDS_EVIDENCE`, `RISK_BLOCKED`, `MONITOR_ONLY`, or `THESIS_INVALIDATED` rather than a mechanical BUY/HOLD/SELL label.
11. Convert the result into conditional actions: entry/add, wait, trim, exit, or collect more evidence. State the trigger and the invalidation condition.
12. Run a backtest or historical validation when a rule is claimed to have an edge. Separate full-sample and out-of-sample results and disclose window-selection bias.
13. Apply risk caps after thesis arbitration: fixed-risk budget, tail-loss cap, concentration cap, liquidity constraints, and event haircut. The smallest cap binds.
14. When decision memory is enabled, freeze the ex-ante decision record before outcomes are known; attach realized outcomes later and compute calibration before writing a reusable reflection.

## Technical inference template

Calculate, where history permits:

- MA/EMA alignment and price distance from MA;
- RSI, MACD, Bollinger position and bandwidth;
- realized volatility, range expansion/contraction, gap behavior;
- volume profile/POC or a clearly labeled price-volume proxy;
- up-volume versus down-volume, without assuming trade direction;
- support/resistance from observed pivots and volume concentration.

Use the following reasoning examples as templates, not as hard-coded rules:

### Trend continuation

`FACT`: price is above a rising long-horizon average and shorter averages are positively aligned.

`DATA_RESULT`: momentum and volume confirm, weaken, or conflict with the alignment.

`MODEL_OUTPUT`: continuation score increases only when at least two independent dimensions agree.

Scenarios:

1. `base`: trend persists; trigger is a hold/retest of the reference zone; monitor momentum decay.
2. `bull`: breakout plus volume expansion; trigger is a close above the observed resistance; action is add only within the risk cap.
3. `bear`: failed breakout or loss of the reference average; trigger is a confirmed close below support; action is reduce or wait.
4. `invalidated`: missing/late bars, corporate-action mismatch, or cross-source price disagreement; action is no directional inference.

### Mean reversion after exhaustion

`FACT`: price is near a lower volatility band or an observed support zone.

`DATA_RESULT`: RSI/MACD, range, and volume distinguish oversold from ongoing trend damage.

`INFERENCE`: oversold is a setup condition, not a buy signal.

Scenarios:

1. `rebound`: price reclaims the reference zone and momentum turns; use a predefined stop and a moving exit.
2. `sideways`: price remains inside the band; wait for compression resolution.
3. `continuation_down`: the support breaks with expanding range/volume; do not average down merely because RSI is low.
4. `false_signal`: the band calculation is distorted by a split, stale bar, or thin trading; discard the signal.

## Fundamental inference template

Separate reported results, estimates, derived ratios, and interpretation. Cover business drivers, revenue/earnings quality, cash conversion, leverage, capital allocation, sector KPIs, and catalysts. For each material valuation conclusion, identify the denominator and the reason it may be non-comparable.

Scenarios:

1. `execution/base`: management delivers the currently supportable operating assumptions.
2. `upside`: the specific KPI or catalyst beats the assumption and the market rerates or estimates rise.
3. `downside`: the KPI misses, guidance falls, or leverage/capital intensity constrains equity value.
4. `event/regime`: rates, regulation, commodity/input prices, customer concentration, or a transaction changes the valuation regime.
5. `unknown`: a key filing, segment disclosure, or share-count/debt input is unavailable; show a valuation range rather than a point estimate.

Do not infer “cheap” from a low multiple alone. Explain whether the discount compensates for growth quality, leverage, cyclicality, execution, or data uncertainty.

## Options-linked inference template

Use the three-source protocol in `options-multi-source.md`. Treat options as a distribution/risk input for the stock thesis, not automatic directional flow.

Calculate only from aligned spot, expiry, strike, price source, and timestamp:

- numerical IV when the price is positive and the contract is valid;
- ATM straddle IV as a diagnostic approximation;
- front/back total variance, not raw IV alone;
- log-moneyness or 25-delta skew when the necessary fields exist;
- volume and OI as activity distributions, never as proof of opening, closing, buying, or selling.

Scenarios:

1. `priced-in event`: front variance is elevated versus back variance; the stock needs a positive surprise to overcome the premium.
2. `underpriced event`: realized move or fundamental catalyst plausibly exceeds the option-implied distribution; this is a hypothesis requiring historical/event evidence.
3. `downside hedge demand`: put-side pricing is elevated relative to the comparable call/ATM surface; increase tail-risk haircut, not a directional short signal.
4. `volatility crush`: the event passes and front variance falls; stock direction and option premium outcome can diverge.
5. `data conflict`: provider prices or timestamps disagree materially; preserve source-specific values and do not blend into a false consensus.

## Kelly and risk-sizing template

Estimate `p` and payoff ratio `b` from a ticker-specific, time-ordered backtest. Report trade count, window, costs, exits, and OOS qualification. The raw Kelly fraction is:

`f_raw = (p*b - (1-p)) / b`

Then apply a declared fractional-Kelly multiplier, option/event volatility haircut, tail-loss cap, and single-name cap:

`f_final = min(fractional_kelly * f_raw * event_haircut, tail_cap, concentration_cap, fixed_risk_cap)`

If the backtest has too few trades or no valid OOS segment, still calculate and display the available `f_raw`, fractional-Kelly ratio, haircut, and diagnostic cap with a low-confidence label. Mark it `conditional_insufficient_data`; use fixed-risk sizing by default and do not turn the diagnostic into a validated Kelly recommendation.

Every reader-facing report must distinguish:

- `diagnostic_fractional_kelly_cap`: the available ratio after the declared formula and known caps, shown even with short samples;
- `applied_fractional_kelly`: the ratio actually passed to automatic position sizing, which may be null;
- `qualification_status`: exploratory, conditional tactical, or standard validated;
- `missing_cap_inputs`: portfolio value, entry, stop, tail budget, or liquidity data that prevent a complete final cap.

Sizing scenarios:

1. `validated edge`: OOS edge survives costs and the event haircut is modest; size remains below all caps.
2. `edge fragile`: OOS is weak, sample is small, or regime differs; use a smaller fixed-risk position.
3. `tail event`: implied/realized risk or an upcoming catalyst dominates; cap or halve exposure according to the declared rule.
4. `no qualification`: insufficient observations, stale options, or conflicting inputs; no Kelly sizing.

## Scenario-table contract

Every report must include a table with at least these columns:

| Case | Probability (assumption) | Evidence/facts | Model implication | Price/risk path | Trigger | Invalidation | Action boundary |
|---|---:|---|---|---|---|---|---|

Use a minimum of four cases. Add scenario-specific probabilities only after documenting the evidence. If probability cannot be defended, use qualitative confidence and mark the numeric probability `not estimated`.

## Quality checks

- For full research, validate that material thesis claims exist in the Claim Graph and that Bull/Bear/Skeptic reviews refer only to known claim/evidence IDs.
- Include at least one counterevidence paragraph for each positive thesis.
- Include at least one path where the signal fails without requiring a catastrophic event.
- Explain what would change the score or position, rather than presenting a static verdict.
- Keep provider limitations in the conclusion, not only in an appendix.
- Treat consensus, Polymarket, FINRA short-sale volume, and Stocktwits as role-specific context; do not upgrade them into primary facts.
- In historical evaluation, use ALFRED/vintage macro and historical consensus/news when available; otherwise mark the affected module PIT-unavailable.
- Never reuse a VST example number for another ticker.
