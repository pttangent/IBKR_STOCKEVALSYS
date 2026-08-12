# IBKR_STOCKEVALSYS

Evidence-backed single-stock research with IBKR/TWS as the primary market/options source, deterministic calculations before analyst interpretation, JSON-first report generation, and replayable evidence-chain packages.

This repository contains the `stock-eval-system` skill plus the project-local, read-only IBKR MCP used by the skill. It is a research system, not an autonomous trading agent.

## Repository layout

```text
skill/       research skill, deterministic engine, schemas, renderers and validators
ibkr-mcp/    project-local IBKR/TWS MCP server and tests
docs/        versioned documentation and current HTML report example
.env.example shared research/TWS configuration template; no secrets
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
                scenario / risk synthesis
                              |
                    structured_report.json
                       /              \
                 Markdown            HTML
                       \              /
                    evidence-chain ZIP
```

`structured_report.json` is the canonical reader-facing semantic source. Markdown and HTML are sibling render targets; the HTML renderer must not parse Markdown to recover report meaning.

## Core behaviors

- SEC/IR primary-source evidence for reported company facts when available.
- FRED/ALFRED point-in-time macro support.
- IBKR market/options/news acquisition with explicit entitlement, timestamp and fallback handling.
- Massive/yfinance as capability-specific research complements, not silent replacements for IBKR evidence.
- Evidence Packet, Claim Graph, Bull/Bear/Skeptic review, arbitration, decision state and checksums.
- `missing != 0` throughout options, valuation and intraday evidence.
- OI/Gamma quality gates: unsigned gross Gamma is not dealer GEX; zero/untrusted OI cannot create a fake wall.
- Explicit intraday evidence gate: without same-session ORH/ORL/VWAP evidence, output a pre-open/next-session plan rather than fake “today confirmed” timing.
- Kelly sizing that separates historical edge from current risk, then shows full / half / quarter variants and portfolio constraints.
- Default position illustration uses a clearly labelled **$10,000 simulation account** unless a different account size is supplied to the deterministic engine.
- Intraday, short-term and long-term scenarios are represented as separate branching trees rather than one flat bull/base/bear table.
- Every major chart includes `WHAT / READ / WHY / LIMIT` interpretation.

## Quick start

```bash
cp .env.example .env

# Start the vendored read-only MCP separately when IBKR/TWS data are needed.
cd ibkr-mcp
uv sync
uv run python run_stdio.py
cd ..

# Examples of evidence acquisition.
python skill/scripts/fetch_sec_research.py --symbol NVDA --as-of 2026-08-07 --output runs/NVDA/sec.json
python skill/scripts/fetch_fred_macro.py --as-of 2026-08-07 --output runs/NVDA/macro.json
python skill/scripts/fetch_finra_short_volume.py --symbol NVDA --as-of 2026-08-07 --output runs/NVDA/finra.json

# Freeze source packets.
python skill/scripts/build_evidence_packet.py --symbol NVDA --as-of 2026-08-07 \
  --source runs/NVDA/sec.json --source runs/NVDA/macro.json \
  --output runs/NVDA/evidence.json
```

## Structured report pipeline

The production report flow is:

```text
raw / normalized evidence
  -> deterministic artifacts (stock_eval.json, options_features.json, valuation snapshot, ...)
  -> structured analyst synthesis / claim outputs
  -> structured_report.json
       -> Markdown renderer
       -> HTML renderer
  -> evidence-chain report package ZIP
```

Build the canonical structured report:

```bash
python skill/scripts/build_structured_report.py \
  --run-dir runs/NVDA \
  --research-content runs/NVDA/research_content.json \
  --out structured_report.json
```

Render Markdown and HTML from the same JSON:

```bash
python skill/scripts/render_markdown_report.py \
  --structured-report runs/NVDA/structured_report.json \
  --output runs/NVDA/NVDA_complete_report.md

python skill/scripts/render_html_report.py \
  --structured-report runs/NVDA/structured_report.json \
  --run-dir runs/NVDA \
  --output runs/NVDA/NVDA_complete_report.html
```

Build the portable evidence-chain package:

