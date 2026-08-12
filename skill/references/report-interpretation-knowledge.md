# Report interpretation knowledge

This reference contains reusable analytical knowledge distilled from audits of real stock-evaluation report packages. It is a set of reasoning lenses, not ticker-specific rules or automatic verdicts. Apply a lens when it is economically material; explain when it changes a conclusion and when it does not.

## 1. Bridge headline accounting to operating economics

A large GAAP profit or loss is not automatically evidence of strong or weak core operations. Before using a headline net-income number in a thesis:

- bridge revenue -> gross profit -> operating income -> non-operating items -> taxes -> net income;
- identify mark-to-market, impairment, restructuring, one-time legal/tax, investment and financing effects;
- compare GAAP and management/non-GAAP reconciliation without treating management adjustments as truth by default;
- ask which components recur, consume cash, change capital needs, or change per-share economics.

The useful question is not merely "was GAAP income large?" but "what economic engine produced the result, what is repeatable, and what still consumes capital?"

## 2. Quantify the actual bottleneck

Avoid vague labels such as "foundry is unprofitable", "margin is weak", or "cash burn is high" when the source permits quantification. Translate the bottleneck into a measurable baseline such as segment operating margin, FCF, capex/revenue, incremental margin, backlog conversion, utilization, yield, or return on invested capital.

A strong report separates observable recovery, the remaining bottleneck, the metric that would demonstrate improvement, and the next event that can falsify the thesis.

## 3. Financing changes equity value, per-share value, and EV differently

For an equity offering, distinguish old shares, new shares, greenshoe/overallotment and diluted share count; offer price, gross proceeds, fees and net proceeds; market capitalization before and after issuance; cash/debt changes; enterprise value after adjusting both equity value and net debt/cash; and per-share dilution versus enterprise-level value creation/destruction.

Do not add new equity market cap to old net debt and call the result a coherent pro-forma EV unless the cash proceeds are also reconciled. An equity raise can dilute each share while leaving enterprise value roughly unchanged at issuance if cash is retained.

## 4. Kelly is setup-specific, not ticker-specific

A win rate and payoff ratio are portable only to the setup that generated them. Match the economically relevant entry condition, exit rule, horizon, transaction cost, liquidity class and regime. A mean-reversion RSI backtest is not evidence for a breakout/reclaim setup merely because both trade the same stock.

When setup identity does not match, the useful interpretation is "not applicable to this setup", not simply "low confidence". A diagnostic Kelly number may still be displayed for research, but it must not masquerade as sizing evidence for a different setup.

## 5. Position size is determined by the binding constraint

Compute candidate sizes independently for fixed-risk/stop distance, concentration, liquidity/capacity, event/tail risk, and qualified Kelly. The applied size is the minimum eligible constraint after respecting hard portfolio limits. Report the binding constraint and recompute stop/target dollar P/L on the applied quantity, not on a larger pre-cap diagnostic quantity.

## 6. Cross-source agreement is field-specific

Two providers can agree on OHLC and disagree materially on volume, adjustment rules, timestamps, corporate actions, session filters or trade-count methodology. Reconciliation should state which fields agree and which do not. "Provider B agrees with Provider A" is too strong when only prices match.

A discrepancy is data-quality evidence. Investigate methodology before turning it into a market signal.

## 7. Empty data is an acquisition diagnosis before it is a market conclusion

An empty intraday/tick/options response can result from entitlement, pacing, request window, future cursor, timezone, market-hours boundary, contract qualification or provider retention. Inspect the actual request and error payload before concluding that the market had no activity or the capability is unavailable.

For historical intraday requests, prefer completed-session boundaries when the requested end time lies in the future relative to runtime.

## 8. IV plausibility matters before Gamma

Gamma is highly sensitive to IV, DTE, spot and strike. A syntactically positive provider IV can still be economically nonsensical because of stale/placeholder values or bad quote context. Before using provider IV in Gamma, sanity-check magnitude and surface continuity, prefer valid timestamped bid/ask-derived IV over stale last-price or placeholder IV, compare provider IV with an independent price inversion when feasible, and downgrade or suppress Gamma when IV quality is not defensible.

Open-interest quality remains a separate issue: reliable IV does not repair missing/untrusted OI, and OI does not identify dealer sign.

## 9. Preserve exact event chronology for PIT research

An announcement, upsizing, pricing and closing can be separate events on different timestamps. Record exact publication/availability timestamps when material. Date-only cutoffs are insufficient for same-day historical replay because later filings or press releases can leak into an earlier research state.

## 10. Keep artifact states semantically consistent

If the structured module says `NEEDS_EVIDENCE` while prose says "complete", explain the distinction or reconcile the state. Machine-readable and reader-facing outputs should describe the same research state, confidence and missing evidence.

## 11. Separate observation from interpretation

For each consequential judgment, preserve what was observed, the analytical interpretation, why that interpretation matters economically, what evidence could overturn it, and what cannot be inferred from the available data.

This is especially useful below charts. A chart without interpretation forces the reader to reverse-engineer the analyst's logic; an interpretation without limitations invites overconfidence.

## 12. Use knowledge notes to teach, not decorate

Reader-facing reports should explain important concepts when they are central to the decision: accounting bridges, EV mechanics, volatility/variance, Gamma, setup-specific Kelly, binding risk caps, relative strength, or evidence quality. Keep explanations adjacent to the relevant chart or judgment and tie them to the current evidence rather than adding generic textbook paragraphs.
