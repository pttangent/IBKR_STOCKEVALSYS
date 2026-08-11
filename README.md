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
                         final report
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

For provider setup and exact source roles, read `skill/references/provider-setup.md`. For the adversarial-review contract, read `skill/references/adversarial-review.md`. For the P3 calibration loop, read `skill/references/decision-memory.md`.

The free-tier, entitlement, pacing, fallback, and especially options-data boundaries are documented in [`limitation.md`](limitation.md). Read it before interpreting a missing chain, empty bar response, IV estimate, or microstructure signal.

The MCP-specific setup, tool inventory, and news/streaming notes are in `ibkr-mcp/README.md`, `ibkr-mcp/docs/SETUP.md`, `ibkr-mcp/docs/NEWS.md`, and `ibkr-mcp/docs/TOOLS.md`.

## Safety boundary

This repository is for research. The stock-evaluation skill does not place orders, does not call IBKR order APIs, and does not mechanically map a score to BUY/HOLD/SELL.
