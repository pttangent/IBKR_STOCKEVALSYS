# Risk and positioning module

Read [kelly-positioning-knowledge.md](kelly-positioning-knowledge.md) before turning an edge estimate into a position guide.

Default to fixed fractional risk for stop-based sizing: `shares = portfolio_value * risk_budget_pct / abs(entry - stop)`, then cap notional by concentration and any applicable Kelly/liquidity constraints. Prefer structure or ATR-informed stops; if no stop is supplied, do not invent one. The absence of a stop does **not** require the Kelly/RV section to disappear: full/half/quarter Kelly can still be translated into NAV, dollar notional, shares and one-day one-sigma risk, while the stop-risk cap is explicitly unavailable.

## Default simulation account

When the user does not supply an account size, every reader-facing report uses a clearly labeled **$10,000 simulation account**. This is a presentation/risk-normalization convention, not an assumption about the user's actual capital. A user-supplied portfolio value overrides it.

## Kelly output contract

Kelly is conditional, not automatic. Estimate edge from the declared setup's trade outcomes and expose both:

- empirical log-growth Kelly over the observed return distribution;
- transparent `p/b` formula Kelly, where `f_raw = (p*b - (1-p)) / b`.

When both are positive and describe the same evidence tier, a conservative guide may use the smaller positive estimate. Record setup identity and setup-match status. A daily RSI mean-reversion backtest is not interchangeable with an EMA reclaim, ORB, post-event gap or other setup.

Always display the available chain even when standard validation is missing:

- total/OOS trade count and sample tier;
- `p`, `b`, average win/loss;
- full-sample and OOS empirical Kelly where available;
- full-sample and OOS formula Kelly;
- selected base edge and source;
- current RV, reference RV, daily sigma and RV-regime haircut when defensible;
- option/event haircut when defensible;
- **full Kelly**, **half Kelly**, **quarter Kelly**;
- post-overlay fraction and final fraction after concentration/stop/liquidity caps;
- binding constraint for every variant;
- $10k notional, shares, one-day one-sigma NAV/$ risk and stop-loss dollars when a stop exists;
- `guidance_status`, `guidance_variant`, `guidance_fraction` and qualification/setup-match status.

Full Kelly is the most estimation-error-sensitive theoretical fraction. Half and quarter are robustness variants; quarter is the conservative reader-facing guide by default unless an explicitly validated strategy governance selects another tier. Full must remain visible even when it is not actionable.

## Give a guide unless the gap is severe

Do not turn insufficient standard OOS into a blank report section.

- same-setup validated OOS -> validated ladder;
- conditional OOS -> conditional ladder;
- small but valid trade log -> exploratory ladder;
- setup mismatch/unknown -> proxy ladder with the mismatch prominently disclosed;
- no positive Kelly edge but valid entry/stop -> fixed-risk/concentration **risk-only fallback**;
- abstain from a numeric guide only when neither a positive edge diagnostic nor a defensible risk-only cap can be computed.

A cap is not automatically a recommended target. For example, a 5% concentration cap says the position may not exceed 5%; it does not prove 5% is appropriate.

## Current volatility

Current realized volatility changes the risk footprint, not the directional edge. With annualized `RV_current`:

```text
daily_sigma = RV_current / sqrt(252)
NAV_1sigma  ≈ position_fraction * daily_sigma
```

When enough prior rolling history exists, the engine may use a PIT reference median and a no-upsize overlay `h_RV = min(1, RV_reference / RV_current)`. This shrinks exposure in an unusually high-volatility regime but never increases Kelly merely because current RV is low.

Options may supply a volatility/event haircut, but they do not create `p`, expected return or dealer direction. Avoid multiplying overlapping volatility penalties blindly; disclose the combination policy.

For scenarios, keep sizing conditional on observable evidence. Intraday, short-term and long-term scenario trees are defined in [scenario-tree-reasoning.md](scenario-tree-reasoning.md). The engine does not issue an order or a BUY/HOLD/SELL label.
