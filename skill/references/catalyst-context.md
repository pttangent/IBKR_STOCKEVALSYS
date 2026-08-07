# Catalyst, macro, and expectation context

The catalyst module answers **what changed, what is scheduled, and what external state can move the thesis**. It is not a generic news summary.

## Output blocks

### Company events

Capture earnings, guidance changes, 8-K events, management changes, M&A, contracts, product/regulatory events, financing, litigation and material customer/supplier developments. Prefer SEC/IR evidence.

### Sector events

Include only events with a causal path to revenue, margins, capex, demand, supply, valuation or risk. State that path explicitly.

### Macro exposure

Select FRED/ALFRED series based on the company's actual sensitivities. A macro series with no stated transmission channel should not enter the scorecard.

### Scheduled catalysts

List event, expected date/time, source, what is priced/expected when evidence exists, and the variables that would invalidate the current scenario distribution.

### Delta since previous evaluation

When a prior evaluation exists, produce a change log:

| Item | Previous state | New evidence | Claim affected | Scenario effect |
|---|---|---|---|---|

Do not rewrite unchanged background as "new" catalyst evidence.

## Consensus/variant perception

When Alpha Vantage or another approved estimate source is available, compare:

`company guidance vs consensus vs internal model vs current market price`

Treat estimate revisions as expectation changes. Do not use a current consensus snapshot in historical replay unless the estimate/revision timestamp is at or before the historical cutoff.

## Prediction-market context

Use Polymarket only for a directly linked binary/event question (e.g., regulation, policy, election, geopolitical action). A probability from a thin or ambiguously worded market should be ignored or given low confidence.
