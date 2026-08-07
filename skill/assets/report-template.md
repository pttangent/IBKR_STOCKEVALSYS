# {{SYMBOL}} research note

## Research posture

- As-of: {{AS_OF}}
- Price timestamp / provider: {{PRICE_STATUS}}
- Filings cutoff: {{FILINGS_CUTOFF}}
- Evidence completeness: {{EVIDENCE_COMPLETENESS}}
- Evidence freeze: {{EVIDENCE_FREEZE_HASH}}
- Underwriting status: preliminary / watchlist / ready for deeper work
- Primary horizon: {{HORIZON}}
- Data limitations: {{LIMITATIONS}}

## Thesis and debate

**Thesis:** {{THESIS}}

**Variant perception / what is priced in:** {{VARIANT}}

**Key evidence:** {{EVIDENCE}}

**Invalidation:** {{INVALIDATION}}

## Catalyst, macro, and expectations context

- What changed since the previous evaluation: {{DELTA_SINCE_PREVIOUS}}
- Company / sector catalysts: {{CATALYSTS}}
- Macro transmission channels and selected FRED/ALFRED evidence: {{MACRO_CONTEXT}}
- Company guidance vs consensus vs internal model: {{EXPECTATION_GAP}}
- Optional prediction-market context: {{PREDICTION_MARKET_CONTEXT}}

Do not include a current consensus, social, or prediction-market snapshot in historical replay unless its availability at the research cutoff is proven.

## Adversarial review and arbitration

### Bull review
{{BULL_REVIEW}}

### Bear review
{{BEAR_REVIEW}}

### Skeptic / methodology review
{{SKEPTIC_REVIEW}}

### Research Arbiter

- Thesis state: {{THESIS_STATE}}
- Material claim changes: {{CLAIM_ADJUSTMENTS}}
- Scenario probability changes and reasons: {{SCENARIO_ADJUSTMENTS}}
- Unresolved evidence requests: {{EVIDENCE_REQUESTS}}

The reviewers and Arbiter may cite only source IDs in the frozen evidence packet. A missing source must remain a request or `UNVERIFIED`; do not fill it from memory.

## Module results

### Business and fundamentals

Separate reported facts, estimates, derived metrics, and interpretation. Include sector KPIs, capital intensity, leverage, capital allocation, and source IDs.

### Valuation

Show current price/EV inputs, method, forecast period, scenarios, and sensitivity. Mark missing share count, debt, lease, or consensus inputs as `needs_source`.

### Technical setup

Show trend, momentum, support/resistance, volume limitations, and whether compression has a confirmed direction.

### Options-implied risk

#### Options-chain evidence

- Current-chain source / retrieval timestamp / data type: IBKR live, IBKR delayed/frozen, `tws-pro` last-chain, Massive historical, or yfinance fallback
- Selected expiries / strike window / number of rows returned
- Spot `S` and provenance; disclose any substitution for a stale or premarket `_ref_price`
- Quote coverage: bid/ask rows, last-only rows, open-interest rows, Greeks rows; explicitly list missing fields
- ATM last-price IV: numerical Black-Scholes inversion, with option type, expiry, `T`, and price source
- ATM straddle diagnostic: `straddle / S * sqrt(pi / (2T))`; label as approximation, not executable IV
- Front/back comparison using total variance `sigma^2*T`; do not compare raw IVs without accounting for `T`
- Skew: 25-delta when delta exists, otherwise documented log-moneyness proxy; state if only a narrow strike slice is available
- Volume/OI ratios as activity distribution only; never infer buy/sell or opening/closing direction
- Staleness, zero/crossed quotes, invalid contract combinations, wide spreads, missing expiries, event-date, and cross-source conflict flags
- Evidence grade: `A` executable/timestamped quote, `B` timestamped last/aggregate with model IV, `C` historical/fallback, `D` discovery-only

### Risk plan

Organize this section by horizon. For the short-horizon block, use this reader-facing order: `Today's short-horizon scenario tree` → `Entry confirmation and invalidation` → `Stop-loss / take-profit and P/L ladder` → `Short-horizon Kelly position plan`. Keep all four on the same entry, stop, target, account, and risk assumptions. Then place the long-horizon scenarios, options event-risk interpretation, and long-horizon position boundary together afterward. Show entry/stop assumption, a labeled simulation account (default $10,000 if unspecified), portfolio risk budget, concentration cap, `p`, `b`, `f_raw`, exploratory/full-sample Kelly, OOS Kelly, full Kelly, half Kelly, quarter Kelly, confidence tier, option-volatility/event haircut, known tail/fixed-risk caps, `diagnostic_fractional_kelly_cap`, `applied_fractional_kelly`, allowed dollar amount, exact fractional-share conversion, optional integer shares, binding constraint, and invalidation. If standard OOS qualification fails, the diagnostic ratio is still mandatory; label it exploratory/conditional, list the exact trade-count gap and missing cap inputs, and keep fixed-risk sizing as the default. The P/L ladder must show per-share and dollar loss/profit using the exact fractional quantity implied by the allowed amount; integer-share comparison is optional. For today's timing, include session phase, ORH/ORL, VWAP, dynamic support/resistance, conditional entry, stop, target, and no-trade criteria. Never reuse same-day opening-range levels as long-horizon stops without recomputing the position.

## Scenarios

Every material inference must be tested against multiple paths. Use at least four cases and do not reuse example probabilities or price levels from another ticker.

| Case | Probability (assumption) | Evidence/facts | Model implication | Price/risk path | Trigger | Invalidation | Action boundary |
|---|---:|---|---|---|---|---|---|
| Bear | | | | | | | |
| Base | | | | | | | |
| Bull | | | | | | | |
| Event / unknown | | | | | | | |

## Source register and missing evidence

List source ID, provider, URL/path, published/accessed time, period, reliability, stale flag, and notes. End with unresolved evidence requests and monitoring triggers.
