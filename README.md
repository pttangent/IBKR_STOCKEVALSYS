# IBKR_STOCKEVALSYS

Evidence-backed single-stock research with IBKR/TWS as the primary market/options source and deterministic calculations before analyst interpretation.

This repository contains the current `stock-eval-system` skill plus the project-local, read-only IBKR MCP used by the skill. The MCP is vendored here so the skill, provider contracts, news fixes, option-chain qualification, tests, runtime configuration, report-quality rules, and HTML output contract remain versioned together. It is not an autonomous trading agent.

## Repository layout

```text
skill/       Evidence-backed research skill, deterministic engine, provider adapters
ibkr-mcp/    Project-local IBKR/TWS MCP server, tests, news and options tools
docs/        Versioned documentation and compact HTML output examples
.env.example Shared research and TWS configuration template (no secrets)
```

## Research architecture

```text
IBKR market/options + SEC + IR + FRED/ALFRED + IBKR News + consensus
                              |
                        evidence freeze
                              |
            deterministic stock-eval calculations
                              |
                         claim graph
                              |
                +-------------+-------------+
                |             |             |
             Bull          Bear          Skeptic
                +-------------+-------------+
                              |
                      Research Arbiter
                              |
                  scenarios / risk state
                              |
                    report manifest
                      /       \
                Markdown     HTML
```

Reviewers are not allowed to browse independently. They may only cite the frozen evidence packet or emit a structured evidence request.

## What was added

- SEC EDGAR adapter: ticker/CIK resolution, submissions, recent filings, XBRL company facts, canonical financial facts, Form 4 parsing.
- FRED/ALFRED macro adapter with point-in-time `realtime_start=realtime_end=as_of` support.
- Alpha Vantage research adapter for earnings estimates, earnings calendar, and optional call transcripts.
- FINRA Reg SHO daily short-sale-volume adapter; values are explicitly labelled a flow proxy, never short interest.
- Polymarket public-search adapter for optional market-implied event context.
- Project-local IBKR MCP with qualified-underlying option-chain discovery, historical option bars, qualified historical news retrieval, explicit news time windows, and read-only research workflows.
- IBKR News normalizer that consumes the MCP output and preserves provider, timestamp, article ID, and body availability.
- Evidence-packet, claim-graph, review, arbitration, and report-manifest schemas plus cross-artifact validation.
- Bull / Bear / Skeptic / Arbiter operating contracts in the skill references.
- Structured decision/outcome SQLite memory with multiclass Brier calibration before any narrative reflection.
- Modular rich HTML renderer with full-report and module-only output.
- Report-quality gates distilled from real report/evidence audits: source freshness barriers, primary-source preference, `missing != 0`, exact Kelly labels, intraday-evidence gating, and replay-completeness disclosure.
- Options Gamma structure that remains unsigned unless dealer/customer position sign is independently inferred; zero/untrusted OI cannot manufacture a Gamma Wall.

## Quick start

```bash
cp .env.example .env

# Start the vendored MCP separately when IBKR/TWS research data are needed.
cd ibkr-mcp
uv sync
uv run python run_stdio.py
cd ..

# SEC: no API key; SEC_USER_AGENT is required.
python skill/scripts/fetch_sec_research.py --symbol NVDA --as-of 2026-08-07 --output runs/NVDA/sec.json

# FRED: requires FRED_API_KEY.
python skill/scripts/fetch_fred_macro.py --as-of 2026-08-07 --output runs/NVDA/macro.json

# Consensus / transcript: requires ALPHA_VANTAGE_API_KEY.
python skill/scripts/fetch_alpha_vantage_research.py --symbol NVDA --include-calendar --output runs/NVDA/consensus.json

# Public sources; no key required.
python skill/scripts/fetch_finra_short_volume.py --symbol NVDA --as-of 2026-08-07 --output runs/NVDA/finra.json
python skill/scripts/fetch_polymarket_context.py --query "AI chip export restrictions" --output runs/NVDA/polymarket.json

# Normalize an ibkr_get_news_articles result from the vendored MCP.
python skill/scripts/normalize_ibkr_news.py --symbol NVDA --input raw_ibkr_news.json --output runs/NVDA/news.json

# Freeze source packets into one evidence packet.
python skill/scripts/build_evidence_packet.py --symbol NVDA --as-of 2026-08-07 \
  --source runs/NVDA/sec.json --source runs/NVDA/macro.json --source runs/NVDA/news.json \
  --source runs/NVDA/consensus.json --output runs/NVDA/evidence.json
```

