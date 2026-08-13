# {{SYMBOL}} research note

## Research posture

- As-of: {{AS_OF}}
- Evidence cutoff: {{EVIDENCE_CUTOFF}}
- Price timestamp / provider: {{PRICE_STATUS}}
- Filings cutoff: {{FILINGS_CUTOFF}}
- Evidence completeness: {{EVIDENCE_COMPLETENESS}}
- Research state: `RESEARCH_READY` / `READY_CONDITIONAL` / `WAIT_CONFIRMATION` / `NEEDS_EVIDENCE` / `RISK_BLOCKED` / `MONITOR_ONLY` / `THESIS_INVALIDATED`
- Primary horizon: {{HORIZON}}
- Data limitations: {{LIMITATIONS}}

## Thesis and variant perception

**Thesis:** {{THESIS}}

**Variant perception / what may be mispriced:** {{VARIANT}}

**What the market appears to expect:** {{EXPECTATIONS}}

**Key evidence:** {{EVIDENCE}}

**Invalidation:** {{INVALIDATION}}

## What changed since the prior evaluation

If no prior evaluation exists, say so. Otherwise lead with the delta rather than repeating the old report.

| New/changed item | Source/evidence ID | Claim affected | Direction | Materiality | Prior view -> updated view | PIT-safe? |
|---|---|---|---|---|---|---|

## Catalyst, macro, and expectation context

### Company and scheduled catalysts

Separate reported company events from scheduled events and third-party commentary.

### Industry read-through

Include only industry/competitor evidence with a stated causal link to the company thesis.

### Macro exposure map

Show the company exposure, the selected FRED/ALFRED series, why it matters, and whether the current/vintage value supports or weakens the thesis.

### Consensus and revisions

Keep management guidance, Street consensus, and the internal model separate. Prefer revision direction/dispersion over a point estimate alone.

### Insider / market-implied / crowding context

Treat SEC Form 4, Polymarket, FINRA Reg SHO, and Stocktwits according to their evidence roles. Do not call FINRA short-sale volume short interest; do not call social attention a fundamental fact.

## Module results

### Business and fundamentals

Separate reported facts, company claims, Street estimates, derived metrics, and interpretation. Include sector KPIs, capital intensity, leverage, capital allocation, and source IDs.

### Valuation

Show current price/EV inputs, method, forecast period, scenarios, and sensitivity. Mark missing share count, debt, lease, or consensus inputs as `UNVERIFIED`/`needs_source`. Explicitly compare internal model, Street consensus, management guidance, and current market price when inputs exist.

### Technical setup

Show trend, momentum, support/resistance, volume limitations, and whether compression has a confirmed direction.

### Options-implied risk

Use [../references/options-volatility.md](../references/options-volatility.md) and [../references/gamma-structure.md](../references/gamma-structure.md). For nightly/full single-stock research, keep the options chapter in this fixed order so data quality is visible before interpretation.

#### 1. Options data quality

- Current-chain source / retrieval timestamp / data type: IBKR live, IBKR delayed/frozen, `tws-pro` last-chain, Massive historical, or yfinance research chain
- Selected expiries / strike mode (`full_expiry` or bounded ATM) / number of rows returned
- Spot `S` and provenance; disclose any substitution for a stale or premarket `_ref_price`
- Quote coverage: bid/ask rows, last-only rows, open-interest rows, Greeks rows; explicitly list missing fields
- Gamma inputs: rows with usable IV/gamma, rows with OI, rows with both gamma+OI, `gamma_oi_coverage_ratio`, and whether full-chain acquisition was requested
- Staleness, zero/crossed quotes, invalid contract combinations, wide spreads, missing expiries, event-date, and cross-source conflict flags
- Evidence grade: `A` executable/timestamped quote, `B` timestamped last/aggregate with model IV, `C` historical/research fallback, `D` discovery-only or materially incomplete gamma/OI coverage

#### 2. Implied volatility and expected move

- ATM last-price IV: numerical Black-Scholes inversion, with option type, expiry, `T`, and price source
- ATM straddle diagnostic: `straddle / S * sqrt(pi / (2T))`; label as approximation, not executable IV
- Front/back comparison using total variance `sigma^2*T`; do not compare raw IVs without accounting for `T`
- Skew: 25-delta when delta exists, otherwise documented log-moneyness proxy; state if only a narrow strike slice is available
- Volume/OI ratios as activity distribution only; never infer buy/sell or opening/closing direction