```bash
python skill/scripts/build_evidence_chain_package.py \
  --run-dir runs/NVDA \
  --structured-report runs/NVDA/structured_report.json \
  --output runs/NVDA/NVDA_evidence_chain_report.zip
```

A module-only reader view uses the same structured JSON and renderer with `--modules`.

## Kelly / position guidance

Kelly is presented as a chain rather than a single unexplained number:

```text
same-setup outcomes
  -> p / b formula Kelly
  -> empirical log-growth Kelly
  -> conservative edge selection
  -> current realized-volatility and option/event risk overlay
  -> FULL / HALF / QUARTER
  -> concentration / stop-risk / liquidity / mandate caps
  -> final NAV %, dollars, shares and risk footprint
```

When evidence is usable but imperfect, the report should normally return a labelled `validated`, `conditional`, `exploratory`, `proxy`, or `risk-only` guide. It should abstain only when the available inputs are too incomplete to support a defensible scale.

See [`skill/references/kelly-positioning-knowledge.md`](skill/references/kelly-positioning-knowledge.md) and [`skill/references/risk-positioning.md`](skill/references/risk-positioning.md).

## Scenario trees

A full report separates three decision horizons:

- **Intraday:** premarket context → gap-up / near-flat / gap-down → acceptance / fade / reversal; nodes carry trigger, response, invalidation, action boundary and sizing tier where defensible.
- **Short term:** days/weeks → structure repair / range digestion / breakdown.
- **Long term:** quarters+ → thesis strengthen / mixed / weaken using business economics, capital efficiency, catalysts and valuation rather than intraday microstructure.

See [`skill/references/scenario-tree-reasoning.md`](skill/references/scenario-tree-reasoning.md) and [`skill/references/tactical-timing.md`](skill/references/tactical-timing.md).

## Current versioned HTML example

The legacy GEV/XE examples have been retired. The current example is:

- [`INTC_v2_full_example.html`](docs/examples/html/INTC_v2_full_example.html) — terminal-style v2 full-report mockup showing $10k Kelly full/half/quarter sizing, current-RV translation, binding caps, intraday branching tree, short-term tree, long-term tree and chart interpretation.
- [`INTC_v2_structured_report.mock.json`](docs/examples/html/INTC_v2_structured_report.mock.json) — compact structured source behind the demonstration.
- [`docs/examples/html/INDEX.html`](docs/examples/html/INDEX.html) — example entry page.

The example is explicitly marked **DEMO / PARTIALLY MOCKED** so the complete v2 UI can be demonstrated even when a frozen real evidence bundle lacks some fields. It is not a live INTC conclusion and is not research evidence.

## Report correctness rules

Reader-facing output must preserve these distinctions:

- Evidence and calculations must be current enough for the report `as_of`; post-event prices must not silently use stale pre-event fundamentals.
- Primary SEC/company IR evidence takes priority for reported company facts when available.
- Missing option fields remain missing. Missing OI, volume, quote, Greeks or one straddle leg must not silently become zero.
- OI is not dealer positioning. Signed/dealer Gamma requires defensible sign evidence.
- All-zero or economically untrusted OI/Gamma returns an unavailable/suppressed state rather than a fake wall.
- Kelly labels must distinguish formula/empirical edge, full/half/quarter, qualification tier, risk overlays, diagnostic guidance and actually applied position constraints.
- A report without current-session ORH/ORL/VWAP evidence may present an intraday decision tree as a plan, but may not claim the branch has already been confirmed.
- Full-research replayability requires frozen evidence/source artifacts, claim/review/arbitration artifacts, deterministic outputs, `structured_report.json`, reader outputs, manifest and checksums.

For provider setup and exact source roles, read `skill/references/provider-setup.md`. For report quality, read `skill/references/report-quality-and-html.md`. For evidence-frozen review, read `skill/references/adversarial-review.md`. For options/data limitations, read [`limitation.md`](limitation.md).

## Safety boundary

This repository is for research. The stock-evaluation skill does not place orders, does not call IBKR order APIs, and does not mechanically map a score to BUY/HOLD/SELL.
