# Multi-source external data

Use this reference when a report needs filings, macro regime, consensus, public event probabilities, short-sale activity, or retail attention. The project smoke test is:

```powershell
& .\.venv\Scripts\python.exe .\skill\scripts\test_external_sources.py --symbol NVDA --out .\data\external_sources_test_YYYY-MM-DD.json
```

It loads `.env.local`, never records secret values, and reports status/schema summaries only. Do not call every endpoint automatically in a normal report: Alpha Vantage is limited, SEC and FRED are primary evidence, and the other services are role-specific complements.

## Project capability snapshot (validated 2026-08-13)

Treat this as the local capability baseline, not a permanent provider guarantee; rerun `test_external_sources.py` when credentials, entitlements, or provider behavior change.

| Source/capability | Validated state | Skill use |
|---|---|---|
| SEC ticker-to-CIK, submissions, companyfacts, 10-K/10-Q/8-K/Form 4 | pass with project User-Agent | primary filings/facts/insider |
| Issuer IR sites | available | primary releases/KPI/guidance/presentations |
| FRED + ALFRED vintage | available | current macro + PIT macro |
| IBKR News | available | timestamped news/catalyst feed in project MCP |
| Alpha Vantage fundamental/earnings endpoints | `OVERVIEW`, `INCOME_STATEMENT`, `BALANCE_SHEET`, `CASH_FLOW`, `SHARES_OUTSTANDING`, `EARNINGS`, `EARNINGS_ESTIMATES`, `EARNINGS_CALENDAR`, `LISTING_STATUS` returned valid HTTP 200 structures for KLAC; calendar/listing are CSV | secondary financial/earnings complement; cache, parse by content type, and enforce quota handling |
| Finnhub reported/context endpoints | `profile2`, `peers`, `metric`, `company-news`, `earnings`, `calendar`, `symbols`, `financials-reported` returned HTTP 200 for TER; standardized `financials` returned 403 | secondary quote/news/expectation/event and reported-financial complement; never overrides SEC or repairs period mismatch |
| SimFin list/general/statements/shares | list returned HTTP 200; legacy non-compact general/statements returned 404; compact general/statements/shares returned HTTP 200; one rapid request returned 429 | secondary as-reported/fundamental cross-check; use compact routes, sequential pacing, cache, and no automatic PIT or SEC replacement |
| Alpaca paper/trading + market data | paper account HTTP 200; assets, clock, calendar, stock IEX snapshot/trade/quote/bars, news, corporate actions, option contracts and indicative option snapshots HTTP 200; SIP stock, OPRA option snapshots, and historical option bars HTTP 403 | market/event layer; no fundamental statements; Basic indicative options are quote/trade evidence only unless IV/Greeks are actually present |
| Massive | available | historical market/options complement |
| yfinance history/options expiry discovery | available | independent unofficial cross-check |
| Polymarket Gamma/CLOB | available | market-implied event context |
| FINRA Reg SHO CSV | available | short-sale-volume proxy |
| Stocktwits legacy stream | available, low-confidence | retail attention only |
| Nasdaq Data Link | token not configured | do not depend on it |
| Reddit | OAuth/official approval unavailable | do not use |

This snapshot does not modify MCP servers or broker infrastructure; it only constrains skill routing around tested capabilities.

See [api-capability-matrix.md](api-capability-matrix.md) for the request parameters and observed response schemas for every endpoint in the fundamental-source checklist.

For the endpoint-by-endpoint evidence and the distinction between HTTP 200, empty payloads, quota notes, and entitlement failures, read [api-capability-matrix.md](api-capability-matrix.md).

## Credentials and official documentation

Credentials are local-only environment variables in `stock-eval-system/.env.local`; never put them in source, JSON, Markdown, shell history, or a report.

