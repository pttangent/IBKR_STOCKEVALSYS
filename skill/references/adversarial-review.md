# Evidence-frozen adversarial review

This is the distilled research-debate layer. It borrows the useful separation of bullish/bearish review from multi-agent research systems but removes autonomous browsing, free-form voting, and order execution.

## Preconditions

Adversarial review starts only after:

1. data acquisition and deterministic calculations are complete;
2. `build_evidence_packet.py` has frozen the source packets and produced `evidence_freeze_hash`;
3. the initial claim graph references only source IDs inside that packet.

All reviewers receive the **same** evidence packet and claim graph. They may not browse, call providers, calculate new undocumented metrics, or introduce an uncited fact. If a missing fact is material, emit `evidence_requests` and stop that line of argument.

## Bull reviewer

Goal: construct the strongest evidence-supported upside interpretation without cheerleading.

For each material claim, ask:
- Is positive evidence underweighted?
- Is the base case ignoring convexity, operating leverage, revision momentum, or a catalyst that is actually in the frozen evidence?
- Is the market-expectation bar lower than the initial thesis assumes?
- What observable evidence would strengthen the bull path?

Output `review.schema.json` with `role=bull`. A positive finding must cite frozen evidence. Bull review may strengthen or reframe a claim; it cannot invent a catalyst.

## Bear reviewer

Goal: attack the weakest links of the thesis, not merely list generic risks.

Check:
- alternative explanations for apparent improvement;
- balance-sheet or cash-flow fragility;
- valuation dependence on optimistic forecasts/multiples;
- cyclical/regime sensitivity;
- technical confirmation that is horizon-mismatched;
- event asymmetry and option-implied risk;
- concentration/customer/regulatory risks;
- claims that fail under a non-catastrophic bear path.

Output `review.schema.json` with `role=bear`.

## Skeptic reviewer

Goal: attack epistemology and methodology rather than direction.

Mandatory checks:
- FACT vs estimate vs model output confusion;
- post-cutoff or revision leakage in historical research;
- stale/conflicting provider values;
- option volume/OI interpreted as buy/sell/open/close direction;
- FINRA short-sale volume called short interest;
- oversold/overbought converted directly to action;
- low multiple converted directly to undervaluation;
- correlation described as causation;
- overlapping signals double-counted in a score;
- backtest sample/OOS/cost assumptions overstated;
- horizon mismatch among evidence, scenario, and stop/target;
- scenario probability presented as empirical fact.

Output `review.schema.json` with `role=skeptic`.

## Research Arbiter

The Arbiter is not another analyst and does not add facts. It consumes:

`evidence packet + claim graph + bull review + bear review + skeptic review`

It must:
1. retain/strengthen/weaken/reject/reframe each disputed claim;
2. explain every material change with frozen evidence IDs;
3. update scenario probabilities only as `ASSUMPTION` and make numeric probabilities sum to 1;
4. surface unresolved evidence requests;
5. output a research state rather than BUY/HOLD/SELL.

Allowed states:
- `READY_CONDITIONAL`
- `WAIT_CONFIRMATION`
- `NEEDS_EVIDENCE`
- `RISK_BLOCKED`
- `THESIS_INVALIDATED`
- `MONITOR_ONLY`
- `RESEARCH_READY`

The Arbiter must not resolve a genuine provider conflict by averaging values. Preserve source-specific values or move the claim to `UNVERIFIED`.

## Validation

Before final reporting run:

```bash
python scripts/validate_research_artifacts.py \
  --evidence evidence.json \
  --claims claims.json \
  --review bull.json --review bear.json --review skeptic.json \
  --arbitration arbitration.json
```

Add `--pit-strict` only when every source has a defensible `available_at <= as_of`. A current consensus/prediction-market packet should fail strict historical replay until it has been snapshotted or otherwise timestamp-qualified.
