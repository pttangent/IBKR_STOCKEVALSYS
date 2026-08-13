# Report quality, structured output, and evidence-chain packaging

This reference governs reader-facing reports after deterministic calculations are complete. It is distilled from audits of real report/evidence bundles. Use it together with [report-interpretation-knowledge.md](report-interpretation-knowledge.md): this file defines the output contract, while the interpretation reference teaches how to reason about accounting bridges, financing/EV, setup-specific Kelly, binding risk caps, cross-source disagreement, acquisition failures, IV/Gamma quality, and PIT chronology.

The interpretation reference is **knowledge, not a ticker-specific rulebook**. Apply those lenses when economically material and explain why they matter in the current case.

## 1. Canonical report architecture

The reader-facing semantic source of truth is `structured_report.json`.

```text
raw/provider evidence
  -> normalized evidence + deterministic artifacts
  -> evidence freeze / claim graph / reviews / arbitration
  -> structured research synthesis
  -> structured_report.json        # canonical reader-facing semantics
       -> Markdown renderer         # terminal format
       -> HTML renderer             # rich reader format
       -> validator
  -> evidence-chain package manifest + checksums
  -> <run_id>_evidence_chain_report_package.zip
```

**Do not use Markdown as an input to the HTML renderer.** Markdown and HTML are sibling outputs from the same structured JSON. A legacy Markdown report may be migrated once into structured content, but future semantics must be edited in JSON/structured synthesis rather than inferred from headings or prose.

`report_manifest.json` may remain as a light module/index/acquisition artifact for backward compatibility. It is not the canonical narrative source once `structured_report.json` exists.

Relevant files:

- `schemas/structured-report.schema.json`
- `scripts/build_structured_report.py`
- `scripts/validate_structured_report.py`
- `scripts/render_markdown_report.py`
- `scripts/render_html_report.py`
- `scripts/build_evidence_chain_package.py`

## 2. Structured report content contract

Every full report should contain:

- exact `run_id`, `symbol`, `as_of`, `evidence_cutoff`, and `price_timestamp`;
- canonical `research_state`;
- executive summary / thesis / variant perception / primary horizon;
- module status, confidence, freshness, evidence IDs and source artifacts;
- deterministic metrics or references to the artifacts that contain them;
- reader-facing blocks;
- explicit key judgments with `why`, confidence, evidence IDs and invalidation when useful;
- **knowledge notes** that teach important concepts only when relevant to the current decision;
- chart specs whose data come from structured artifacts;
- missing fields and limitations.

Use the `judgments` field for conclusions and the `knowledge_notes` field for transferable explanations. Do not hide analytical logic only inside free-form prose.

## 3. Chart interpretation contract

A chart is incomplete if the reader has to guess why it exists. Every chart must carry four explanations in `structured_report.json`:

- `WHAT`: what data/relationship is being plotted;
- `READ`: what the current evidence says and how to read the shape/levels;
- `WHY`: why the chart matters to the thesis, timing, valuation, options or risk decision;
- `LIMIT`: what the chart cannot prove and which data-quality caveats remain.

The HTML renderer shows this explanation immediately below each figure. Markdown renders the same four fields as text. This prevents a visual from becoming an unexplained dashboard decoration.

When a concept is central to a judgment, add a nearby `knowledge_note`, for example:

- GAAP-to-operating bridge;
- Foundry/segment economics;
- EV versus dilution mechanics;
- total variance versus raw IV;
- gross Gamma versus signed dealer GEX;
- setup-specific Kelly;
- binding position constraints;
- relative-strength/residual interpretation;
- PIT/source-quality distinctions.

## 4. HTML design language

The rich report should follow the terminal design language supplied by the project owner rather than a rounded-card dashboard aesthetic:

- near-black background (`~4%` lightness) and high-contrast foreground;
- thin neutral-gray borders;
- zero/near-zero border radius;
- monospace-first typography (`Space Mono` / `JetBrains Mono` style fallback);
- uppercase English labels with concise Chinese explanations where useful;
- 12-column terminal/grid composition;
- green/red/amber reserved for semantic state, not decoration;
- no gradients, glassmorphism or oversized rounded cards;
- data density may be high, but section hierarchy must remain obvious.

Normal generated HTML embeds Plotly and is standalone/offline. Versioned repository examples may use a CDN build to avoid duplicating several megabytes of Plotly in Git history.

## 5. Correctness and freshness principles

A report can be visually polished and still be wrong. Preserve these principles:

### 5.1 Freshness coherence

Do not combine post-event market data with pre-event fundamental/valuation conclusions without explicitly marking the mismatch. Record latest material event, latest primary evidence and price timestamp. If an important module is stale, downgrade the relevant judgment or request new evidence.

### 5.2 Primary-source priority

