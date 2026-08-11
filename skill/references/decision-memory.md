# Decision memory, PIT replay, and calibration

This is the long-term learning layer. It records what the research system believed **before** outcomes were known, then measures what actually happened. Natural-language reflection is secondary to structured calibration.

## Principle

Do not train memory on a rewritten hindsight narrative. Save the ex-ante state first, freeze it, then attach outcomes later.

## Run layout

Recommended local layout:

```text
data/research_runs/
  SYMBOL/
    RUN_ID/
      manifest.json
      evidence_manifest.json
      claim_graph.json
      bull_review.json
      bear_review.json
      skeptic_review.json
      arbitration.json
      decision.json
      outcome.json
      reflection.md
```

The skill may use different storage locations, but the logical separation must remain.

## Decision record

Use [schemas/decision-record.schema.json](../schemas/decision-record.schema.json). At minimum freeze:

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

Do not edit the ex-ante fields after the record is frozen. Corrections should create a new version/run and link to the superseded record.

## Outcome record

Attach outcomes only after the required horizon/event has elapsed. Useful checkpoints:

- T+1 trading day;
- T+5;
- T+20;
- next material scheduled event / earnings date;
- user-defined horizon.

Record, when available:

```text
entry_reference_price
end_price
raw_return
benchmark_return
alpha
max_favorable_excursion
max_adverse_excursion
realized_volatility
observed_scenario
invalidation_triggered
claim_outcomes
```

Outcome classification must not change the original probabilities.

## Calibration metrics

### Scenario probabilities

When exactly one mutually exclusive scenario is resolved, calculate multiclass Brier score:

`Brier = sum((p_i - y_i)^2)`

where `y_i=1` for the observed scenario and `0` otherwise.

Track calibration by probability bucket, horizon, sector, catalyst type, and research-state type once enough samples exist.

### Expected range

Track interval coverage and width:

```text
covered = lower <= realized_price <= upper
range_width_pct = (upper - lower) / reference_price
```

A very wide interval can have high coverage but little information; report both.

### Direction / alpha

Direction accuracy is a diagnostic only. Also record benchmark alpha because a positive absolute return can still be a poor stock-selection call in a strong market.

### Claim calibration

For material claim IDs, record `confirmed`, `weakened`, `invalidated`, or `unresolved` at the evaluation horizon. This enables later questions such as which claim families are consistently reliable.

### Reviewer attribution

When a reviewer materially changes an arbitration result, log the accepted review item. Later measure whether accepted Bull/Bear/Skeptic interventions improved Brier score, avoided invalidated claims, or reduced adverse excursion. Do not optimize reviewers on a handful of anecdotes.

## Reflection contract

Only after structured metrics are computed, write a short reflection:

1. What was predicted correctly?
2. What was wrong or overconfident?
3. Was the error due to evidence, model, timing, regime, or unsupported inference?
4. Which reviewer caught or missed it?
5. Is the lesson ticker-specific or reusable?
6. What concrete rule/evidence request should change next time?

Do not inject an unvalidated prose lesson into every future ticker. Prefer lessons supported by repeated structured outcomes.

## PIT replay

Historical replay must use evidence with `observed_at/received_at <= evidence_cutoff`. Preserve publication time and retrieval time separately. If the historical version of a source cannot be reconstructed, mark that module `PIT_UNAVAILABLE` rather than substituting current data.

FRED historical runs should use ALFRED/vintage semantics. News should use the time it became available to the system when known. Consensus history must not use a current estimate as if it were the historical estimate.

## Utility scripts

For the legacy JSON run layout, use [scripts/research_memory.py](../scripts/research_memory.py) for local record creation, outcome attachment, and simple calibration summaries.

For the canonical SQLite memory, use [scripts/decision_memory.py](../scripts/decision_memory.py), backed by [research_memory.py](../research_memory.py):

```powershell
python scripts/decision_memory.py --db runs/decision_memory.sqlite record --decision decision.json
python scripts/decision_memory.py --db runs/decision_memory.sqlite outcome --decision-id <id> --outcome outcome.json
python scripts/decision_memory.py --db runs/decision_memory.sqlite summary --symbol NVDA
```

SQLite records require a symbol, `as_of`, and `evidence_freeze_hash`; outcomes retain realized return, benchmark return, alpha, realized scenario, MAE/MFE, and the original decision JSON. The utility performs no external data acquisition and does not modify MCP services. Never overwrite a frozen decision to repair hindsight; create a new run/version.
