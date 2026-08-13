---
name: stock-eval-system
description: Evidence-backed single-stock research with IBKR-first market/options data, deterministic calculations, SEC/FRED/consensus context, evidence-frozen adversarial review, scenario/risk synthesis, structured decision calibration, and modular HTML reporting. Use for deep research, valuation/technical/options risk analysis, catalyst review, conditional timing, and research-ready position boundaries. Never place orders or provide personalized financial advice.
---

# Stock Evaluation System

Use this skill as a router plus reproducible calculation layer. Produce a research posture, not a magic score or an automatic buy/sell label. Preserve the chain `FACT -> DATA_RESULT -> MODEL_OUTPUT -> INFERENCE -> ACTION CONDITION`; do not let missing fields silently become zero. For the distilled reasoning chain and reusable multi-scenario examples, read [references/reasoning-framework.md](references/reasoning-framework.md). For full underwriting, also read [references/distilled-research-governance.md](references/distilled-research-governance.md), [references/adversarial-review.md](references/adversarial-review.md), [references/catalyst-context.md](references/catalyst-context.md), [references/provider-setup.md](references/provider-setup.md), [references/decision-memory.md](references/decision-memory.md), and [references/report-quality-and-html.md](references/report-quality-and-html.md).

## Operating contract

1. State `as_of`, evidence cutoff, price timestamp, filing cutoff, source/provider, live/delayed status, and missing fields before interpreting results.
2. Prefer user files and local IBKR/TWS first; use Massive REST for historical OHLC and contract reference; use public primary sources for filings/IR; use reputable web sources only for clearly labeled secondary facts.
3. Keep facts/company claims/Street estimates, computed metrics, model outputs, assumptions, and analyst interpretation separate. Every material number must be traceable to an input or formula.
4. Freeze the evidence set before Bull/Bear/Skeptic review. Use the canonical Evidence Packet and SHA256 `evidence_freeze_hash`; convert material conclusions into a Claim Graph with frozen evidence references, counterevidence, confidence, and invalidation conditions.
5. Choose modules from the request: `quick-check`, `fundamental-deep-dive`, `valuation`, `technical-setup`, `options-implied-risk`, `position-plan`, `full-research`, or `backtest-validation`. Do not run every module by default.
6. Never fabricate missing data. Downgrade confidence and list the exact evidence needed to upgrade it.
7. For `full-research`, run constrained Bull/Bear/Skeptic reviews and a Research Arbiter against the frozen evidence/Claim Graph; reviewers may emit `evidence_request` but may not browse or add uncited facts after freeze. Output a research state, not BUY/HOLD/SELL.
8. Do not place orders. The IBKR adapter must use readonly connections and must not call order APIs.
9. For every reader-facing report, apply [references/report-quality-and-html.md](references/report-quality-and-html.md): enforce the freshness barrier, primary-source priority, missing-not-zero semantics, canonical research-state/Kelly labels, the intraday evidence gate, and the OI/Gamma availability gate before rendering.
10. Every report-producing workflow must support modular HTML. Full research produces a full HTML report; a narrow module request may produce only the requested module(s) as a standalone HTML document. Markdown and JSON remain audit/support artifacts and must not be discarded.
11. Before publishing `missing_fields`, run [scripts/resolve_evidence_requirements.py](scripts/resolve_evidence_requirements.py) or the applicable provider-specific route. Distinguish `FOUND` from `NOT_AVAILABLE_AT_CUTOFF`, preserve attempts and source documents, and never call a source-backed field missing merely because it has not yet been copied into the run directory.

## Data routing