## Rich HTML reports

The canonical renderer is `skill/scripts/render_html_report.py`. It can emit either the complete research report or one or more independent modules such as `technical`, `options`, or `risk`. Generated reports should keep data quality and missing-evidence warnings reader-visible rather than hiding them only in JSON audit artifacts.

```bash
# Full HTML
python skill/scripts/render_html_report.py \
  --report runs/NVDA/NVDA_complete_report.md \
  --run-dir runs/NVDA \
  --output runs/NVDA/NVDA_complete_report.html

# Options-only HTML
python skill/scripts/render_html_report.py \
  --report runs/NVDA/NVDA_complete_report.md \
  --run-dir runs/NVDA \
  --output runs/NVDA/NVDA_options.html \
  --modules options
```

The report contract and distilled quality gates are documented in [`skill/references/report-quality-and-html.md`](skill/references/report-quality-and-html.md). The machine-readable output contract is [`skill/schemas/report-manifest.schema.json`](skill/schemas/report-manifest.schema.json), with validation through `skill/scripts/validate_report_manifest.py`.

### Versioned HTML examples

Compact examples are kept under [`docs/examples/html/`](docs/examples/html/):

- [`GEV_full_example.html`](docs/examples/html/GEV_full_example.html) — representative full report, including evidence-quality warnings and scenario/risk visualization.
- [`XE_technical_example.html`](docs/examples/html/XE_technical_example.html) — technical-only output.
- [`XE_options_example.html`](docs/examples/html/XE_options_example.html) — options-only output showing the required zero-OI Gamma suppression behavior.

The normal renderer embeds Plotly so generated reports are standalone/offline. The Git-versioned examples use the Plotly CDN only to avoid duplicating several megabytes of library JavaScript per example. They are frozen demonstration artifacts, not live market views.

## Report correctness rules

Reader-facing output must preserve these distinctions:

- Evidence and calculations must be current enough for the report `as_of`; a post-earnings price snapshot cannot silently use pre-earnings fundamentals as if no newer filing exists.
- Prefer primary SEC/company IR evidence for reported company results when available; secondary reporting is a complement, not the default replacement.
- Missing option fields remain missing. Missing OI, volume, quote, Greeks, or one ATM straddle leg must not silently become zero.
- OI is not dealer positioning. Gross Gamma is unsigned unless a defensible position-sign model exists.
- All-zero or economically untrusted OI/Gamma must return an unavailable/suppressed Gamma concentration state rather than ranking fake zero-valued walls.
- Kelly outputs must distinguish raw/full-sample, half, quarter/fractional, OOS-qualified, diagnostic cap, and actually applied Kelly.
- A report without intraday VWAP/ORH/ORL/current-session evidence may present a next-session setup, but not claim current intraday confirmation.
- Full-research replayability requires the underlying evidence packet / source artifacts, Claim Graph, review/arbitration artifacts, and relevant deterministic outputs; prose URLs alone are not a complete frozen research run.

For provider setup and exact source roles, read `skill/references/provider-setup.md`. For the adversarial-review contract, read `skill/references/adversarial-review.md`. For the P3 calibration loop, read `skill/references/decision-memory.md`.

The free-tier, entitlement, pacing, fallback, and especially options-data boundaries are documented in [`limitation.md`](limitation.md). Read it before interpreting a missing chain, empty bar response, IV estimate, or microstructure signal.

The MCP-specific setup, tool inventory, and news/streaming notes are in `ibkr-mcp/README.md`, `ibkr-mcp/docs/SETUP.md`, `ibkr-mcp/docs/NEWS.md`, and `ibkr-mcp/docs/TOOLS.md`.

## Safety boundary

This repository is for research. The stock-evaluation skill does not place orders, does not call IBKR order APIs, and does not mechanically map a score to BUY/HOLD/SELL.
