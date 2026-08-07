# Options and volatility module

Use bid/ask mid when both quotes are positive, ordered, and not crossed; otherwise use last only as a fallback and flag it. The local `tws-pro` chain format currently returns last/high/low/volume/bars plus `_ref_price`, but no bid/ask, OI, or Greeks. Treat it as last/aggregate evidence and normalize it with `scripts/normalize_twspro_option_chain.py`; `bars` is not OI or a directional-flow measure. Exclude zero, crossed, stale, or extremely wide markets from primary quote-IV statistics.

For each option, solve Black-Scholes implied volatility numerically from the mid/mark price, or from last only when no valid quote exists and the report labels it `last_iv_model`. Use forward-aware inputs when rates/dividends are available. The ATM straddle approximation is a diagnostic only:

`sigma ≈ straddle / spot × sqrt(pi / (2T))`.

Do not compute OTM IV by multiplying option price by an ATM coefficient. Prefer provider IV or numerical inversion. Use 25-delta put/call when delta exists; otherwise use a documented log-moneyness fallback. Put/call volume and OI are “options activity distribution”, never trader direction without opening/closing and buy/sell data.

Compare expiry curves using total variance `w(T)=sigma(T)^2*T`; derive forward variance only when both expiries are valid and comparable. Flag earnings/event dates, missing Greeks, stale quotes, wide spreads, and low open interest.
