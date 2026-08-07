---
name: stock-eval-system
description: Evidence-backed single-stock research with IBKR-first market/options data, deterministic calculations, SEC/FRED/consensus context, evidence-frozen adversarial review, scenario/risk synthesis, and structured decision calibration. Use for deep research, valuation/technical/options risk analysis, catalyst review, conditional timing, and research-ready position boundaries. Never place orders.
---

# Stock Evaluation System

Use this skill for rigorous single-stock research. The system is **research-only**: it may calculate risk budgets and conditional action boundaries, but it must never call IBKR order APIs or mechanically map a score to BUY/HOLD/SELL.

## Non-negotiable evidence rules

Every material statement must be visibly classifiable as one of:

- `FACT`: directly reported/observed primary or trusted-source evidence.
- `DATA_RESULT`: deterministic calculation from named inputs.
- `MODEL_OUTPUT`: formula/model/scenario/sizing output.
- `INFERENCE`: interpretation linking evidence to a thesis.
- `ASSUMPTION`: explicit unobserved input such as a scenario probability.
- `UNVERIFIED`: missing, stale, conflicting, or entitlement-limited information.

Preserve the reasoning chain:

`FACT -> DATA_RESULT -> MODEL_OUTPUT -> INFERENCE -> ACTION CONDITION`

Never average conflicting facts to make the conflict disappear. Never treat missing option fields as zero. Option volume/OI are activity distributions, not buy/sell/open/close direction. FINRA daily short-sale volume is a flow proxy, not short interest. Oversold/overbought is a state, not an action.

Read `references/reasoning-framework.md` for the full reusable logic and `references/evidence-policy.md` for source/confidence rules.

## Provider roles

### Market, intraday, options, liquidity — IBKR first

Use the user's existing read-only IBKR/TWS MCP or IBKR data adapter for price/bars/options. **Do not modify or vendor the MCP into this repository.** Preserve provider timestamps, market-data type, entitlement failures, quote quality, and session information.

For option evidence read:

- `references/options-volatility.md`
- `references/options-multi-source.md`
- `references/tws-pro-options.md`
- `references/ibkr-history-limits.md`

Massive/yfinance may be used only as explicit cross-check/fallback evidence when useful; label provider and timestamp.

### Primary company evidence — SEC + issuer IR

Use `scripts/fetch_sec_research.py` for ticker/CIK resolution, submissions, recent 10-K/10-Q/8-K/ownership filings, XBRL company facts, and Form 4 parsing. Set a descriptive `SEC_USER_AGENT`; no API key is required.

Use issuer IR for guidance, non-GAAP reconciliations, KPI tables, presentations, shareholder letters, and prepared remarks. Prefer an 8-K exhibit when the same document is filed with SEC.

### Macro — FRED/ALFRED

Use `scripts/fetch_fred_macro.py`. Set `FRED_API_KEY`. For historical research pass `--as-of`; the adapter sets the FRED real-time period to the cutoff so later revisions are excluded.

### News — existing IBKR MCP

Use the existing MCP's news-provider/articles/article tools. Normalize the returned JSON with `scripts/normalize_ibkr_news.py`. A headline is not proof of the headline's interpretation; retrieve article text or primary filing/IR evidence for a material claim.

### Expectations — Alpha Vantage

Use `scripts/fetch_alpha_vantage_research.py` for earnings estimates, calendar, and optional transcript. Set `ALPHA_VANTAGE_API_KEY`. Consensus is `street_estimate`/market expectation, not company fact. A current response is not automatically PIT-safe for historical replay.

### Optional context — FINRA / Polymarket

- `scripts/fetch_finra_short_volume.py`: regulatory short-sale **flow** proxy.
- `scripts/fetch_polymarket_context.py`: optional event-market implied expectation when the resolution question directly maps to a material catalyst.

See `references/provider-setup.md` for setup and source-of-truth hierarchy.

## Standard workflow

### 1. Define scope and cutoff

Record symbol, `as_of`, primary horizon, requested modules, portfolio/risk inputs if supplied, and whether the task is current research or historical replay.

### 2. Acquire raw packets

Fetch data without interpretation. Keep raw packets and acquisition metadata. For historical replay, reject any material source whose `available_at` cannot be proven to be at or before the cutoff.

### 3. Deterministic market/options calculation

The public engine is `stock_eval_engine.py`, split internally into:

- `stock_eval_core.py`: OHLCV normalization, technical indicators, option normalization/IV/term structure.
- `stock_eval_kelly.py`: fixed-rule backtest and Kelly diagnostics.
- `stock_eval_position.py`: risk-budget sizing and P/L ladder.

CLI compatibility wrapper:

```bash
python scripts/stock_eval_engine.py --symbol NVDA --data bars.json \
  --options-front front.json --options-back back.json --as-of 2026-08-07 --out calc.json
```

Do not call the daily close-weighted volume histogram a true intraday volume profile. Do not let model-only/last-trade option IV masquerade as executable quote IV.

### 4. Build catalyst/macro/expectation context

Use `references/catalyst-context.md`. Focus on **what changed**, scheduled events, causal macro transmission, and guidance-vs-consensus-vs-model gaps rather than generic news summaries.

### 5. Freeze evidence

Convert source packets into one immutable evidence packet:

```bash
python scripts/build_evidence_packet.py --symbol NVDA --as-of 2026-08-07 \
  --source sec.json --source macro.json --source news.json --source consensus.json \
  --output evidence.json
```

Use `--pit-strict` only when every included source has defensible availability timing.

### 6. Build the claim graph

Create `schemas/claim-graph.schema.json` compatible output. Each claim must contain a stable `claim_id`, label, horizon, direction, frozen `evidence_refs`, counterevidence, and invalidation where applicable. Do not cite a source outside the freeze.

### 7. Run evidence-frozen adversarial review

Read `references/adversarial-review.md`.

Run three logically separate reviews on the **same** frozen evidence:

- Bull: strongest evidence-supported upside interpretation.
- Bear: strongest non-generic attack on thesis weak links.
- Skeptic: evidence/methodology/PIT/horizon/double-counting attack.

Reviewers must not independently browse. If evidence is missing, emit an `evidence_request` instead of introducing a new fact.

### 8. Research Arbiter

The Arbiter adds no new facts. It consumes evidence + claim graph + reviews and may retain/strengthen/weaken/reject/reframe claims. Scenario probabilities are explicit `ASSUMPTION`s and must sum to 1 when numeric.

Allowed research states:

- `READY_CONDITIONAL`
- `WAIT_CONFIRMATION`
- `NEEDS_EVIDENCE`
- `RISK_BLOCKED`
- `THESIS_INVALIDATED`
- `MONITOR_ONLY`
- `RESEARCH_READY`

Validate cross-artifact integrity:

```bash
python scripts/validate_research_artifacts.py \
  --evidence evidence.json --claims claims.json \
  --review bull.json --review bear.json --review skeptic.json \
  --arbitration arbitration.json
```

### 9. Risk and timing

Read `references/risk-positioning.md`, `references/tactical-timing.md`, and `references/position-timing-report.md`.

Kelly is diagnostic unless qualified by the declared OOS governance. Options may haircut risk for IV/event conditions but may not create directional edge or real-world probability. A missing stop must not be invented. Keep short-horizon opening-range/VWAP logic separate from long-horizon thesis stops.

### 10. Report

Use `assets/report-template.md`. The final note must include source register, evidence limitations, claim/counterevidence, Bull/Bear/Skeptic findings, Arbiter changes, at least four scenarios, triggers/invalidation, and conditional action boundaries.

### 11. Decision memory and calibration

After a completed research decision, store a structured decision record and later settle comparable outcomes:

```bash
python scripts/decision_memory.py --db runs/decision_memory.sqlite record --decision decision.json
python scripts/decision_memory.py --db runs/decision_memory.sqlite outcome --decision-id <id> --outcome outcome.json
python scripts/decision_memory.py --db runs/decision_memory.sqlite summary --symbol NVDA
```

Read `references/decision-memory.md`. Quantitative calibration (multiclass Brier, realized return/alpha, scenario frequency) comes before any narrative reflection. Never let an LLM overwrite the immutable historical decision record.

## Quality gates

Before finalizing a research note verify:

1. current vs historical/PIT mode is explicit;
2. provider/timestamp and material source conflicts are visible;
3. primary reported numbers trace to SEC/IR where available;
4. consensus/model/company guidance remain separate concepts;
5. option direction is not inferred from volume/OI alone;
6. at least one non-catastrophic counter-path challenges a positive thesis;
7. probabilities are assumptions and sum correctly when numeric;
8. reviewers cite only frozen evidence;
9. short- and long-horizon triggers/stops are not mixed;
10. diagnostic Kelly is separated from applied Kelly;
11. the final state is conditional/research-oriented rather than an autonomous trade command.
