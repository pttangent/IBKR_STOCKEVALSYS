# IBKR_STOCKEVALSYS

Evidence-backed single-stock research with IBKR/TWS as the primary market/options source, deterministic calculations before analyst interpretation, JSON-first report generation, and replayable evidence-chain packages.

This repository contains the `stock-eval-system` skill plus the project-local, read-only IBKR MCP used by the skill. It is a research system, not an autonomous trading agent.

## Repository layout

```text
skill/       research skill, deterministic engine, schemas, renderers and validators
ibkr-mcp/    project-local IBKR/TWS MCP server and tests
docs/        versioned documentation and current full HTML report example
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
- Kelly sizing separates historical edge from current risk, then shows full / half / quarter variants and portfolio constraints.
- Default position illustration uses a clearly labelled **$10,000 simulation account** unless a different account size is supplied to the deterministic engine.
- Intraday, short-term and long-term scenarios are represented separately.
- Intraday scenario construction is **compositional and event-driven**, not a fixed gap-up/flat/gap-down template.
- Concrete scenario prices are provenance-bearing anchors: support, resistance, same-session VWAP/OR, moving averages and volatility bands have distinct roles and cannot silently substitute for one another.
- Reader-facing HTML uses Chinese as the primary reading language and keeps important chart interpretation visible.

## Quick start

```bash
cp .env.example .env

cd ibkr-mcp
uv sync
uv run python run_stdio.py
cd ..

python skill/scripts/fetch_sec_research.py --symbol NVDA --as-of 2026-08-07 --output runs/NVDA/sec.json
python skill/scripts/fetch_fred_macro.py --as-of 2026-08-07 --output runs/NVDA/macro.json
python skill/scripts/fetch_finra_short_volume.py --symbol NVDA --as-of 2026-08-07 --output runs/NVDA/finra.json

python skill/scripts/build_evidence_packet.py --symbol NVDA --as-of 2026-08-07 \
  --source runs/NVDA/sec.json --source runs/NVDA/macro.json \
  --output runs/NVDA/evidence.json
```

## Structured report pipeline

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

## Compositional scenario trees

A full report separates three horizons:

- **日內:** first determine which real structure is being tested, then compose `突破/受阻/跌破 -> 回踩/反抽 -> 守住/失守 -> 再攻/假突破/bear trap/整理` paths.
- **短期:** days/weeks → repair/reclaim, range digestion, or breakdown using completed-session evidence.
- **長期:** quarters+ → thesis strengthen, limited improvement, weaken, or invalidate using company-specific operating economics and valuation.

The intraday tree does **not** use `gap-up / near-flat / gap-down` as a universal spine. Gap and prior close may remain contextual metadata, but the structural tree should be anchored to actual calculated evidence such as S1/S2/R1/R2, EMA20/SMA50 and same-session VWAP/ORH/ORL when those values actually exist.

Each numeric scenario anchor should retain `value`, `role`, `source`, `method`, `confidence`, and `status`. ATR/Bollinger are volatility space rather than magical support/resistance. Missing same-session VWAP/ORH/ORL remain missing until formed.

See [`skill/references/scenario-tree-reasoning.md`](skill/references/scenario-tree-reasoning.md) and [`skill/references/tactical-timing.md`](skill/references/tactical-timing.md).

## Current versioned full HTML example

The old GEV/XE examples and the earlier partial INTC v2 mock have been retired. The current example is:

- [`INTC_full_report_example.html`](docs/examples/html/INTC_full_report_example.html) — complete Chinese report with research posture, fundamentals, valuation, technical evidence, options, Kelly/$10k sizing, governance, evidence chain and all three scenario horizons.
- [`INTC_full_structured_report.mock.json`](docs/examples/html/INTC_full_structured_report.mock.json) — full structured semantic mock behind the demonstration.
- [`docs/examples/html/INDEX.html`](docs/examples/html/INDEX.html) — browser-oriented entry page.

The example is explicitly marked **DEMO / 部分 MOCK**. It uses frozen/reproducible values where available and clearly illustrative values where necessary to show the full layout. It is not live INTC research evidence.

The price colors in the example have semantic meaning:

- support = green;
- resistance = red;
- same-session VWAP/OR = cyan;
- moving averages = purple;
- ATR/volatility room = amber;
- current/reference price = neutral.

## Report correctness rules

Reader-facing output must preserve these distinctions:

- Evidence and calculations must be current enough for the report `as_of`; post-event prices must not silently use stale pre-event fundamentals.
- Primary SEC/company IR evidence takes priority for reported company facts when available.
- Missing option fields remain missing. Missing OI, volume, quote, Greeks or one straddle leg must not silently become zero.
- OI is not dealer positioning. Signed/dealer Gamma requires defensible sign evidence.
- All-zero or economically untrusted OI/Gamma returns an unavailable/suppressed state rather than a fake wall.
- Kelly labels must distinguish formula/empirical edge, full/half/quarter, qualification tier, risk overlays, diagnostic guidance and actually applied position constraints.
- A report without current-session ORH/ORL/VWAP evidence may present a next-session conditional event tree, but may not display invented same-session levels or claim a branch has already been confirmed.
- Prior close is context/gap metadata, not a replacement for deterministic support/resistance or same-session structural anchors.
- Scenario numeric anchors must remain traceable to a deterministic/source artifact; unsourced prices should fail validation rather than render as authoritative levels.
- Full-research replayability requires frozen evidence/source artifacts, claim/review/arbitration artifacts, deterministic outputs, `structured_report.json`, reader outputs, manifest and checksums.

For provider setup and exact source roles, read `skill/references/provider-setup.md`. For report quality, read `skill/references/report-quality-and-html.md`. For evidence-frozen review, read `skill/references/adversarial-review.md`. For options/data limitations, read [`limitation.md`](limitation.md).

## Safety boundary

This repository is for research. The stock-evaluation skill does not place orders, does not call IBKR order APIs, and does not mechanically map a score to BUY/HOLD/SELL.
