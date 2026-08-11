# Research provider setup and source roles

The stock-evaluation skill is IBKR-first for market/options data, but a complete research packet needs independent primary/company/macro/expectations evidence. Provider roles are intentionally narrow so one convenient API cannot silently become the source of truth for everything.

## P1 required sources

### SEC EDGAR — primary filings and XBRL

Official documentation:
- https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- https://www.sec.gov/about/developer-resources

Authentication: none. Set a descriptive contact header:

```text
SEC_USER_AGENT="IBKR_STOCKEVALSYS research@example.com"
```

Use `scripts/fetch_sec_research.py`. It resolves ticker -> CIK, reads submissions, filters recent 10-K/10-Q/8-K/Form 4/13D/G filings to `as_of`, reads companyfacts, maps a conservative canonical financial set, and parses recent ownership XML when available.

SEC is the default source of truth for reported GAAP facts. Non-GAAP KPIs, guidance, backlog, product metrics, and management language still require the filing exhibit or company IR document.

### Company Investor Relations — primary guidance and KPIs

There is no universal API. Prefer the issuer's earnings release, shareholder letter, supplemental workbook, presentation, and prepared remarks. If an earnings release/presentation is attached to an 8-K, preserve the SEC exhibit URL as the canonical source.

Store at minimum: `symbol`, `document_type`, `published_at`, `available_at`, `retrieved_at`, `source_url`, `title`, `period`, and a content hash. Never substitute a news summary for a primary KPI when the primary document is available.

### FRED / ALFRED — macro and historical vintages

Official documentation:
- https://fred.stlouisfed.org/docs/api/fred/
- https://fred.stlouisfed.org/docs/api/fred/series_observations.html

Set:

```text
FRED_API_KEY=...
```

Use `scripts/fetch_fred_macro.py`. In historical research pass `--as-of YYYY-MM-DD`; the adapter sets `realtime_start` and `realtime_end` to the cutoff so later revisions are excluded.

Default starter series: DFF, DGS2, DGS10, T10Y2Y, CPIAUCSL, PCEPILFE, UNRATE, PAYEMS, INDPRO, BAMLH0A0HYM2, DCOILWTICO. Do not interpret every series for every company; select exposures that can actually affect the thesis.

### IBKR News — company and market news

Use the existing project-local IBKR MCP. Do **not** modify the MCP to add the research layer. The relevant tools are:

1. `ibkr_get_news_providers`
2. `ibkr_get_news_articles`
3. `ibkr_get_news_article` when the full article is needed

Normalize the returned JSON with `scripts/normalize_ibkr_news.py` before evidence freeze. Free/paid provider availability depends on the connected IBKR account. A headline is not a primary-source substitute for a filing, guidance table, or contract announcement.

## P2 expectation/crowding sources

### Alpha Vantage — consensus estimates and transcript complement

Official documentation: https://www.alphavantage.co/documentation/

Set:

```text
ALPHA_VANTAGE_API_KEY=...
```

Use `scripts/fetch_alpha_vantage_research.py` for:
- `EARNINGS_ESTIMATES`: EPS/revenue estimates, analyst counts and revision fields exposed by the provider;
- `EARNINGS_CALENDAR`: scheduled earnings date;
- `EARNINGS_CALL_TRANSCRIPT`: optional quarter-specific transcript.

Consensus is a market-expectations input, not a reported company fact. Current API responses are not automatically PIT-safe for historical replay; each estimate/revision needs a timestamp at or before the historical cutoff.

### FINRA Reg SHO daily short-sale volume — crowding/flow proxy

Official documentation:
- https://developer.finra.org/docs
- https://developer.finra.org/docs/api-explorer/query_api-equity-reg_sho_daily_short_sale_volume

No key is required for the public dataset. Use `scripts/fetch_finra_short_volume.py`. The adapter aggregates reporting-facility rows by date and deliberately calls the output `SHORT_SALE_FLOW_PROXY`.

Do not call the ratio short interest. FINRA daily short-sale volume is transaction flow reported to FINRA facilities and differs from outstanding short positions.

### Polymarket — optional market-implied event context

Official documentation:
- https://docs.polymarket.com/api-reference/predictions/overview
- https://docs.polymarket.com/api-reference/search/search-markets-events-and-profiles

No key is needed for public search. Use `scripts/fetch_polymarket_context.py`. Only include a market when its resolution question maps directly to a material catalyst. Label outcomes `MARKET_IMPLIED_EXPECTATION`, not `FACT` or objective probability.

### Stocktwits / Reddit

These are not required for P1/P2 core research. Add them only after official access is available and the data can be timestamped and snapshotted. Their role is narrative/attention/crowding, never intrinsic value.

## Source-of-truth hierarchy

For a material numeric company claim, default to:

1. SEC filing / filed exhibit
2. issuer IR release or supplemental data
3. licensed structured provider with timestamp
4. reputable secondary reporting
5. social/narrative sources

IBKR remains primary for price, bars, options and liquidity. FRED/ALFRED remains primary for the selected official macro series. Consensus and prediction markets answer "what is expected/priced", not "what is true".