| Source | Environment | Official documentation | Role |
|---|---|---|---|
| SEC EDGAR | `SEC_USER_AGENT` (no key) | [EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces), [developer resources](https://www.sec.gov/about/developer-resources) | filings, XBRL, Form 4 |
| Company IR | none | issuer IR site | earnings release, guidance, KPI, presentation |
| FRED/ALFRED | `FRED_API_KEY` | [FRED API](https://fred.stlouisfed.org/docs/api/fred/), [API keys](https://fred.stlouisfed.org/docs/api/fred/v2/api_key.html) | macro series and point-in-time vintages |
| IBKR News | local TWS/MCP | [IBKR News API](https://interactivebrokers.github.io/tws-api/news.html) | historical headlines and selected article bodies |
| Alpha Vantage | `ALPHA_VANTAGE_API_KEY` | [Alpha Vantage docs](https://www.alphavantage.co/documentation/) | estimates, transcripts, earnings calendar |
| Finnhub | `FINNHUB_API_KEY` | [reported financials](https://finnhub.io/docs/api/financials-reported), [metrics](https://finnhub.io/docs/api/metric) | secondary reported-financials/metrics cross-check; standardized statements may be entitlement-limited |
| SimFin | `SIMFIN_API_KEY` | [Getting Started](https://simfin.readme.io/reference/getting-started-1), [statements](https://simfin.readme.io/reference/statements-1), [rate limits](https://simfin.readme.io/reference/rate-limits) | secondary statements/general/shares cross-check; Authorization `api-key <key>` |
| Alpaca | `ALPACA_API_KEY_ID`, `ALPACA_API_SECRET_KEY`, `ALPACA_TRADING_BASE_URL`, `ALPACA_DATA_BASE_URL` | [Getting started](https://docs.alpaca.markets/us/docs/getting-started), [market data](https://docs.alpaca.markets/us/docs/about-market-data-api), [option chain](https://docs.alpaca.markets/us/v1.4.2/reference/optionchain) | IEX stock market data, indicative options, news, corporate actions, assets; not accounting fundamentals |
| Massive | `MASSIVE_API_KEY`, `MASSIVE_BASE_URL` | [Massive REST](https://massive.com/docs/rest/quickstart) | historical market/options complement |
| yfinance | `YFINANCE_ENABLED` | [yfinance docs](https://ranaroussi.github.io/yfinance/) | independent fallback/cross-check; unofficial |
| Polymarket | none | [Polymarket API](https://docs.polymarket.com/api-reference/introduction) | market-implied event probability, never a fact |
| FINRA | none for public read route | [FINRA Developer Center](https://developer.finra.org/docs) | Reg SHO daily short-sale volume proxy |
| Stocktwits | Firestream credentials not configured | [Firestream docs](https://firestream.stocktwits.com/documentation) | retail attention/sentiment, low-confidence complement |
| Reddit | OAuth + explicit access/approval | [Data API wiki](https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki) | not used until authorized |

SEC requests must identify the client with a real contact email in `SEC_USER_AGENT`; a descriptive value without an email may be blocked. The smoke test may use a known CIK only to test the downstream SEC endpoints when the ticker mapping file is blocked; production must fix the User-Agent and use the official mapping file.

## Priority routing for this skill

- **P1 / core underwriting**: SEC + issuer IR, FRED/ALFRED, IBKR News, Alpha Vantage expectations when relevant, plus existing IBKR/Massive/yfinance market/options routes.
- **P2 / expectation and crowding overlays**: Alpha Vantage revisions, SEC Form 4, Polymarket when event-matched, FINRA Reg SHO, Stocktwits low-confidence attention; Finnhub may cross-check news/quote context.
- **P3 / learning**: persist point-in-time evidence manifests and decision/outcome records locally per `references/decision-memory.md`; do not add a new vendor by default.

Do not call a P2 source merely because it exists. Each source must answer a specific claim, catalyst, expectation, or crowding question.

## Routing rules

### Facts and filings

1. Resolve ticker → CIK using SEC `company_tickers.json`.
2. Request `submissions/CIK##########.json`.
3. Request `api/xbrl/companyfacts/CIK##########.json`.
4. Normalize facts before interpretation; do not ask the model to infer financial series directly from raw XBRL.
5. Use issuer IR for non-XBRL KPI, guidance, presentations, and releases. Preserve URL, published time, retrieved time, document type, and hash/path for PIT replay.

Form 4 is part of SEC evidence. Classify transaction code before interpretation: open-market purchase (`P`) is not equivalent to grant (`A`), exercise (`M`), tax withholding (`F`), or an ordinary sale (`S`). Do not treat every insider sale as bearish.

### Macro and PIT

Use FRED series observations for current macro context and the same FRED API with `vintage_dates` for point-in-time research. At minimum support `DFF`, `DGS2`, `DGS10`, `T10Y2Y`, `CPIAUCSL`, `PCEPILFE`, `UNRATE`, `PAYEMS`, `INDPRO`, `BAMLH0A0HYM2`, and `DCOILWTICO`. Store `series_id`, observation date, realtime start/end, vintage date, value, and retrieval time.

### Consensus and transcripts

Use Alpha Vantage only for the requested consensus layer:

- `EARNINGS_ESTIMATES`: estimates, analyst count, revisions where returned;
- `EARNINGS_CALL_TRANSCRIPT`: transcript by symbol/quarter;
- `EARNINGS_CALENDAR`: event timing.

The free quota is small. Cache by symbol/quarter/day, do not repeat calls after a successful response, and disclose if the provider returns a quota note, empty CSV, or partial fields. Finnhub can complement quote/news checks, but never override SEC/IR reported financials merely because it responds faster.

### Event probability and crowding

- Polymarket Gamma/CLOB public market data are `MARKET_IMPLIED_EXPECTATION`, not a factual probability or company forecast. Preserve market ID, question, outcome, timestamp, and source URL.
- FINRA `regShoDaily` is daily short-sale volume. Label it `SHORT_SALE_FLOW_PROXY`; it is not consolidated short interest. The public endpoint may return CSV even with HTTP 200, so parse content type/body rather than requiring JSON.
- Stocktwits' legacy public symbol endpoint may respond, but it is not evidence that Firestream access is configured. Use only as low-grade attention/sentiment context and preserve the endpoint/observation time.
- Reddit requires OAuth and current policy/access approval. Do not scrape or use unauthenticated responses as evidence; a 403 is a permission result, not a market signal.

### Market data fallback

For prices/bars/options retain the existing priority: IBKR → Massive → yfinance. This is not a blind fallback: reconcile timestamps, timezone, adjustment, quote status, volume convention, and missing fields. yfinance is an unofficial wrapper and cannot provide IBKR `barCount` semantics.

## Evidence and report contract

Every external record must retain:

```text
source
endpoint or source_url
retrieved_at
published_at / observation_date / vintage_date when available
provider status and error
raw identifier (CIK, accession, series_id, articleId, market_id)
evidence grade
```

Use source roles rather than source-counting: SEC/IR can support reported facts; FRED can support macro regime; IBKR news can support a timestamped catalyst headline/body; Alpha/Finnhub can support market expectations; Polymarket can support an implied probability; FINRA/Stocktwits can support crowding proxies. Multiple feeds repeating the same story are not independent confirmations.
