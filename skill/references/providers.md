# Provider routing

This file is the provider-routing authority for the stock-evaluation skill. When a generic instruction elsewhere says “IBKR first”, the **lane-specific rules below override it** for single-stock research so the live IBKR connection can remain dedicated to the intraday radar.

Official documentation must be consulted for uncertain behavior: [IBKR TWS API](https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/), [IBKR market-data requests](https://www.interactivebrokers.com/docs/tws-api/doc/quick-start/requesting-market-data), [IBKR subscriptions](https://www.interactivebrokers.com/campus/ibkr-api-page/market-data-subscriptions/), [Alpaca market data](https://docs.alpaca.markets/us/docs/about-market-data-api), [Alpaca stock snapshot](https://docs.alpaca.markets/us/reference/stocksnapshotsingle), [Alpaca news](https://docs.alpaca.markets/us/v1.1/reference/news-3), [Alpaca corporate actions](https://docs.alpaca.markets/us/v1.4.2/reference/corporateactions-1), [Massive Options REST](https://massive.com/docs/rest/options/overview), [Massive contracts](https://massive.com/docs/rest/options/contracts/all-contracts), [Massive option bars](https://massive.com/docs/rest/options/aggregates/custom-bars), [yfinance Ticker](https://ranaroussi.github.io/yfinance/reference/api/yfinance.Ticker.html), [yfinance download](https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html), and [yfinance disclaimer](https://ranaroussi.github.io/yfinance/index.html).

## Two-lane architecture

### Research Lane — default for single-stock analysis

The default single-stock research run should **not open an IBKR/TWS market-data session** when non-IBKR evidence can satisfy the requested module. This prevents research jobs from competing with the live radar for IBKR subscriptions, pacing, client sessions, option permissions, and quote capacity.

Default routing:

- Reported fundamentals / filings: SEC + issuer IR.
- Standardized fundamentals / peer-ready schema: SimFin.
- Market expectations / estimate revisions: Alpha Vantage.
- Events / metadata / peers / earnings calendar / quick cross-check: Finnhub.
- Current timestamped stock reaction, IEX quote/snapshot/bars, assets, news, corporate actions, option-contract/indicative context: Alpaca.
- Longer historical adjusted stock bars or independent cross-check: Massive REST when entitled; otherwise Alpaca IEX historical bars or yfinance research fallback, clearly labelled.
- Non-live option research: Alpaca indicative contract/snapshot context + Massive historical/reference + yfinance independent chain/model input as available. Do not wake IBKR solely because IV/Greeks are absent from the Alpaca Basic response.

The Research Lane may use IBKR only when one of these conditions is true:

1. the user explicitly requests IBKR evidence;
2. the requested field is genuinely unavailable from the non-IBKR sources and materially changes the conclusion;
3. exchange-entitled real-time/OPRA evidence is required for the research question;
4. execution-adjacent validation is explicitly requested.

If none applies, an IBKR call is a routing error, not an upgrade.

### Radar Lane — IBKR/TWS reserved for live monitoring

The live radar owns the IBKR/TWS connection for exchange-entitled stock/option quotes, tick/short-bar microstructure, streaming news where available, position/risk monitoring, and execution-adjacent state. Radar work may use a separate clientId/session policy, but research must not consume it by default.

A report should record `data_lane=research_non_ibkr` or `data_lane=radar_ibkr` for every market-data artifact. When a research run crosses into IBKR, record the reason as `ibkr_exception_reason`.

## Alpaca in the Research Lane

Use `scripts/fetch_alpaca_research.py`. The validated Basic/paper environment supports IEX stock snapshot/trade/quote/bars, assets, news, corporate actions, option contracts, and indicative option snapshots. Current entitlement observations are a reproducible environment snapshot, not a permanent vendor guarantee.

Important limits:

- IEX is not consolidated SIP. Label IEX quote/volume as `IEX_ONLY` and do not present it as total-market volume.
- Current Basic account tests returned 403 for SIP stock feed, OPRA option feed, and historical option bars.
- Indicative option snapshots may contain quote/trade fields while IV/Greeks are absent. Missing IV/Greeks must remain missing; do not fabricate them.
- Alpaca is a market/event layer, not an accounting-fundamentals source.
- If a timestamped option price is usable, a deterministic model may derive model IV, but label it `MODEL_IV_FROM_PRICE`, not provider IV and not executable OPRA IV.

For price freshness in a research report, Alpaca IEX snapshot/quote is preferred over opening an IBKR session. For technical history, use Alpaca bars when IEX-only coverage is acceptable; if consolidated/adjusted history materially matters, prefer Massive or an explicitly labelled independent fallback.

## IBKR/TWS

Use `ib_async` against local TWS/IB Gateway only when the lane policy permits it. Qualify `Stock(symbol, "SMART", "USD")` before requests, use `readonly=True`, capture marketDataType/quote timestamp/error codes, and distinguish live, delayed, frozen, no-subscription, and stale states. A successful socket connection is never evidence of entitlement.

For Radar Lane short bars or microstructure, follow the project paging/chunk rules. For options, use the project-local MCP historical-chain path when appropriate; the direct quote/Greeks helper remains hard-blocked unless live option permission is explicitly confirmed. Error 354/10167 is an entitlement diagnostic, not proof that the underlying company lacks data.

Never place an order from this skill.

## Massive REST

Use `MASSIVE_API_KEY` and optional `MASSIVE_BASE_URL`. Keep keys out of artifacts. Useful research endpoints include adjusted daily/minute aggregates and option contract/reference/history. Treat results according to actual account entitlement and timestamp; a reference contract is not a quote and does not imply IV/Greeks.

## yfinance

Use only as an independent research fallback/cross-check. Label provenance `secondary_unofficial`. It may be useful for an independent option chain or historical bars when official APIs are unavailable, but must not silently become execution-grade evidence.

## Research market-data ladder

For a normal single-stock research report:

1. Alpaca IEX snapshot/quote for current timestamped stock context.
2. Massive adjusted daily/minute history when the account provides the needed history/coverage.
3. Alpaca IEX bars for research history when IEX-only coverage is acceptable.
4. yfinance as an explicitly labelled independent fallback.
5. IBKR only under an exception condition listed above.

For an execution-adjacent or live-radar question, use the Radar Lane instead; do not reinterpret the Research Lane ladder as execution quality.

Run cross-source reconciliation when overlapping packets exist. Compare timestamps and price first; compare volume only after acknowledging venue/feed differences. A fallback packet must preserve attempts, errors, source labels, coverage, and unavailable fields.

## Web and filings

Use company IR, SEC filings, earnings releases, and transcripts for reported facts. Capture URL, published date, access timestamp, period covered, and evidence label. Use web search for current context only when needed, while preserving primary sources for reported company facts.

## MCP decision rule

MCP does not upgrade provider entitlement. Keep REST adapters local when that is enough. IBKR MCP belongs primarily to the Radar Lane and to explicit IBKR research exceptions; it should not be the default dependency of a standalone stock research report.