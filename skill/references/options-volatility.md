# Options and volatility module

Use bid/ask mid when both quotes are positive, ordered, and not crossed; otherwise use last only as a fallback and flag it. The local `tws-pro` chain format currently returns last/high/low/volume/bars plus `_ref_price`, but no bid/ask, OI, or Greeks. Treat it as last/aggregate evidence and normalize it with `scripts/normalize_twspro_option_chain.py`; `bars` is not OI or a directional-flow measure. Exclude zero, crossed, stale, or extremely wide markets from primary quote-IV statistics.

For each option, solve Black-Scholes implied volatility numerically from the mid/mark price, or from last only when no valid quote exists and the report labels it `last_iv_model`. Use forward-aware inputs when rates/dividends are available. The ATM straddle approximation is a diagnostic only:

`sigma ≈ straddle / spot × sqrt(pi / (2T))`.

Do not compute OTM IV by multiplying option price by an ATM coefficient. Prefer provider IV or numerical inversion. Use 25-delta put/call when delta exists; otherwise use a documented log-moneyness fallback. Put/call volume and OI are “options activity distribution”, never trader direction without opening/closing and buy/sell data.

Compare expiry curves using total variance `w(T)=sigma(T)^2*T`; derive forward variance only when both expiries are valid and comparable. Flag earnings/event dates, missing Greeks, stale quotes, wide spreads, and low open interest.

## Gamma structure

Read [gamma-structure.md](gamma-structure.md) before producing a gamma wall, GEX, dealer-hedging, or squeeze interpretation. The free/low-cost default is **gross gamma structure**, not dealer GEX.

- Compute theoretical gamma locally when spot, strike, DTE, and defensible IV exist.
- Weight by observed OI to estimate unsigned `gross_gamma_notional_per_1pct_spot` and aggregate it by strike/expiry.
- Missing OI stays missing. Report OI and gamma/OI coverage; never silently turn missing OI into zero.
- For nightly concentration analysis, use the full strike set for selected expiries when the provider permits it. A bounded ATM slice can miss important OI/gamma clusters.
- Do not infer dealer sign from call/put labels or OI alone. Any long-gamma/short-gamma result based only on OI is `ASSUMPTION_ONLY`.
- Without a defensible signed dealer-exposure model, `gamma_flip` is unavailable and `gamma squeeze` is `CONDITIONAL_ONLY`.
- Treat upper/lower gamma concentrations as locations of potential hedge sensitivity. They become more actionable only when they align with technical structure and independent stock-flow/microstructure evidence.

Use `scripts/options_gamma_structure.py` on the normalized/provider packet after option-source reconciliation. The output is an audit artifact that belongs inside the options-risk layer; it may modify volatility/event haircuts, timing confidence, and position caps, but it must not create directional probability or Kelly edge.
