# Distilled adversarial research governance

This reference distills the useful research-organization mechanisms of multi-agent trading frameworks into this evidence-backed stock-evaluation skill. It does **not** add autonomous trading agents, order execution, or a second data-access stack.

## Design goal

Preserve the existing deterministic/evidence-first workflow and add only four governance mechanisms:

1. `Evidence Freeze` — all reviewers see the same point-in-time evidence packet.
2. `Claim Graph` — material conclusions are explicit, typed, sourced claims rather than prose-only assertions.
3. `Bull / Bear / Skeptic Review` — three constrained review passes attack different failure modes.
4. `Research Arbiter` — reconciles disputes and scenario probabilities without inventing new facts.

A fifth mechanism, `Decision Memory`, records the ex-ante research state and later realized outcomes for calibration. See [decision-memory.md](decision-memory.md).

## Non-negotiable boundary

These roles are **reasoning passes inside the skill**, not independent data-acquisition agents.

After `Evidence Freeze`:

- reviewers may cite only evidence IDs and claim IDs already present in the frozen packet;
- reviewers may request missing evidence, but must not silently acquire or substitute it during the review pass;
- repeated headlines or copied syndication are one information event, not independent confirmation;
- the Arbiter cannot add a new `FACT`, `DATA_RESULT`, or external citation;
- if a requested fact is absent, output an `evidence_request` and downgrade confidence.

This prevents source drift, timestamp drift, hidden PIT contamination, and debate-by-hallucination.

## Research-state machine

Use these states instead of a mechanical BUY/HOLD/SELL label:

- `RESEARCH_READY`: evidence packet is sufficient for underwriting, but no tactical condition has been evaluated.
- `READY_CONDITIONAL`: thesis is supportable and a defined action condition exists.
- `WAIT_CONFIRMATION`: thesis may be valid but a price/event/technical condition has not confirmed.
- `NEEDS_EVIDENCE`: a material claim cannot be resolved with the frozen evidence.
- `RISK_BLOCKED`: thesis may be valid but risk, liquidity, event, or sizing constraints bind.
- `MONITOR_ONLY`: no sufficiently differentiated edge is established.
- `THESIS_INVALIDATED`: one or more declared thesis invalidation conditions have occurred.

The report may describe conditional entry/add/trim/exit boundaries, but the skill must not place an order.

## Stage contract

### Stage 0 — Acquire and normalize

Acquire only the data required by the selected modules. Preserve source, raw identifier, publication/observation time, retrieval time, live/delayed status, and provider errors.

### Stage 1 — Evidence Freeze

Create an immutable logical packet for this research run. At minimum record:

```text
run_id
symbol
as_of
filing_cutoff
evidence_cutoff
provider_status
raw_evidence_ids
missing_evidence
```

For historical replay, an item is usable only if `observed_at/received_at <= evidence_cutoff`. Prefer system-observed time over publication time when both exist. Use [schemas/evidence-manifest.schema.json](../schemas/evidence-manifest.schema.json) as the machine-readable freeze contract.

### Stage 2 — Deterministic modules

Run technical, valuation, options/volatility, macro/catalyst, backtest, and risk calculations. Calculations produce `DATA_RESULT` or `MODEL_OUTPUT`, never facts.

### Stage 3 — Claim Graph

Represent every material thesis statement as a claim with:

```text
claim_id
statement
claim_type
horizon
direction
supporting_evidence_ids
counterevidence_ids
depends_on
confidence
invalidation_conditions
status
```

Allowed `claim_type` values:

- `FACT`
- `DATA_RESULT`
- `MODEL_OUTPUT`
- `INFERENCE`
- `ASSUMPTION`
- `UNVERIFIED`

Allowed `direction` values: `positive`, `negative`, `neutral`, `mixed`.

Allowed `status` values: `supported`, `contested`, `unresolved`, `invalidated`.

An `INFERENCE` must cite at least one supporting evidence ID or upstream claim ID. A `FACT` must cite a primary/trusted evidence ID. An `UNVERIFIED` claim must not be used as the sole basis for an action condition.

Use [schemas/claim-graph.schema.json](../schemas/claim-graph.schema.json) as the machine-readable contract.

## Bull Reviewer

Purpose: construct the strongest **evidence-supported** positive/upside interpretation, not cheerlead.

Required outputs:

- strongest supported positive claims;
- positive evidence the base thesis underweights;
- plausible upside causal chain;
- claims that should receive higher confidence or scenario weight;
- specific evidence requests that could materially strengthen the case.

Forbidden:

- inventing catalysts;
- treating social sentiment as fundamental evidence;
- treating option activity as directional flow;
- increasing probability because multiple feeds copied the same story.

## Bear Reviewer

Purpose: identify the most plausible non-catastrophic ways the thesis can be wrong.

Required attack surface:

- alternative explanation for the same observed data;
- weak links in revenue/earnings quality, cash conversion, leverage, capital intensity, or valuation;
- regime dependence and catalyst asymmetry;
- expectation risk: good company / bad stock because expectations are already too high;
- technical, volatility, liquidity, or event contradictions;
- declared invalidation conditions that may be too loose or too late.

At least one bear path must be plausible without assuming an extreme market crash.

## Skeptic Reviewer

Purpose: attack **epistemic and methodological validity**, not direction.

Check for:

- estimate presented as fact;
- management claim presented as independently verified;
- revised macro data used in a historical PIT run;
- post-event information leaking into a pre-event analysis;
- low multiple equated with undervaluation;
- oversold indicator equated with a buy signal;
- option volume/OI equated with buyer/seller or opening/closing direction;
- short-sale volume equated with consolidated short interest;
- correlation or coincident timing presented as causation;
- stale or mismatched timestamps/timezones;
- conflicting provider values silently averaged;
- duplicated evidence counted twice;
- model horizon mismatched to action horizon;
- backtest selection bias, small sample, missing OOS, or cost omission;
- double counting the same economic driver across several scores.

The Skeptic may downgrade a claim even when both Bull and Bear agree on direction.

## Review format

Each reviewer returns a structured object compatible with [schemas/review.schema.json](../schemas/review.schema.json). The key unit is a claim challenge/update, not a long free-form essay.

Recommended shape:

```json
{
  "reviewer": "bear",
  "claim_reviews": [
    {
      "claim_id": "NVDA-20260807-FUND-003",
      "assessment": "weaken",
      "reason": "...",
      "evidence_ids": ["SEC-..."],
      "confidence_delta": -0.10
    }
  ],
  "scenario_probability_deltas": {
    "bull": -0.03,
    "base": -0.02,
    "bear": 0.05,
    "unknown": 0.00
  },
  "evidence_requests": []
}
```

Probability deltas are analyst assumptions. They must explain their evidence basis and must not be treated as calibrated probabilities until P3 calibration supports that interpretation.

## Research Arbiter

The Arbiter reads only:

- frozen evidence manifest;
- deterministic module outputs;
- Claim Graph;
- Bull review;
- Bear review;
- Skeptic review.

It then produces a payload compatible with [schemas/arbitration.schema.json](../schemas/arbitration.schema.json):

```text
research_state
thesis_state
material_supported_claims
material_contested_claims
material_unresolved_claims
scenario_probabilities
probability_change_log
confidence
binding_risk_or_evidence_constraint
action_boundary
next_evidence_requests
```

Rules:

1. The Arbiter may resolve a disagreement only by reference to existing evidence/claims or by leaving it unresolved.
2. Scenario probabilities must sum to 1 when numeric. If they cannot be defended, use qualitative confidence and `not_estimated`.
3. Every probability adjustment must be logged as `prior -> delta -> final` with a reason and claim/evidence IDs.
4. A Skeptic finding of PIT leakage, stale identity, invalid data, or material evidence conflict can force `NEEDS_EVIDENCE` regardless of Bull/Bear direction.
5. Risk/sizing constraints are applied after thesis arbitration; a good thesis can still become `RISK_BLOCKED`.
6. The Arbiter does not output an order.

## When to run the distilled reviews

Run Bull/Bear/Skeptic + Arbiter for:

- `full-research`;
- explicit investment-thesis underwriting;
- material pre/post-earnings evaluations;
- a user request to challenge, debate, stress-test, or update an existing thesis.

Do **not** automatically run them for a narrow quote lookup, one indicator calculation, an options-chain diagnostic, or a mechanical backtest request.

## Distillation map: what is absorbed and what is deliberately not copied

| Multi-agent framework capability | This skill | Decision |
|---|---|---|
| Fundamental analyst | existing `fundamental-deep-dive` + SEC/IR evidence | keep existing deterministic/evidence-first module |
| Technical analyst | existing deterministic technical engine | do not add an LLM technical agent |
| News analyst | `catalyst-context` + IBKR News + FRED/ALFRED + expectations | absorb as a structured context module |
| Sentiment analyst | FINRA/Stocktwits/Polymarket role-specific overlays | optional context only; never a core score |
| Bull researcher | Bull Reviewer | absorb as constrained claim review |
| Bear researcher | Bear Reviewer | absorb as constrained claim review |
| Research manager | Research Arbiter | absorb, but prohibit new facts and majority-vote logic |
| Risk debate | existing risk engine + explicit binding risk constraint | absorb only the risk-lens discipline, not free-form role play |
| Portfolio manager | research-state/action-boundary output | do not turn this skill into portfolio management |
| Trader agent | none | deliberately excluded |
| Order execution | none | deliberately excluded |
| Persistent decision log/reflection | Decision Memory + structured calibration | absorb and strengthen with PIT/outcome metrics |
| Checkpoint/resume concept | local run artifacts/manifests | use at research-run level; no MCP change required |

The guiding rule is: **LLMs challenge interpretations; deterministic code computes metrics; sources establish evidence; the Arbiter reconciles without trading.**
