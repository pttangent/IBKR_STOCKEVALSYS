# Multi-horizon scenario-tree reasoning

Use this reference whenever the report contains scenario analysis. Scenarios are not a flat bull/base/bear list. They are a conditional decision tree that tells the reader what evidence appears next, how price may react, and what should change in the interpretation.

## 1. Always separate three horizons

A full stock report should carry three different scenario layers unless the request is explicitly narrower:

1. **Intraday / next session** — pre-market observations, the opening state, first reaction, VWAP/opening-range behavior, and no-trade branches.
2. **Short term** — roughly the next several sessions to several weeks: reclaim, range repair, continuation, breakdown, catalyst digestion and estimate/positioning changes.
3. **Long term** — quarters and beyond: operating thesis confirmation, valuation rerating/derating, capital intensity, competitive structure and thesis invalidation.

Do not let one horizon impersonate another. A strong long-term thesis can coexist with a failed gap-up today. A bullish opening-range breakout does not prove the long-term fundamental thesis.

## 2. Intraday tree starts before the open

The pre-market section should answer:

- What changed overnight: filing, earnings, guidance, financing, analyst/news catalyst, macro release?
- Where is the reference price versus prior close, nearest support/resistance, important moving averages and option-implied move when defensible?
- Is the gap large or small relative to ATR/current RV?
- Is pre-market volume/activity unusual, if the feed supports it?
- Which data are stale, delayed or unavailable?
- Which price levels would materially change the interpretation after the open?

If there is no same-session quote yet, call this a `next-session conditional tree`, not a confirmed `today` signal.

## 3. Minimum opening tree

Every intraday tree should contain the equivalent of these branches. Use actual current levels when available and generic conditions when they are not.

```text
OPEN / 開盤
├─ GAP UP / 高開
│  ├─ ACCEPTANCE / 衝高延續
│  │  └─ holds R1 / ORH / VWAP -> wait for retest/hold -> continuation candidate
│  └─ FADE / 衝高回落
│     └─ loses R1 / prior close / VWAP -> do not chase -> downgrade or no-trade
├─ NEAR FLAT / 平開
│  ├─ UPSIDE BREAK -> ORH/reclaim holds -> continuation candidate
│  ├─ RANGE -> stays inside ORH/ORL -> no forced direction
│  └─ DOWNSIDE BREAK -> ORL/S1 fails -> defensive branch
└─ GAP DOWN / 低開
   ├─ ACCEPTANCE / 弱勢延續
   │  └─ failed retest of S1/VWAP -> downside remains accepted
   └─ REVERSAL / 低開反轉
      └─ reclaims S1/VWAP/ORH + retest -> reversal candidate
```

The tree is a map of **conditional responses**, not a prediction that every branch is equally likely.

## 4. Every node needs an observable trigger and a response

A scenario node should contain:

- `label`: human-readable branch name;
- `trigger`: observable condition that enters the branch;
- `price_reference`: concrete level(s) when available;
- `watch`: what to observe next;
- `interpretation`: what the branch means economically/technically;
- `response`: how the research posture changes if it occurs;
- `invalidation`: what exits the branch;
- `action_boundary`: wait / reassess / reduce confidence / allow a setup / no-trade; never an automatic order;
- optional `sizing_tier`: which risk tier can be considered (`none`, `quarter`, `half`, or `full_diagnostic`) after the branch is actually confirmed;
- optional `probability` only when the probability is defensible from stated evidence.

A useful tree should let the reader answer “price did X — what do I look at next?” without returning to a prose paragraph.

## 5. Use price zones, not magical points

When the deterministic engine provides current price, nearest support/resistance, EMA20/SMA50/SMA200, ATR, VWAP, ORH/ORL or option-implied move, carry them into the relevant nodes.

Examples:

- gap-up above R1 but below the next resistance: first ask whether R1 becomes support;
- open above a reclaim level but immediate loss of VWAP: the gap-up branch is not accepted;
- gap-down into S1/S2 followed by VWAP reclaim and retest: treat as a reversal candidate, not proof of a new long-term uptrend.

Do not invent ORH/ORL or VWAP before the corresponding same-session bars exist. Before the open, label them as values to be formed after the declared opening-range window.

## 6. Short-term tree

A useful short-term tree normally contains at least:

- **repair/reclaim**: price reclaims the first medium-term level and holds it on subsequent sessions;
- **range/digestion**: price remains between nearby support/resistance while RV compresses or the catalyst is absorbed;
- **continuation/breakdown**: support fails or the adverse catalyst continues to propagate.

Tie each branch to observable evidence such as closes relative to EMA20/SMA50, support/resistance, realized-volatility change, estimate revisions, financing/catalyst completion, or other frozen evidence. Avoid replacing this with arbitrary percentage targets.

## 7. Long-term tree

Long-term scenarios should be driven primarily by business and valuation variables, not by the same intraday levels. A generic structure is:

- **thesis strengthens**: key operating KPI, margin/cash-flow/capacity/market-share evidence moves in the expected direction and valuation remains supportable;
- **mixed execution**: some product/revenue evidence improves but capital intensity, margins, dilution, competition or valuation offset it;
- **thesis weakens / invalidates**: the core operating mechanism fails, required capital rises faster than expected, or valuation cannot be supported by the updated economics.

Populate the exact KPI and invalidation from the company's evidence packet. Do not hard-code another ticker's thresholds.

## 8. Position context for the tree

The default report simulation account is **$10,000** unless the user supplies another portfolio value. Scenario nodes may reference the current Kelly/risk tier, but a branch confirmation does not itself generate an order.

A typical presentation is:

- unconfirmed / contradictory branch -> `sizing_tier=none`;
- acceptable but low-confidence setup -> `quarter` guidance may be considered;
- validated same-setup confirmation with adequate risk evidence -> `half` may be shown as an additional candidate;
- `full` remains a theoretical/diagnostic upper bound unless the strategy's explicit governance says otherwise.

The actual dollar notional and shares come from the risk module after current RV, stop risk, concentration and other caps are applied.

## 9. HTML contract

Render the intraday/short-term/long-term trees as visible branching maps, not only tables. Each node should expose its trigger and next response on hover/click or directly inside the node. Price references and sizing tier should be visually distinct. The tree should remain readable on mobile by stacking branches vertically.
