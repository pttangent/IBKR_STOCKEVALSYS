# IBKR Realtime Radar + Executed Order Flow

This module implements the **Radar Lane** described by the repository's dual-lane architecture. It is deliberately separate from the Research Lane: IBKR market-data lines are treated as scarce live resources and are not used as the generic historical/fundamental warehouse.

## Modes

### 1. `radar` — broad watchlist via `reqMktData`

Use when the watchlist is larger than the tick-by-tick allocation (for example 10–100 stocks on a default 100-line account).

Inputs:

- `reqMktData()` top-of-book snapshots
- generic ticks `233,293,294,295,375` when available (RTVolume / trade count / trade rate / volume rate / RTTradeVolume)
- bid / ask / sizes / last / cumulative volume

Outputs include price/spread, quote imbalance, trade/volume activity, large-print proxy, executed-flow proxy, absorption/exhaustion proxy, candidate price levels, and a **proxy footprint** when RTVolume-style events are available.

Governance label: `MKTDATA_SNAPSHOT_PROXY`.

This mode must **not** be presented as complete Time & Sales.

### 2. `flow` — targeted true trade ticks

Default flow configuration uses `reqMktData()` for top-of-book and `reqTickByTickData(..., "AllLast")` for true trade prints. This consumes **one tick-by-tick request per stock**, so a default account with 100 market-data lines (5% tick-by-tick allocation = 5 requests) can target five stocks.

Governance label: `TBT_TRADES_MKTDATA_QUOTES`.

This is the recommended five-stock configuration. Trade prints are true tick-by-tick, while aggressor classification uses the most recent `reqMktData` quote plus tick-rule fallback.

### 3. `flow --flow-quote-source tick` — fully tick-enriched

Uses `AllLast` tick-by-tick trades plus `BidAsk` tick-by-tick quotes. That costs **two tick-by-tick requests per stock**. With five default slots, only two fully enriched stocks fit while preserving one spare request.

Governance label: `TBT_TRADES_TBT_QUOTES`.

## Why five stocks is not always five full tick streams

IBKR caps simultaneous tick-by-tick subscriptions at 5% of total market-data lines. A tick type is requested separately. Therefore:

- 5 symbols × `AllLast` = 5 TBT requests → fits default allocation.
- 2 symbols × (`AllLast` + `BidAsk`) = 4 TBT requests → fits.
- 5 symbols × (`AllLast` + `BidAsk`) = 10 TBT requests → **does not fit** default allocation.

The planner makes this explicit and refuses to start a flow plan that exceeds the configured TBT allocation.

## Signals

The engine computes observable/inferred microstructure states rather than directional predictions: aggressor buy/sell volume (classified), 60-second delta, 30-minute CVD, trade/volume activity, quote imbalance, robust large-trade score, 15-second bid/offer absorption, buyer/seller exhaustion, 30-second price response, price-level footprint, and high-volume price-level candidates.

`BID ABSORPTION` means aggressive selling was observed while downside price progress remained small. It does **not** prove the identity of a hidden buyer. `OFFER ABSORPTION` is the symmetric condition for aggressive buying meeting supply.

## What L1 cannot do

Without L2 market depth this module does not label multi-level resting liquidity walls, cancellation/pull of deeper book liquidity, queue position, full-depth order-book imbalance, or spoofing based on displayed depth. Those belong in a future `reqMktDepth()` extension.

## Run

From `ibkr-mcp/`:

```bash
# Auto: five symbols -> flow mode on a default 100-line allocation
uv run python run_radar.py --symbols TER KLAC AEHR COHU FORM --mode auto

# Broad radar
uv run python run_radar.py --symbols AAPL MSFT NVDA AMD AVGO MU TER KLAC LRCX AMAT ONTO COHU FORM AEHR PDFS --mode radar

# Two fully tick-enriched symbols
uv run python run_radar.py --symbols TER KLAC --mode flow --flow-quote-source tick
```

Paper TWS defaults to port `7497`. Live TWS commonly uses `7496`; pass it explicitly rather than silently switching environments.

Dashboard: `http://127.0.0.1:8765/radar`

The radar uses a dedicated read-only client id (`4711` by default) so the existing MCP/account workflow does not have to share the same client state.

## HTTP API

- `GET /api/v1/radar/plan`
- `GET /api/v1/radar/health`
- `GET /api/v1/radar/snapshot`
- `GET /api/v1/radar/snapshot?symbol=TER`
- `GET /api/v1/radar/alerts`
- `POST /api/v1/radar/control` with `{"action":"pause"|"resume"|"stop"}`
- `POST /api/v1/radar/config` while stopped

## Storage

The service writes an append-only SQLite replay/audit database at `ibkr-mcp/data/realtime_radar.sqlite3`. Override with `IBKR_RADAR_DB` or `--db`. The storage thread is decoupled from market-data ingestion so disk I/O does not block the polling/event loop.

## UI

The UI intentionally reuses the repository's individual-stock HTML report language: black background, mono typography, thin grid borders, green/red/amber/cyan semantic colors, no decorative dashboard gradients/cards, and explicit data-quality/governance labels.