When issuer/SEC primary evidence exists for a material reported number, prefer it over a secondary article. Secondary reporting may add context but should not be the only evidence for a directly available company/filing fact.

### 5.3 Missing is not zero

Missing OI, volume, bid/ask, Greeks, valuation inputs, bars/counts or revisions remain `null/not_observed`. If an aggregate is partial, expose coverage. Do not make a missing field look like an economically meaningful zero.

### 5.4 Timing language follows timing evidence

If the package has only previous completed-session evidence, describe a `next-session setup` or `daily-structure scenario`. Use labels such as `today confirmed`, VWAP, ORH/ORL or microstructure confirmation only when the relevant same-session evidence exists.

### 5.5 Options evidence strength

A few historical call/put closes across two expiries are a straddle/variance proxy, not a full volatility surface. Gross OI-weighted Gamma is not signed dealer GEX. Missing/untrusted OI must suppress Gamma-wall ranking; unreliable IV should downgrade Gamma rather than be accepted just because it is numerically positive.

For the reasoning behind these principles, read [report-interpretation-knowledge.md](report-interpretation-knowledge.md) rather than turning them into blind numeric thresholds.

## 6. Evidence-chain ZIP is the normal report deliverable

A completed report run should end with one portable ZIP, the same artifact type used for external audit/review:

`<run_id>_evidence_chain_report_package.zip`

Use:

```powershell
python scripts/build_evidence_chain_package.py `
  --run-dir outputs/INTC_2026-08-12 `
  --structured-report structured_report.json
```

The packager:

1. validates `structured_report.json`;
2. renders Markdown from structured JSON;
3. renders HTML from the same structured JSON and deterministic artifacts;
4. writes `evidence_chain_manifest.json` with path/size/SHA256;
5. writes `SHA256SUMS.txt`;
6. compresses the report, evidence and supporting artifacts into one ZIP.

Do not package unrelated historical ZIPs or temporary/lock files inside the report ZIP.

## 7. Replay-complete package target

A full-research package should be portable enough to audit without re-browsing. Include when applicable:

- `structured_report.json`;
- evidence packet and evidence freeze metadata;
- raw or frozen SEC/IR primary-source packets used for material claims;
- market and intraday packets;
- options source packets, reconciliation, feature and Gamma artifacts;
- valuation snapshot and deterministic model outputs;
- Claim Graph;
- Bull/Bear/Skeptic review objects;
- arbitration object;
- decision record;
- Markdown and HTML reader outputs;
- `evidence_chain_manifest.json` and `SHA256SUMS.txt`.

A URL in prose is navigation, not a replacement for a frozen primary-source artifact when replay completeness matters.

Before any field is shown as `MISSING`, run the relevant primary/alternative source route and write an `evidence_resolution` record containing the exact field, status (`FOUND`, `NOT_AVAILABLE_AT_CUTOFF`, `ERROR`, or `NOT_AUDITED`), attempts, source documents, retrieval/cutoff time, and next action. A field with status `FOUND` must be removed from `missing_fields`. `NOT_AVAILABLE_AT_CUTOFF` means the route was queried and no qualifying document existed by the stated cutoff; it does not mean the document can never be found.

## 8. Modular output

`structured_report.json` can contain all modules while a renderer selects a subset. A narrow request does not need to rebuild the entire research workflow if the requested conclusion is independent.

Examples:

```powershell
python scripts/render_html_report.py --structured-report structured_report.json --run-dir runs/NVDA --output report.html
python scripts/render_html_report.py --structured-report structured_report.json --run-dir runs/NVDA --output options.html --modules options
python scripts/render_markdown_report.py --structured-report structured_report.json --output tactical.md --modules technical,options,risk
```

A module-only HTML is still a complete document: title, status, evidence limitations, charts, chart explanations and knowledge notes must remain visible.

## 9. Structured synthesis workflow for the agent

After evidence freeze and deterministic calculation, the research agent should synthesize into structured fields rather than drafting Markdown first. `build_structured_report.py` can merge a `research_content.json` synthesis object with deterministic artifacts and legacy module metadata.

The synthesis step should answer:

- What is observed?
- What is the judgment?
- Why does it matter economically?
- What is the confidence and evidence basis?
- What would invalidate it?
- Which transferable concept should be explained to the reader?
- Which chart best supports the judgment, and what are its WHAT/READ/WHY/LIMIT notes?

Only after this step should Markdown/HTML be rendered.

## 10. Validation philosophy

Validation should fail closed on structural/reporting contradictions that make rendering unsafe (invalid state enum, malformed structured report, missing chart interpretation fields). Analytical knowledge should not be encoded as simplistic hard thresholds when the correct interpretation depends on context. Use knowledge references to guide reasoning, and reserve validators for true schema/governance invariants.