Read [references/providers.md](references/providers.md) before connecting to a provider. Use [scripts/fetch_market_data.py](scripts/fetch_market_data.py) for one-shot acquisition, [scripts/fetch_ibkr_daily_full.py](scripts/fetch_ibkr_daily_full.py) for paged daily history, [scripts/fetch_ibkr_intraday.py](scripts/fetch_ibkr_intraday.py) for recent short-bar paging, and [scripts/fetch_intraday_resilient.py](scripts/fetch_intraday_resilient.py) for IBKR-first retry/chunk/fallback acquisition. For options evidence, use the project-local IBKR MCP sequence documented in [references/tws-pro-options.md](references/tws-pro-options.md); normalize its response with [scripts/normalize_twspro_option_chain.py](scripts/normalize_twspro_option_chain.py). **If the account lacks live/OPRA option permission, do not call `scripts/fetch_ibkr_options.py`: that script is the separate direct `reqMktData`/quote/Greeks path and its 354 errors are entitlement diagnostics, not proof that historical option bars are unavailable.** Use [scripts/fetch_ibkr_options.py](scripts/fetch_ibkr_options.py) only when live option permission is explicitly confirmed. Use [scripts/fetch_massive_intraday.py](scripts/fetch_massive_intraday.py) and [scripts/fetch_massive_options.py](scripts/fetch_massive_options.py) for Massive historical complements, and [scripts/fetch_yfinance_options.py](scripts/fetch_yfinance_options.py) for an independent research chain view. Run [scripts/reconcile_option_sources.py](scripts/reconcile_option_sources.py) before interpreting cross-source option differences, then use [scripts/options_chain_features.py](scripts/options_chain_features.py) and [scripts/validate_inputs.py](scripts/validate_inputs.py) before calculation.

- IBKR/TWS: the project-local MCP is the stable IBKR acquisition layer for stock bars and recent historical option bars. The skill decides when to call it and how to interpret it.
- Massive REST: historical contract reference and option/underlying EOD bars; use as a complementary history source, not an assumed live snapshot.
- yfinance: independent research chain/stock view; use for cross-checks and missing fields, but label its unofficial provenance.
- Alpaca: use as a complementary market/event layer. Current paper account supports IEX stock snapshot/trade/quote/bars, assets, news, corporate actions, option contracts, and indicative option snapshots. Do not treat Basic indicative options as OPRA evidence; in the validated account SIP stock, OPRA options, and historical option bars returned 403, and sampled indicative snapshots had no IV/Greeks. Never use Alpaca as an accounting-fundamentals source.
- Fundamental reconciliation: SEC/IR remains primary; `fetch_finnhub_research.py` and `fetch_ibkr_fundamentals.py` are secondary packets, while `reconcile_fundamentals.py` enforces same-period and same-filing gates.
- Web/filings: preferred for company facts, guidance, catalysts, and disclosures; retain URLs and retrieval timestamps.

For news and catalysts, read [references/news-capability.md](references/news-capability.md). Use the project-local IBKR MCP sequence `ibkr_get_news_providers` → qualified historical headlines → selected `ibkr_get_news_article` bodies. Historical news is a separate capability from live quotes and OPRA options. Never interpret an empty headline response until provider availability, contract qualification, time window, and errors have been audited. Preserve provider code, timestamp, articleId, body availability, retrieval time, and the distinction between company facts, analyst views, and media commentary.

For filings, macro, consensus, event probabilities, short-sale proxies, and retail-attention context, read [references/external-sources.md](references/external-sources.md) and [references/fundamental-sources.md](references/fundamental-sources.md), and, for event delta analysis, [references/catalyst-context.md](references/catalyst-context.md). Use the bundled read-only smoke test when onboarding or auditing credentials; route each source by role and evidence grade instead of counting the number of responding APIs. SEC/IR are primary facts; IBKR Reuters Fundamentals, Finnhub reported financials/metrics, and SimFin statements are secondary fundamental cross-checks. Run `fetch_sec_research.py`, `fetch_finnhub_research.py --modules financials_reported,metric`, `fetch_ibkr_fundamentals.py`, and `fetch_simfin_research.py --modules general,statements,shares` sequentially when available, then `reconcile_fundamentals.py`; never merge incompatible filing periods.

For the research layer, use the bundled adapters and preserve their labels: `FACT` for reported facts, `street_estimate` for consensus, `MARKET_IMPLIED_EXPECTATION` for event markets, and `SHORT_SALE_FLOW_PROXY` for FINRA Reg SHO. Do not call a source merely because it exists; each source must answer a specific claim, catalyst, expectation, or crowding question. Keep raw packets separate from normalized evidence and record provider status, endpoint, retrieval time, publication/observation/vintage time, and errors.

