# Provider routing

Official documentation must be consulted for uncertain behavior: [IBKR TWS API](https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/), [IBKR market-data requests](https://www.interactivebrokers.com/docs/tws-api/doc/quick-start/requesting-market-data), [IBKR subscriptions](https://www.interactivebrokers.com/campus/ibkr-api-page/market-data-subscriptions/), [Massive Options REST](https://massive.com/docs/rest/options/overview), [Massive contracts](https://massive.com/docs/rest/options/contracts/all-contracts), [Massive option bars](https://massive.com/docs/rest/options/aggregates/custom-bars), [Massive snapshots](https://massive.com/docs/rest/options/snapshots/option-contract-snapshot), [Massive pricing](https://massive.com/pricing?product=options), [yfinance Ticker](https://ranaroussi.github.io/yfinance/reference/api/yfinance.Ticker.html), [yfinance download](https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html), and [yfinance disclaimer](https://ranaroussi.github.io/yfinance/index.html).

## IBKR/TWS

Use `ib_async` against the local TWS/IB Gateway socket, normally `127.0.0.1:7497` for paper trading. Qualify `Stock(symbol, "SMART", "USD")` before requests. Use `readonly=True`, `useRTH=True`, and capture `marketDataType`, quote timestamp, and IBKR error codes. A successful socket connection is not evidence of a live entitlement: distinguish live, delayed, frozen, no subscription, and stale.

Historical bars: `reqHistoricalDataAsync` with `TRADES`, `1 day` bars, and enough history for the requested indicator. For intraday acquisition, use the retry/chunk adapter: `scripts/fetch_intraday_resilient.py` first retries a 30-day 1-minute batch on fresh read-only clients, then falls back to `14 D + 14 D + 4 D` chunks. Never discard a timeout as an empty dataset. Option chains: use `reqSecDefOptParams` to enumerate expirations/strikes, then request a bounded quote slice only for selected expirations and near-spot strikes. Record error 354/10167 as missing option market data rather than converting model fields to market quotes. Never place an order from this skill.

## Massive REST

Use `MASSIVE_API_KEY` and optional `MASSIVE_BASE_URL` environment variables. Never place keys in JSON, Markdown, shell history, or source code. The free tier is rate-limited, so the fetcher spaces calls and records HTTP status, provider timestamp, and missing fields.

Useful endpoints for this skill:

- `/v2/aggs/ticker/{TICKER}/range/1/day/{FROM}/{TO}` for historical adjusted OHLCV.
- `/v2/aggs/ticker/{TICKER}/range/1/minute/{FROM}/{TO}` for minute aggregates when IBKR is unavailable or for a cross-check. The free tier includes minute aggregates, but not second aggregates or raw trades; the endpoint may include extended-hours bars, so filter to 09:30–16:00 ET before comparing with IBKR RTH data.
- `/v2/aggs/ticker/{TICKER}/prev` for the latest available aggregate when supported by the account.
- `/v3/reference/options/contracts` for contract reference. Contract reference is not a quote and does not imply IV/Greeks.
- The Options Contract Snapshot endpoint can expose quotes, IV, Greeks, and OI only when the current plan includes that endpoint; the official plan matrix marks it unavailable to Options Basic Free. Do not treat contract reference as a substitute.

Treat Massive results as EOD/delayed unless the response and account explicitly establish otherwise. Do not infer option direction from put/call totals.

## Fallback ladder and source reconciliation

For a requested 1-minute window, use this order:

1. IBKR single batch with a fresh readonly client and bounded retries.
2. IBKR smaller chunks with timestamp cursor, deduplication, and a coverage check.
3. Massive minute aggregates as a REST fallback/cross-check; do not use it to fabricate 10-second bars.
4. `scripts/fetch_yfinance_intraday.py` as the final fallback. It chunks 1-minute requests into windows no longer than seven days because Yahoo may reject longer individual requests even though yfinance documents a broader recent-intraday horizon. It does not provide IBKR-style trade count, and it is an unofficial research wrapper around Yahoo's publicly available APIs. It is not the primary source for a reproducible execution-adjacent report.

Run `scripts/compare_intraday_sources.py` on overlapping packets. Compare timestamps and close prices first. Treat volume mismatches separately because IBKR can return shares or round lots depending on the TWS/API setting, while Massive returns its own volume convention. A fallback packet must record which source was selected, every failed attempt, the reason for failure, and the fields that are unavailable from the fallback source.

The current Options Basic free tier is documented as $0/month with 5 API calls/minute, two years of historical data, EOD data, reference data, corporate actions, technical indicators, and minute aggregates. It does not list real-time Greeks/IV, open interest, snapshots, trades, quotes, WebSockets, or second aggregates. Verify the account dashboard before relying on any field.

## Web and filings

Use company IR, SEC filings, earnings releases, and transcripts for reported facts. Capture URL, published date, access timestamp, period covered, and evidence label. Use web search for current events and market context, but preserve primary sources for reported financials.

## MCP decision rule

For a free tier, keep Massive as a REST adapter inside the skill. Add Massive MCP only when a connected client needs interactive discovery across many endpoints, shared auth/observability, or repeated tool calls from several skills. MCP does not upgrade the underlying entitlement and should not be added solely to obtain Greeks or snapshots that the account does not provide. IBKR MCP is also optional because the existing local readonly adapter can be called directly by the deterministic fetcher.

Massive's official AI-tools documentation describes a hosted remote MCP at `https://mcp.massive.com/` and a self-hosted server for larger local datasets; both mirror the user's entitlements. Treat third-party package names or old `npx` examples as unverified until checked against the current official documentation.
