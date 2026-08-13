# Gamma structure and dealer-hedging interpretation

This module adds a deterministic **gross gamma structure** layer to stock research. It is designed to work on free/low-cost option data without pretending that open interest reveals dealer positioning.

## What the free-tier layer may compute

When a row has a defensible spot, strike, expiry, IV (provider IV or locally inverted IV), and open interest, compute Black-Scholes theoretical gamma:

`Gamma = phi(d1) / (S * sigma * sqrt(T))`

The default zero-rate/zero-dividend convention matches the current lightweight IV inversion. Treat this as a research approximation; dividends, rates, American exercise, stale last prices, and bad spreads can bias the result.

For a 1% move in the underlying, compute the unsigned hedge-sensitivity proxy:

`gross_hedge_shares_1pct = Gamma * OI * 100 * (0.01 * S)`

`gross_gamma_notional_1pct = Gamma * OI * 100 * S^2 * 0.01`

Aggregate by strike and expiry. This answers **where option open interest is most sensitive to spot movement**. It does not answer whether the dealer must buy or sell stock.

## Naming contract

Use these names exactly enough that the evidence level stays clear:

- `OI concentration`: open-interest clustering by strike/expiry.
- `gross gamma concentration`: unsigned OI-weighted theoretical gamma.
- `gamma proximity`: spot distance to a gross-gamma concentration.
- `signed GEX scenario`: an explicit assumption/bounding case, never an observed dealer position unless independently inferred.
- `dealer-flow inference`: only when option trade/quote evidence supports a documented sign model.
- `gamma flip`: unavailable when position sign is not defensible.

Do **not** call a high-OI strike a `Call Wall`/`Put Wall` as an observed support/resistance fact. A strike may be described as an upper/lower gamma concentration, then compared with technical structure and stock-flow evidence.

## Missing-data policy

Missing OI is `null`, not zero. Every gamma summary must show at least:

- eligible option rows;
- rows with usable IV/gamma;
- rows with OI;
- rows with both gamma and OI;
- `gamma_oi_coverage_ratio`;
- whether full-expiry strikes were requested.

Observed sums may be shown with coverage. A complete OI total must remain `null` when any required row is missing OI.

For nightly gamma/OI concentration scans, acquire the full strike set for each selected expiry when the provider permits it. A narrow ATM slice is acceptable for IV diagnostics but can miss distant OI/gamma concentrations.

## Dealer sign and squeeze rules

Open interest does not identify customer/dealer ownership, buyer/seller, or opening/closing direction. Therefore the free-tier layer may show two bounding cases:

- dealer short gamma assumption -> procyclical hedge tendency;
- dealer long gamma assumption -> countercyclical hedge tendency.

Both must be labelled `ASSUMPTION_ONLY`. Do not average them or choose the one that fits the price move.

A gamma squeeze may be described only as `CONDITIONAL_ONLY` unless the evidence also supports dealer sign/flow. At minimum require:

1. spot is approaching a large gross-gamma concentration;
2. dealer sign is independently inferred or explicitly assumed;
3. stock microstructure confirms directional pressure;
4. option and underlying timestamps are sufficiently aligned.

## Nightly stock-report placement

Within `Options-implied risk`, use this order:

1. **Data quality** — source, timestamps, live/delayed/EOD state, quote/OI/gamma coverage, evidence grade.
2. **Implied volatility** — ATM IV, straddle expected move, skew, total-variance term structure.
3. **Gamma structure** — upper/lower concentrations, near-spot gross gamma, distance to concentrations, OI coverage.
4. **Dealer-hedging scenarios** — long-gamma vs short-gamma bounding interpretation, explicitly unsigned/conditional.
5. **Technical + gamma confluence** — compare gamma concentrations with support/resistance, VWAP, intraday volume/activity, and price response. Confluence raises attention; it does not convert the gamma level into confirmed support/resistance.

The options section may change event-risk haircut, timing confidence, and position caps. It must not manufacture directional probability or Kelly edge.

## Intraday reuse

A low-cost intraday mode may freeze previous-close OI/IV and update only spot:

- `oi_as_of = previous close`
- `iv_as_of = previous close/latest defensible snapshot`
- `spot_as_of = live/current`

Recompute theoretical gamma as spot moves and emit `gamma proximity` alerts. Label the map `STATIC_GAMMA_MAP` or equivalent; it is not live dealer-flow monitoring.