#### 3. Gamma structure

Run `scripts/options_gamma_structure.py` on the reconciled/provider option packet when IV and OI coverage permit it.

Report:

- largest upper and lower **gross gamma concentrations** and distance from spot;
- top gamma concentrations by strike and selected expiry coverage;
- gross gamma notional for a 1% spot move, including the near-spot band (default ±3%);
- call/put OI observed at those strikes and OI coverage;
- `gross_gamma_notional_per_1pct_spot = gamma * OI * 100 * S^2 * 0.01` as an unsigned hedge-sensitivity proxy.

Do not rename this output `dealer GEX`. Do not call an upper concentration resistance or a lower concentration support unless independent price/flow evidence supports that interpretation.

#### 4. Dealer-hedging scenarios

If dealer position sign is not independently observed/inferred, show both bounding cases and mark them `ASSUMPTION_ONLY`:

- dealer short gamma -> potentially procyclical hedge flow;
- dealer long gamma -> potentially countercyclical hedge flow.

`gamma_flip` must be `UNAVAILABLE_WITHOUT_POSITION_SIGN` unless a documented signed-exposure model exists. A `gamma squeeze` is `CONDITIONAL_ONLY`, not a fact inferred from OI or gamma concentration alone.

#### 5. Technical + gamma confluence

Compare gamma concentrations with technical support/resistance, VWAP, intraday volume/activity acceleration, and price response. Highlight coincident levels as **confluence / attention zones**, not mechanical support/resistance. If intraday analysis reuses prior-close OI/IV with live spot, label the output `STATIC_GAMMA_MAP` and show separate `oi_as_of`, `iv_as_of`, and `spot_as_of` timestamps.

### Backtest / historical validation

State the tested rule, window, costs, trade count, full-sample result, OOS result, regime dependence, and selection-bias limitations. Do not use a backtest to validate a different horizon or signal definition than the one actually tested.

## Claim Graph summary

For full research, include the material claims only; keep the complete machine-readable graph as an audit artifact.

| Claim ID | Type | Horizon | Statement | Direction | Status | Confidence | Evidence / dependencies | Invalidation |
|---|---|---|---|---|---|---:|---|---|

## Adversarial review

Do not write three long role-play essays. Summarize the strongest claim-level interventions.

### Bull reviewer

- Strongest supported upside case:
- Underweighted evidence:
- Claims to strengthen:
- Evidence requests:

### Bear reviewer

- Strongest plausible non-catastrophic downside case:
- Alternative explanation:
- Expectation/valuation fragility:
- Claims to weaken/invalidate:
- Evidence requests:

### Skeptic reviewer

- PIT/timestamp problems:
- Evidence-label violations:
- Model/horizon mismatches:
- Double counting / unsupported causal links:
- Claims to mark unresolved:

## Research Arbiter

- Research state: {{RESEARCH_STATE}}
- Thesis state: {{THESIS_STATE}}
- Supported claims: {{SUPPORTED_CLAIMS}}
- Contested claims: {{CONTESTED_CLAIMS}}
- Unresolved claims: {{UNRESOLVED_CLAIMS}}
- Binding evidence/risk constraint: {{BINDING_CONSTRAINT}}
- Next evidence requests: {{NEXT_EVIDENCE}}

### Scenario probability change log

Numeric scenario probabilities are `ASSUMPTION` unless calibrated otherwise.

| Case | Prior | Review delta | Final | Reason / claim IDs / evidence IDs |
|---|---:|---:|---:|---|
| Bear | | | | |
| Base | | | | |
| Bull | | | | |
| Event / unknown | | | | |

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

List evidence ID, source/provider, endpoint/URL/path, published/observation time, retrieved/received time, period, raw identifier, evidence role/grade, stale flag, PIT status, and notes. End with unresolved evidence requests and monitoring triggers.

## Decision-memory record

When decision memory is enabled, freeze this section before outcomes are known:

```text
run_id
symbol
as_of
evidence_cutoff
primary_horizon
research_state
scenario_probabilities
expected_range (if estimated)
thesis_claim_ids
key_invalidation_conditions
action_boundary
benchmark
```

Do not put realized outcome or hindsight reflection in the ex-ante block. Attach those later in the P3 outcome/calibration record.
