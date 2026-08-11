# Catalyst, macro, expectations, and crowding context

Use this module to answer **what changed, what is scheduled, and what the market appears to expect**. It is a context layer, not a standalone directional signal.

## Source roles

Use the tested project sources by role:

### Primary/company evidence

- SEC submissions/companyfacts and filing documents: 10-K, 10-Q, 8-K, Form 4.
- Issuer investor-relations pages/releases/presentations.

These can establish reported facts or company claims, subject to the evidence policy.

### Macro/PIT

- FRED for current macro series.
- ALFRED/FRED vintage parameters for historical point-in-time analysis.

Never use today's revised macro value as if it were known at a historical `as_of`.

### News/catalyst

- IBKR News for timestamped market/company headlines and selected article bodies.
- Finnhub news as a complementary feed when useful.
- Do not count duplicate/syndicated headlines as independent evidence.

### Market expectations

- Alpha Vantage `EARNINGS_ESTIMATES`, transcripts, and earnings calendar.
- Management guidance from SEC/IR remains distinct from Street consensus.

Represent the key comparison explicitly:

`our model vs consensus vs management guidance vs current market price`.

### Market-implied event context

- Polymarket Gamma/CLOB public data only when a company thesis maps to a relevant external event.
- Label the output `MARKET_IMPLIED_EXPECTATION`; it is not an objective event probability or company forecast.

### Crowding/attention proxies

- FINRA Reg SHO daily short-sale volume: label `SHORT_SALE_FLOW_PROXY`, not short interest.
- Stocktwits legacy stream: low-confidence retail attention/sentiment context only.
- Reddit: unavailable unless OAuth/current official approval is configured; do not scrape around the restriction.

## Catalyst taxonomy

Classify every catalyst into one of:

- `company_reported`: earnings, guidance, KPI, capital allocation, contract, management, M&A, litigation;
- `company_scheduled`: earnings date, investor day, vote, regulatory deadline;
- `industry`: competitor result, capacity, pricing, supply/demand, customer read-through;
- `macro`: rates, inflation, labor, growth, FX, commodity, policy;
- `regulatory_geopolitical`: sanctions, export controls, tariffs, approvals, court/policy events;
- `market_expectation`: consensus revision, implied event probability, crowding/attention shift.

## Delta-first analysis

Do not write a generic seven-day news summary when a prior evaluation exists. First answer:

1. What evidence is new since the previous evaluation?
2. Which existing claim does each new item support, weaken, invalidate, or leave unchanged?
3. Did consensus, guidance, event probability, or macro regime change?
4. Which scenario probability should change, if any?
5. What remains unresolved?

Recommended output:

| New item | Evidence type | Claim affected | Direction | Materiality | Prior -> updated view | PIT-safe? |
|---|---|---|---|---|---|---|

## Expectation-revision rules

Treat consensus as `street_estimate`, not `FACT`.

For each available horizon capture:

```text
period
metric (EPS/revenue/etc.)
mean/median if available
high/low if available
analyst_count
revision timestamp/window
previous estimate
current estimate
revision direction and magnitude
```

Prefer revision **change** and dispersion over a point estimate in isolation. Do not infer causality from a revision unless the supporting event is separately sourced.

## Insider rules

Use SEC Form 4 and classify the transaction code before interpretation. Distinguish open-market purchase, sale, grant, exercise, tax withholding, and other/non-discretionary activity. Preserve owner role, direct/indirect ownership, transaction date, price, shares, post-transaction holdings, and disclosed 10b5-1 context where available.

An insider sale is not automatically bearish; an open-market purchase may be informative but remains one evidence item.

## Macro exposure mapping

Do not inject every FRED series into every stock. Select macro evidence through a causal exposure map, for example:

- rates/duration sensitivity;
- credit/funding sensitivity;
- commodity/input sensitivity;
- FX/geography sensitivity;
- industrial-cycle sensitivity;
- consumer/labor sensitivity.

The report must state why each macro series is relevant to the company thesis.

## Output contract

The module returns:

```text
as_of
previous_evaluation_as_of (if any)
new_company_catalysts
scheduled_catalysts
industry_readthroughs
macro_exposures_and_changes
consensus_and_revision_delta
insider_context
market_implied_event_context
crowding_attention_context
material_claim_updates
unresolved_evidence_requests
```

Do not convert any one context signal into a mechanical buy/sell recommendation.
