# tws-pro options evidence path

When the deferred `tws-pro` MCP tools are available, use this order for a read-only current-chain snapshot:

1. Connect to TWS/IB Gateway and probe capabilities. Confirm the session is the intended paper/read-only session.
2. Resolve the underlying stock contract first and retain its `conId`. In the local `IBKR_MCP` source, `ibkr_get_option_chain_params` is defined with `underlyingConId`, not `symbol`; use the live MCP tool schema if it differs. Select a near expiry and a back expiry from the returned expirations; do not invent an expiry or infer it from a rounded date.
3. Call `ibkr_get_option_chain` once per selected expiry:

```json
{"symbol":"VST","expiration":"20260821","num_strikes":20}
```

Use `num_strikes=20` as the default bounded slice because smaller slices can be empty for some symbols. Keep the raw response, including `expiration`, `strikeCount`, and `_ref_price`.

The current packet shape observed in the local `tws-pro` response is:

```json
{
  "symbol": "VST",
  "expiration": "20260821",
  "chain": [{"strike": 140, "right": "C", "last": 7.2, "high": 7.2,
              "low": 7.2, "volume": 3, "bars": 4}],
  "strikeCount": 20,
  "_ref_price": 141.38
}
```

The local `IBKR_MCP` implementation explains why this path can succeed when direct `reqTickers` fails: `ibkr_get_option_chain` qualifies each option and calls `reqHistoricalDataAsync` for `1 D` of `5 mins` `TRADES` bars, then returns the last historical bar close, high/low, and summed volume. It does not call real-time `reqMktData` for the chain. Therefore a successful response means historical option bars are available; it does not prove live OPRA bid/ask, OI, or Greeks access.

This is not a full quote/Greeks snapshot: the observed packet has last/high/low/volume/bars but no bid, ask, open interest, or Greeks. Normalize it with `scripts/normalize_twspro_option_chain.py`, then run `scripts/options_chain_features.py`. The report must label the resulting IV as either:

- `last_iv_model`: numerical European Black-Scholes inversion from the last trade/last observed price; or
- `atm_straddle_approx_iv`: `straddle / S * sqrt(pi / (2T))`, a quick ATM diagnostic.

Neither is a live market IV unless the input prices are timestamped, executable bid/ask marks. `bars` is an observation-count field, not open interest and not buy/sell direction.

For premarket or a stale chain, `_ref_price` is only the chain provider's reference. Prefer a separately timestamped IBKR underlying quote/close or a Massive daily close for `S`, and record the substitution.

## Two-source options workflow

Use `tws-pro`/IBKR for the current or most recent bounded chain and activity distribution. Use Massive REST for historical contract discovery and daily option OHLC only when the free plan permits the endpoint. Reconstruct historical IV by matching option call/put closes to the underlying close on the same date. A Massive free-tier response without snapshot/Greeks is historical pricing evidence, not a live Greeks feed. Use yfinance only after IBKR and Massive, and mark it as an unofficial fallback.

All conclusions must include the selected expiries, strike window, spot provenance, price source, quote coverage, model formula, and missing fields. Put/call volume and OI ratios describe activity distribution; they do not identify opening buys, closing sells, or trader direction.
