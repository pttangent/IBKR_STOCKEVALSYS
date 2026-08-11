# Report quality, freshness, and modular HTML output

This reference governs reader-facing reports after deterministic calculations are complete. It was distilled from audits of real report/evidence bundles: a strong research method is not enough if the rendered report mixes stale fundamentals with fresh prices, hides missing fields as zero, or overstates the evidence level of an options/timing module.

## 1. Report correctness gates

A report is publishable only when all material modules pass these gates. If a gate fails, keep the module visible but downgrade it to `UNVERIFIED`, `NEEDS_EVIDENCE`, or `RISK_BLOCKED`; do not silently omit the failure.

### 1.1 Freshness barrier

For every module record:

- `module_as_of`
- `latest_material_event_at`
- `latest_primary_evidence_at`
- `price_as_of`
- `freshness_status`

If a material event (earnings, guidance, financing, merger, regulatory decision, major product/capacity update) occurred after the newest evidence used by a module but before the price/reference timestamp, the module is stale. Do not combine post-event price/options data with pre-event fundamental/valuation conclusions as if they were one coherent snapshot.

Required behavior:

- mark `freshness_status=stale_after_material_event`;
- suppress confident thesis/valuation/risk conclusions that depend on the stale module;
- emit an evidence request for the missing post-event primary source;
- create a new run after refresh rather than editing the frozen old run.

### 1.2 Primary-source priority

When a company/SEC primary source exists for the period being analyzed, use it before a secondary news summary. Secondary sources may add interpretation or context, but must not be the only evidence for a number that is directly available from the issuer/SEC.

### 1.3 Missing is not zero

A missing field is `null` / `not_observed`, never numeric zero unless the source explicitly reported zero. This applies especially to:

- option open interest;
- option volume;
- bid/ask;
- Greeks;
- valuation inputs;
- short-horizon bars/counts;
- consensus revisions.

Any aggregate must report observed-row count, missing-row count, and coverage. If coverage is insufficient, aggregate output is `null` or explicitly partial.

### 1.4 Research-state enum

Reader-facing state must use the canonical governance enum exactly:

`RESEARCH_READY`, `READY_CONDITIONAL`, `WAIT_CONFIRMATION`, `NEEDS_EVIDENCE`, `RISK_BLOCKED`, `MONITOR_ONLY`, `THESIS_INVALIDATED`.

Do not invent near-synonyms such as `READY CONDITIONAL`, `WATCHLIST INITIATION`, or prose states that cannot be validated.

## 2. Timing and technical labeling

### 2.1 Intraday evidence gate

Do not label a block `today timing`, `opening confirmation`, `VWAP setup`, `ORH/ORL`, or similar unless the run contains same-session intraday evidence adequate for that claim.

If only prior-close/daily/ATR evidence is present, label it `next-session setup` or `daily-structure scenario`.

### 2.2 Multi-horizon trend state

Do not collapse short-, medium-, and long-horizon trend into one bullish/bearish label when they conflict. Prefer:

- `short_trend_state`
- `medium_trend_state`
- `long_trend_state`
- `trend_conflict`

A stock below short EMAs with bearish short momentum but above a rising long SMA is a horizon conflict, not one-dimensional bullishness.

## 3. Options and Gamma terminology

### 3.1 Evidence-strength naming

One call/put pair at two expiries from historical closes is a `two-expiry ATM straddle/variance proxy`, not a full volatility surface or robust term structure.

Use stronger terms only when the required surface/quote coverage exists.

### 3.2 OI/Gamma gate

Gamma concentration is publishable only when open interest is actually observed with adequate coverage and at least one economically meaningful positive OI/Gamma row exists.

If OI is missing, all zero/untrusted, or coverage is below the declared threshold:

- `gamma_status=UNAVAILABLE_ZERO_OR_UNTRUSTED_OI` (or an equivalent explicit unavailable status);
- do not rank upper/lower Gamma walls;
- do not draw a Gamma wall chart;
- do not convert an arbitrary all-zero strike into a concentration level.

Unsigned OI-weighted Gamma is `gross gamma structure`, never `dealer GEX`. Signed/dealer Gamma requires an explicitly labeled position-sign assumption or flow inference.

### 3.3 Activity is not direction

Option volume/OI are activity distributions. They do not identify buyer/seller, opening/closing, customer/dealer side, or forced hedging flow.

## 4. Kelly and sizing labels

Display each quantity under its exact meaning. Never call a quarter/fractional Kelly number “full-sample Kelly”. At minimum separate:

- `p`
- `b`
- `f_raw_formula`
- `empirical_full_sample_kelly` when actually computed
- `full_kelly`
- `half_kelly`
- `quarter_kelly`
- `option_event_haircut`
- `diagnostic_fractional_kelly_cap`
- `applied_fractional_kelly`
- `qualification_status`

A diagnostic can be shown with insufficient OOS; it must not be described as validated/applied.

## 5. Replay-complete evidence bundle

A `full-research` run should be portable enough to audit without re-browsing. Bundle the raw/normalized artifacts used for material conclusions, including when applicable:

- market and intraday packets;
- SEC/IR primary evidence packets;
- macro and consensus packets;
- options source packets and reconciliation output;
- valuation input snapshot;
- deterministic module outputs;
- Evidence Packet / freeze hash;
- Claim Graph;
- Bull/Bear/Skeptic review objects;
- arbitration object;
- decision record.

URLs in Markdown are not a substitute for the frozen source packet.

## 6. Modular report manifest

Prefer a machine-readable `report_manifest.json` as the common input to all reader-facing renderers. Markdown and HTML should be sibling outputs, not an HTML parser scraping semantic data out of prose.

Each module should declare:

- module name;
- status and confidence;
- `as_of` / evidence cutoff;
- source artifact paths / evidence IDs;
- freshness status;
- missing fields;
- deterministic metrics;
- optional narrative Markdown;
- visualization specs or artifact references.

See `schemas/report-manifest.schema.json` and `assets/report-manifest-template.json`.

## 7. HTML output contract

HTML is the default rich reader-facing representation when a report is generated. A full report and a module-only report use the same renderer.

Supported modules:

`overview`, `fundamentals`, `valuation`, `technical`, `options`, `governance`, `risk`, `scenarios`, `evidence`.

Examples:

```powershell
python skill/scripts/render_html_report.py --report report.md --run-dir runs/NVDA --output report.html
python skill/scripts/render_html_report.py --report report.md --run-dir runs/NVDA --output options.html --modules options
python skill/scripts/render_html_report.py --report report.md --run-dir runs/NVDA --output tactical.html --modules technical,options,risk
```

Renderer rules:

1. Plot from deterministic JSON/raw artifacts when available; do not scrape numerical values out of narrative if a structured source exists.
2. Missing/untrusted data suppress the corresponding visualization instead of producing a deceptive zero chart.
3. Every chart states evidence type and as-of context in nearby text/tooltips.
4. Module-only HTML remains a complete standalone document with title, evidence status, limitations, and source narrative for that module.
5. The HTML renderer must never upgrade evidence strength. Visualization is presentation, not new analysis.
6. Keep Markdown/JSON outputs as audit/support artifacts even when HTML is the primary reading surface.

## 8. Recommended pipeline

```text
acquisition
  -> raw source packets
  -> normalization / deterministic calculations
  -> evidence freeze + claim graph
  -> report_manifest.json
       -> Markdown renderer
       -> HTML renderer (full or selected modules)
       -> machine audit/validation
```

A narrow request may stop after only the required modules are acquired/calculated, then produce a module-only manifest and HTML. It does not need to run the entire full-research workflow unless the requested conclusion depends on it.