### Official API documentation map

The agent must consult these links when a provider behavior, field, endpoint, entitlement, or retention limit is uncertain:

- IBKR: [TWS API docs](https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/), [requesting market data](https://www.interactivebrokers.com/docs/tws-api/doc/quick-start/requesting-market-data), [market-data subscriptions](https://www.interactivebrokers.com/campus/ibkr-api-page/market-data-subscriptions/).
- IBKR news: [TWS API News](https://interactivebrokers.github.io/tws-api/news.html).
- Massive: [Options REST overview](https://massive.com/docs/rest/options/overview), [all option contracts](https://massive.com/docs/rest/options/contracts/all-contracts), [custom option bars](https://massive.com/docs/rest/options/aggregates/custom-bars), [option snapshot](https://massive.com/docs/rest/options/snapshots/option-contract-snapshot), [pricing/plan matrix](https://massive.com/pricing?product=options).
- yfinance: [Ticker API](https://ranaroussi.github.io/yfinance/reference/api/yfinance.Ticker.html), [`Ticker.option_chain`](https://ranaroussi.github.io/yfinance/reference/api/yfinance.Ticker.html), [`download`](https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html), [research-use disclaimer](https://ranaroussi.github.io/yfinance/index.html).
- Alpaca: [getting started](https://docs.alpaca.markets/us/docs/getting-started), [market data](https://docs.alpaca.markets/us/docs/about-market-data-api), [stock snapshot](https://docs.alpaca.markets/us/reference/stocksnapshotsingle), [option chain](https://docs.alpaca.markets/us/v1.4.2/reference/optionchain), [historical option bars](https://docs.alpaca.markets/us/v1.4.2/reference/optionbars), [news](https://docs.alpaca.markets/us/v1.1/reference/news-3), [corporate actions](https://docs.alpaca.markets/us/v1.4.2/reference/corporateactions-1), and [assets](https://docs.alpaca.markets/us/reference/get-v2-assets-1).

For the complete three-source options protocol, read [references/options-multi-source.md](references/options-multi-source.md). Do not invent an endpoint from memory and do not label a source as unavailable until its documented route has been attempted or its entitlement has been checked.

## Evidence-frozen research workflow

For a full research run, use this sequence after raw acquisition:

1. Build one immutable packet from provider packets:

   ```powershell
   python scripts/build_evidence_packet.py --symbol NVDA --as-of 2026-08-07 `
     --source sec.json --source macro.json --source news.json --source consensus.json `
     --output evidence.json
   ```

   Add `--pit-strict` only when every source has defensible `available_at <= as_of`; current consensus, news, and prediction-market snapshots usually fail historical replay until timestamp-qualified.
2. Build a Claim Graph whose `evidence_refs` are source IDs inside that packet. Use [schemas/claim-graph.schema.json](schemas/claim-graph.schema.json) or the template in [assets/claim-graph-template.json](assets/claim-graph-template.json).
3. Run Bull, Bear, and Skeptic reviews on the same packet and graph. They may request missing evidence but must not acquire it or smuggle it into the review.
4. Run the cross-artifact validator:

   ```powershell
   python scripts/validate_research_artifacts.py --evidence evidence.json `
     --claims claims.json --review bull.json --review bear.json --review skeptic.json `
     --arbitration arbitration.json
   ```

The older [scripts/research_governance.py](scripts/research_governance.py) validator remains available for the legacy evidence-manifest/review schema; use the Evidence Packet validator for new runs and do not mix schemas within one run.

### Standard technical-data bundle

When the user asks for the current technical report, use this bundle unless a different horizon is explicitly requested:

1. **Full available daily K**: run `fetch_ibkr_daily_full.py` with `TRADES` and `useRTH=True`. The script asks IBKR for the head timestamp, walks backward in `1 Y` / `1 day` pages, deduplicates by session date, and records every request. "Full history" means the history available to the connected IBKR account for that contract, not an assumed fixed number of years.
2. **30-day 1-minute context**: run `fetch_market_data.py --source ibkr --duration "30 D" --bar-size "1 min" --what-to-show TRADES`. A single request is valid and normally returns the full batch (for a regular US stock, approximately 30 sessions x 390 RTH bars); page only if the server soft-throttles or the user asks for a precise calendar window.
3. **Three recent RTH sessions at 10 seconds**: run `fetch_ibkr_intraday.py --sessions 3 --bar-size "10 secs" --what-to-show TRADES`. The script uses repeated `14400 S` pages, stops after three distinct session dates, deduplicates boundary bars, and discloses page count and coverage. It is deliberately not described as raw ticks.

For the 30-day 1-minute leg, use `fetch_intraday_resilient.py`: it tries the large request once, then immediately falls back to `14 D + 14 D + 4 D` IBKR chunks when the farm soft-throttles or returns an incomplete packet. A one-shot timeout followed by complete IBKR chunks is a **successful IBKR chunked acquisition**, not a provider failure; report both the timeout and the successful chunk coverage. Repeating the timed-out large request is opt-in, not the default. If IBKR remains unavailable, `fetch_massive_intraday.py --rth-only` is the next source; if Massive also fails, `fetch_yfinance_intraday.py` uses five non-overlapping windows of at most seven days. yfinance must be marked as a non-IBKR, no-count fallback, and its empty/partial chunks must be disclosed. Never silently replace an IBKR timeout with an empty series.

For an options-linked technical report, use the three-source protocol in [references/options-multi-source.md](references/options-multi-source.md): (1) project-local IBKR MCP for recent historical option bars, (2) Massive REST for contract reference and matched historical option/underlying bars, and (3) yfinance for an independent chain/stock view. This is a capability-based multi-source design, not a blind fallback ladder. Run [scripts/reconcile_option_sources.py](scripts/reconcile_option_sources.py) before deriving consensus, and preserve source-specific values when the data are complementary or conflicting. The local MCP source first resolves an underlying `conId` for `ibkr_get_option_chain_params`, then calls `ibkr_get_option_chain` once per expiry, normally with `num_strikes=20`; its implementation uses `reqHistoricalDataAsync` with `1 D`/`5 mins` `TRADES` for each option, not live `reqMktData`. A `tws-pro` packet containing only last/high/low/volume/bars is last/aggregate evidence, not a live quote. Run [scripts/normalize_twspro_option_chain.py](scripts/normalize_twspro_option_chain.py), then report both `last_iv_model` and `atm_straddle_approx_iv` only when calculable, with formulas and caveats. A chain with only expiries/strikes is discovery evidence, not quote evidence. A provider-reported IV without a valid quote timestamp is not market-validated IV. Put/call volume and open interest are activity distributions, never directional flow.

The exact IBKR strings matter: short bars use plural forms (`1 secs`, `5 secs`, `10 secs`, `30 secs`), while one-minute bars use `1 min`. Time-qualified cursors should use `YYYYMMDD HH:mm:ss US/Eastern` (or the exchange timezone) to avoid ambiguous-time warnings. Use the project environment first: `stock-eval-system\\.venv\\Scripts\\python.exe`. The project pins MCP to the compatible `1.18.0` line and includes `ib-async` and `yfinance`; if the project environment is unavailable, the WorkBuddy environment `C:\\Users\\pt-desktop\\.workbuddy\\binaries\\python\\envs\\ibkr-pro\\Scripts\\python.exe` is an explicit secondary interpreter. Never silently fall back to a system Python that lacks `ib_async`.

## Calculation routing

Run `python scripts/stock_eval_engine.py --symbol SYM --data bars.json` for technicals/backtest, adding `--options-front` and `--options-back` only when option data passes validation. The public root facade `stock_eval_engine.py` delegates to `stock_eval_core.py`, `stock_eval_kelly.py`, and `stock_eval_position.py`; the `scripts/` wrapper remains the CLI compatibility path. Use the module references only when needed:

- [references/technical.md](references/technical.md): trend, momentum, support/resistance, and volume limitations.
- [references/options-volatility.md](references/options-volatility.md): quote quality, IV inversion, skew, activity distribution, and variance term structure.
- [references/risk-positioning.md](references/risk-positioning.md): fixed-risk sizing, ATR/structure stops, concentration caps, conditional Kelly, and option-risk haircuts.
- [references/tactical-timing.md](references/tactical-timing.md): same-day/pre-market/opening-range scenarios, dynamic entry conditions, short-horizon Kelly tiers, and confidence output.
- [references/position-timing-report.md](references/position-timing-report.md): consecutive Kelly, stop/target P/L, share rounding, $10,000 simulation, and short-term report tables.
- [references/evidence-policy.md](references/evidence-policy.md): source hierarchy, freshness, conflicts, and confidence.
- [references/catalyst-context.md](references/catalyst-context.md): delta-first catalysts, macro exposure, expectations, insider and crowding context.
- [references/distilled-research-governance.md](references/distilled-research-governance.md): Evidence Freeze, Claim Graph, constrained reviews, Arbiter, and research states.
- [references/decision-memory.md](references/decision-memory.md): point-in-time decision records, outcomes, calibration, and reflection.
- [references/ibkr-history-limits.md](references/ibkr-history-limits.md): high-frequency history depth, step sizes, paging, and pacing.
- [references/provider-setup.md](references/provider-setup.md): credentials, source-of-truth hierarchy, SEC User-Agent, FRED/ALFRED, IBKR News, Alpha Vantage, FINRA, and Polymarket setup.
- [references/adversarial-review.md](references/adversarial-review.md): frozen Bull/Bear/Skeptic review and Arbiter boundaries.
- [references/report-quality-and-html.md](references/report-quality-and-html.md): freshness/output correctness gates, replay completeness, canonical labeling, report manifest, and modular HTML contract.
- For a low-cost microstructure proxy, fetch IBKR intraday `TRADES` bars with the official API size string `--bar-size "10 secs"` (or `1 secs` when a smaller diagnostic window is specifically useful) and run [scripts/intraday_features.py](scripts/intraday_features.py). Use each bar's `count` as `bar_count_proxy`; it is not a time-and-sales reconstruction and must not be used to claim confirmed aggressor flow. The script also reports realized log-return volatility, session ranges, activity-shape ratios, and a clearly labeled `price_change_signed_volume_proxy`.
- `reqHistoricalData` returns a batch of candlesticks per request. For 1-minute RTH history, a single `--duration "14 D" --bar-size "1 min"` request is a valid practical test; do not reduce it to one request per bar. Fall back to smaller chunks only if the server soft-throttles or session-boundary completeness matters.

## Report contract

Start with:

```text
As-of / price timestamp / filings cutoff
Evidence completeness / underwriting status
Primary horizon / data limitations
```

Then report: thesis, variant perception, what is priced in, what changed since the prior evaluation, catalyst/macro/expectation context, key evidence, Claim Graph summary, Bull/Bear/Skeptic review, Research Arbiter state, invalidation conditions, at least four explicit long-horizon scenarios, risk budget, and missing evidence. Preserve that long-horizon section when adding timing analysis. Organize reader-facing risk content by horizon: keep today's short-horizon scenario, entry/invalidation, stop/target P/L ladder, and short-horizon Kelly sizing together only when same-session intraday evidence exists; otherwise label that block `next-session setup` or `daily-structure scenario`. Keep long-horizon scenarios, fundamental/valuation evidence, options event-risk interpretation, and long-horizon position boundaries together afterward. Do not insert long-term scenarios between the inputs and outputs of one short-term setup. Follow [references/position-timing-report.md](references/position-timing-report.md). Use a labeled $10,000 simulation when no account size is supplied. Display allowed position amount in dollars as the primary output; show exact fractional shares only as an auxiliary conversion and do not force 0.5-share rounding. Show dollar P/L at every stop and target. If the user asks for today's or short-horizon timing, add the session-phase/opening-range contract in [references/tactical-timing.md](references/tactical-timing.md), including conditional entry/stop/target criteria and data/setup/sample confidence. For options, include source role, retrieval time, selected expiries, strike window, spot provenance, quote coverage, OI coverage, missing fields, IV formula, total-variance comparison or explicitly weaker ATM proxy, skew method, activity-distribution caveat, Gamma availability status, and evidence grade. Suppress Gamma-wall ranking/visualization when OI is missing, zero/untrusted, or economically unusable; unsigned gross Gamma is not dealer GEX. For Kelly, **always display the available position-ratio chain with exact labels**, even when OOS is insufficient: `p`, `b`, `f_raw_formula`, empirical/full-sample Kelly when actually computed, full Kelly, half Kelly, quarter Kelly, option/event haircut, tail/concentration/fixed-risk caps when available, and the resulting `diagnostic_fractional_kelly_cap`. Never label quarter/fractional Kelly as full-sample Kelly. Separately display `applied_fractional_kelly` and its qualification status; it may be null when standard OOS is not qualified. Never hide a small-sample diagnostic, but never label it validated or automatically apply it to a position. Use "not a recommendation" for scenario work; never map a score to BUY/WATCH/HOLD/AVOID.

When news/catalysts are requested, add a news evidence table with provider, timestamp, articleId, headline, body availability, historical/live status, deduplication status, evidence grade, and the event's trigger/invalidation implication. Do not count duplicated provider headlines as independent confirmation.

For every rendered observation price anchor, preserve `source`, `method`, `confidence`, `status`, and `confidence_interval`. Support/resistance intervals must be computed from observed evidence and labelled as structural tolerance when they are not statistical confidence intervals. Both the HTML price chip and the plotted support/resistance bar must expose all of these fields on hover; do not show a bare support/resistance number without its evidence and interval or an explicit unavailable state.
The plotted level map must suppress any technical level that cannot be matched to a validated deterministic anchor; it must not render an unsupported price with a placeholder evidence state.

When filings, macro, consensus, short-sale flow, or event-market context is requested, use the matching deterministic adapter before interpretation: `fetch_sec_research.py`, `fetch_fred_macro.py`, `fetch_alpha_vantage_research.py`, `fetch_finra_short_volume.py`, `fetch_polymarket_context.py`, and `normalize_ibkr_news.py`. Cache successful responses and disclose empty, quota-limited, delayed, or partial packets. Do not treat a 403, quota note, or missing field as a market signal.

Use the template in [assets/report-template.md](assets/report-template.md) for full research. Prefer `report_manifest.json` as the shared machine-readable report contract using [schemas/report-manifest.schema.json](schemas/report-manifest.schema.json) and [assets/report-manifest-template.json](assets/report-manifest-template.json). Validate it with [scripts/validate_report_manifest.py](scripts/validate_report_manifest.py). HTML is the default rich reader-facing report and is rendered with [scripts/render_html_report.py](scripts/render_html_report.py); Markdown and JSON remain audit/support artifacts. A module-only request uses the same renderer with `--modules` and must still produce a complete standalone HTML document for that module.

## Validation

Run:

```powershell
python scripts/validate_inputs.py --bars tests/fixtures/bars_xe.json
python scripts/stock_eval_engine.py --symbol TEST --data tests/fixtures/bars_xe.json --options-front tests/fixtures/options_front.json --options-back tests/fixtures/options_back.json --out tests/fixtures/golden_output.json
python scripts/validate_report_manifest.py --manifest assets/report-manifest-template.json
python C:\Users\pt-desktop\.codex\skills\.system\skill-creator\scripts\quick_validate.py .
python -m unittest discover -s tests -p "test_*.py"
```

The engine's output is deterministic for a fixed `as_of` and input fixture. It must fail closed on malformed bars, crossed markets, non-positive prices, insufficient observations, stale-after-event module evidence, invalid research-state labels, unavailable Gamma being rendered as a wall, or intraday timing claims without intraday evidence.
