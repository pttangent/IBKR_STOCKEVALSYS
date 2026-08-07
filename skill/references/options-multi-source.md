# Multi-source options protocol

This is the required routing and reconciliation protocol for option-linked stock research. It separates provider capability from evidence quality and prevents a missing field from being treated as a zero.

## Official API references

### IBKR / local IBKR MCP

- [IBKR TWS API documentation](https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/)
- [IBKR requesting market data](https://www.interactivebrokers.com/docs/tws-api/doc/quick-start/requesting-market-data)
- [IBKR market-data subscriptions](https://www.interactivebrokers.com/campus/ibkr-api-page/market-data-subscriptions/)
- [IBKR option-chain parameters and historical bars](https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/)
- Project-local MCP implementation: `../../ibkr-mcp/src/tools/options.py` and `../../ibkr-mcp/src/tools/contracts.py`

The project-local MCP chain tool currently qualifies contracts and requests `1 D` of `5 mins` `TRADES` historical bars for each selected option. Its `last` is the latest historical bar close, not an executable bid/ask quote. Direct `reqMktData`/`reqTickers` is a separate entitlement path.

### Massive / REST

- [Massive Options API overview](https://massive.com/docs/rest/options/overview)
- [Massive all option contracts](https://massive.com/docs/rest/options/contracts/all-contracts)
- [Massive custom aggregate bars](https://massive.com/docs/rest/options/aggregates/custom-bars)
- [Massive option contract snapshot](https://massive.com/docs/rest/options/snapshots/option-contract-snapshot)
- [Massive options pricing and plan matrix](https://massive.com/pricing?product=options)

The free Options Basic plan is a historical/reference route, not a substitute for a live options snapshot. Check the current plan matrix before using snapshot, Greeks, OI, trades, quotes, or second-level fields. Keep the five-calls-per-minute budget in the acquisition audit.

### yfinance / Yahoo research wrapper

- [yfinance Ticker API](https://ranaroussi.github.io/yfinance/reference/api/yfinance.Ticker.html)
- [yfinance `Ticker.option_chain`](https://ranaroussi.github.io/yfinance/reference/api/yfinance.Ticker.html)
- [yfinance `download`](https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html)
- [yfinance documentation and research-use disclaimer](https://ranaroussi.github.io/yfinance/index.html)

yfinance is an unofficial research wrapper around Yahoo's publicly available APIs. Use it for chain discovery/last-trade fields and recent stock bars when needed, but preserve its retrieval time and never present it as an exchange-authoritative quote feed.

## Capability matrix and roles

| Field or task | IBKR MCP | Massive REST | yfinance | Required interpretation |
|---|---|---|---|---|
| Underlying current/recent reference | Historical bar / local TWS context | EOD or plan-dependent | Recent Yahoo quote/history | Prefer IBKR; timestamp every source |
| Expiry/strike directory | `reqSecDefOptParams` | Contracts reference | `Ticker.options` | IBKR/Massive define availability; yfinance is discovery only |
| Option last/high/low/volume | Historical 5-minute bars | Historical aggregates, plan-dependent | Option-chain fields | Compare only aligned sessions and contract keys |
| Bid/ask | Not in local MCP chain tool | Snapshot/quote only on eligible plan | Sometimes present, often stale/zero | Never turn missing/zero into a consensus quote |
| OI/Greeks/provider IV | Not in local MCP chain tool | Snapshot/eligible plan only | Provider fields may be stale | Use only with field-level timestamp/quality |
| Historical IV reconstruction | Limited by returned bar window | Best role: matched option + underlying EOD bars | Not the primary route | Use numerical IV with one formula and matched `S,T` |

## Required acquisition order

1. Create a source manifest with provider, endpoint/tool, request parameters, retrieval time, session date, quote type, and missing fields.
2. Use the project-local IBKR MCP first for the stock contract, option-chain parameters, and selected front/back expiries. Store the raw packet before normalization.
3. Use `scripts/fetch_massive_options.py` for a bounded Massive packet: contract reference + matched underlying daily bars + one call/put pair of historical option daily bars. Respect the plan's call budget; the default is four calls and does not request a snapshot.
4. Use yfinance to add a same-expiry chain view or recent stock history only when it contributes a field not already available. Do not call it a fallback merely because it is cheaper; label it as a complementary source.
5. Run `scripts/reconcile_option_sources.py` on normalized packets before producing IV, skew, term-structure, or Kelly inputs.

## Consensus rules

Consensus is field-specific. It is not a vote over provider names.

### Underlying spot

- Align by exchange session date and currency.
- If two or more sources are within 0.5% and their timestamps are within one trading session, mark `consensus=agree` and use the median.
- If the difference is 0.5%–2%, mark `soft_conflict` and retain the source values.
- Above 2%, or with a stale/pre-market reference, mark `hard_conflict`; use the freshest IBKR value for current-chain calculations and do not hide the disagreement.

### Option last price

- Join on `(underlying, expiry, strike, call_put)`; never compare unlike strikes or unlike expiries.
- Compare only if the observations are from the same session or within one trading session.
- Use `abs(a-b) <= max(0.05, 0.02 * median(a,b))` for `agree`.
- Use 2%–10% relative dispersion as `soft_conflict`; above 10% is `hard_conflict` unless the timestamps clearly show different sessions.
- Use the median only for a consensus diagnostic. Keep each provider's price for IV inversion and auditability.

### IV

- First normalize `S`, `T`, rate/dividend assumptions, option price source, and formula.
- Compare numerical IVs derived from comparable prices. Do not blend provider-reported IV with last-price IV.
- ATM straddle IV is a diagnostic, not a consensus surface.
- If sources disagree, report the range and use the higher defensible risk estimate for a conservative stock-position haircut; do not call the range directional evidence.

### Volume and open interest

- Do not average volume or OI across providers. Definitions, correction policies, and session cutoffs differ.
- Compare only as a coverage/quality check.
- Put/call totals are activity distributions and never identify buyer/seller or opening/closing direction.

## Complement and conflict rules

Use complement when the sources answer different questions:

- IBKR MCP: what the local TWS session recently recorded for the selected option bars.
- Massive: how the same contracts priced historically across matched dates.
- yfinance: an independent chain view, recent Yahoo last/bid/ask/OI/provider fields, or a stock-history bridge.

Use conflict when sources purport to answer the same question but differ after timestamp/session alignment. A source outage is `unavailable`, not a disagreement. A missing field is `not_observed`, not zero.

## Evidence grades for options-linked stock sizing

- `A`: timestamped executable bid/ask plus underlying quote and aligned contract identity.
- `B`: timestamped same-session last/aggregate prices from at least two sources with agreement.
- `C`: one-source historical/last-price model IV, or multi-source data with unresolved soft conflict.
- `D`: contract discovery only, stale/zero fields, or provider data with no trustworthy timestamp.

For Kelly, options can alter the volatility/event-risk haircut. They cannot create directional edge, real-world probabilities, or expected stock return. The report must show the source grade and whether the option input actually affected the final position cap.
