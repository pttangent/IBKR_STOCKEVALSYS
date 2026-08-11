# IBKR_STOCKEVALSYS

Evidence-backed single-stock research with IBKR/TWS as the primary market/options source and deterministic calculations before analyst interpretation.

This repository contains the current `stock-eval-system` skill plus the project-local, read-only IBKR MCP used by the skill. The MCP is vendored here so the skill, provider contracts, news fixes, option-chain qualification, tests, and runtime configuration remain versioned together. It is not an autonomous trading agent.

## Repository layout

```text
skill/       Evidence-backed research skill, deterministic engine, provider adapters
ibkr-mcp/    Project-local IBKR/TWS MCP server, tests, news and options tools
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
                    report_manifest.json
                        /           \
                  Markdown        HTML
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
- Evidence-packet, claim-graph, review, and arbitration schemas plus cross-artifact validation.
- Bull / Bear / Skeptic / Arbiter operating contracts in the skill references.
- Structured decision/outcome SQLite memory with multiclass Brier calibration before any narrative reflection.
- Report-output governance distilled from real evidence/report audits: freshness barrier, primary-source priority, missing-not-zero, exact research-state/Kelly labels, intraday evidence gate, and Gamma/OI suppression rules.
- Modular standalone HTML renderer for full reports or selected modules, with charts generated from structured run artifacts rather than prose.
- `report_manifest.json` schema/template plus a lightweight invariant validator so Markdown and HTML can share one machine-readable report contract.

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

## Modular HTML reports

Install the renderer-only dependencies in the environment used for report generation:

```bash
pip install -r skill/requirements-html.txt
```

Render a full standalone HTML report from a Markdown narrative plus the structured run directory:

```bash
python skill/scripts/render_html_report.py \
  --report NVDA_complete_report.md \
  --run-dir runs/NVDA \
  --output NVDA_complete_report.html
```

Render only one module, or a selected set of modules:

```bash
python skill/scripts/render_html_report.py --report NVDA_complete_report.md --run-dir runs/NVDA --output NVDA_options.html --modules options
python skill/scripts/render_html_report.py --report NVDA_complete_report.md --run-dir runs/NVDA --output NVDA_tactical.html --modules technical,options,risk
```

Supported modules are `overview,fundamentals,valuation,technical,options,governance,risk,scenarios,evidence`.

The renderer embeds Plotly JS in the output so the generated file is standalone. It suppresses unavailable Gamma charts when OI/Gamma evidence is missing or economically zero, and it does not promote missing fields to zero. For the full output-quality contract, read `skill/references/report-quality-and-html.md`. For the machine-readable output contract, use `skill/schemas/report-manifest.schema.json` and `skill/assets/report-manifest-template.json`; validate high-value invariants with `skill/scripts/validate_report_manifest.py`.

For provider setup and exact source roles, read `skill/references/provider-setup.md`. For the adversarial-review contract, read `skill/references/adversarial-review.md`. For the P3 calibration loop, read `skill/references/decision-memory.md`.

The free-tier, entitlement, pacing, fallback, and especially options-data boundaries are documented in [`limitation.md`](limitation.md). Read it before interpreting a missing chain, empty bar response, IV estimate, or microstructure signal.

The MCP-specific setup, tool inventory, and news/streaming notes are in `ibkr-mcp/README.md`, `ibkr-mcp/docs/SETUP.md`, `ibkr-mcp/docs/NEWS.md`, and `ibkr-mcp/docs/TOOLS.md`.

## Safety boundary

This repository is for research. The stock-evaluation skill does not place orders, does not call IBKR order APIs, and does not mechanically map a score to BUY/HOLD/SELL.
