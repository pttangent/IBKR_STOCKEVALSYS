#!/usr/bin/env python3
"""Deterministic scenario-tree scaffolding from current structured evidence.

The tree describes conditional paths; it does not assign orders or manufacture
probabilities. Structured analyst content may enrich/override the generic long-
horizon nodes after the deterministic scaffold is built.
"""
from __future__ import annotations

from typing import Any


def _number(value: Any) -> float | None:
    try:
        x = float(value)
        return x if x == x and abs(x) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _nearest_levels(technical: dict[str, Any]) -> tuple[list[float], list[float]]:
    price = _number(technical.get("last_price"))
    sr = technical.get("support_resistance", {}) or {}
    if price is None:
        return [], []
    supports = sorted({_number(x) for x in sr.get("supports", []) if _number(x) is not None and _number(x) < price}, reverse=True)
    resistances = sorted({_number(x) for x in sr.get("resistances", []) if _number(x) is not None and _number(x) > price})
    return [x for x in supports if x is not None], [x for x in resistances if x is not None]


def _refs(**kwargs: Any) -> dict[str, Any]:
    return {key: value for key, value in kwargs.items() if value is not None}


def _node(node_id: str, label: str, trigger: str, *, watch: list[str] | None = None,
          interpretation: str = "", response: str = "", invalidation: str = "",
          action_boundary: str = "wait / reassess", sizing_tier: str = "none",
          price_reference: dict[str, Any] | None = None, children: list[dict[str, Any]] | None = None,
          probability: float | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": node_id,
        "label": label,
        "trigger": trigger,
        "watch": watch or [],
        "interpretation": interpretation,
        "response": response,
        "invalidation": invalidation,
        "action_boundary": action_boundary,
        "sizing_tier": sizing_tier,
        "price_reference": price_reference or {},
        "children": children or [],
    }
    if probability is not None:
        out["probability"] = probability
    return out


def build_scenario_trees(technical: dict[str, Any], daily_context: dict[str, Any] | None = None,
                         intraday_context: dict[str, Any] | None = None,
                         long_term_context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    daily_context = daily_context or {}
    intraday_context = intraday_context or {}
    long_term_context = long_term_context or {}

    price = _number(technical.get("last_price"))
    ma = technical.get("ma", {}) or {}
    momentum = technical.get("momentum", {}) or {}
    atr = _number(momentum.get("atr14"))
    rv = _number(technical.get("realized_vol_20d_annualized"))
    prior_close = _number(daily_context.get("prior_close"))
    current_reference = _number(intraday_context.get("current_price")) or price
    supports, resistances = _nearest_levels(technical)
    s1 = supports[0] if supports else None
    s2 = supports[1] if len(supports) > 1 else None
    r1 = resistances[0] if resistances else None
    r2 = resistances[1] if len(resistances) > 1 else None
    ema20 = _number(ma.get("ema20"))
    sma50 = _number(ma.get("sma50"))
    sma200 = _number(ma.get("sma200"))
    orh = _number(intraday_context.get("orh"))
    orl = _number(intraday_context.get("orl"))
    vwap = _number(intraday_context.get("vwap"))
    same_session = bool(intraday_context.get("same_session"))
    intraday_status = "same_session" if same_session else "next_session_conditional"

    common_refs = _refs(prior_close=prior_close, current_reference=current_reference, S1=s1, S2=s2, R1=r1, R2=r2,
                        EMA20=ema20, SMA50=sma50, SMA200=sma200, ATR14=atr, RV20=rv, ORH=orh, ORL=orl, VWAP=vwap)

    gap_up = _node(
        "gap_up", "GAP UP / 高開", "Open above prior close; stronger branch if the open also clears R1.",
        watch=["First stable opening range", "Whether the gap level becomes support", "VWAP/ORH once formed", "Volume response"],
        interpretation="A high open is only an initial condition. Acceptance versus fade decides whether the gap carries information.",
        response="Do not chase the first print; classify acceptance or fade after the first stable reaction.",
        invalidation="Gap state changes if price returns through the prior close/held reclaim zone.",
        price_reference=common_refs,
        children=[
            _node(
                "gap_up_accept", "ACCEPTANCE / 衝高延續", "Holds the reclaimed/gap level and then holds or retakes VWAP/ORH after formation.",
                watch=["Retest quality", "Higher low versus opening range", "Whether sell volume expands on retest"],
                interpretation="The market is accepting the higher opening auction rather than immediately rejecting it.",
                response="A confirmed retest can upgrade a tactical long setup; keep the next resistance/ATR distance visible.",
                invalidation="Loss of the held level followed by failed reclaim or ORL breakdown.",
                action_boundary="allow confirmed setup / otherwise wait", sizing_tier="quarter",
                price_reference=_refs(R1=r1, R2=r2, ORH=orh, VWAP=vwap, prior_close=prior_close),
            ),
            _node(
                "gap_up_fade", "FADE / 衝高回落", "Fails to hold the gap/reclaim level and falls back below VWAP or prior close.",
                watch=["Lower highs", "Failed VWAP reclaim", "ORL pressure", "Whether the gap fully closes"],
                interpretation="The higher open was rejected; the gap itself is not bullish evidence.",
                response="Downgrade tactical confidence and reassess at the next support rather than averaging into the fade.",
                invalidation="Price reclaims the failed level and holds it on retest.",
                action_boundary="no chase / reassess", sizing_tier="none",
                price_reference=_refs(prior_close=prior_close, S1=s1, VWAP=vwap, ORL=orl),
            ),
        ],
    )

    flat = _node(
        "near_flat", "NEAR FLAT / 平開", "Open around the prior close / inside the nearby structure zone.",
        watch=["Opening range high/low", "VWAP", "Which side of S1/R1 is accepted", "Range expansion versus RV/ATR"],
        interpretation="A flat open delegates direction to the opening auction; forcing a pre-decided direction has little evidence support.",
        response="Wait for either range acceptance or a clean breakout/reclaim failure.",
        invalidation="Not applicable; this is the neutral root branch.",
        price_reference=common_refs,
        children=[
            _node(
                "flat_up_break", "UPSIDE BREAK / 向上突破", "ORH/reclaim level breaks and then holds on a retest.",
                watch=["ORH retest", "VWAP support", "Distance to R1/R2", "Follow-through volume"],
                interpretation="The opening auction resolved upward after initially neutral positioning.",
                response="Treat as a tactical continuation candidate only after the breakout level holds.",
                invalidation="False break back inside the opening range.",
                action_boundary="allow confirmed setup / otherwise wait", sizing_tier="quarter",
                price_reference=_refs(ORH=orh, VWAP=vwap, R1=r1, R2=r2),
            ),
            _node(
                "flat_range", "RANGE / 區間", "Price remains inside ORH/ORL and repeatedly crosses VWAP.",
                watch=["Range compression", "False breaks", "Volume decay/expansion"],
                interpretation="No side has established acceptance; repeated trades inside the opening range are low-information noise.",
                response="Preserve capital and wait for a close/hold outside the range or a better structural edge.",
                invalidation="Sustained acceptance outside ORH/ORL.",
                action_boundary="wait / no forced direction", sizing_tier="none",
                price_reference=_refs(ORH=orh, ORL=orl, VWAP=vwap),
            ),
            _node(
                "flat_down_break", "DOWNSIDE BREAK / 向下跌破", "ORL/S1 fails and the first recovery attempt cannot reclaim it.",
                watch=["Failed retest", "VWAP rejection", "Distance to S2/ATR band"],
                interpretation="The neutral auction resolved lower and nearby support did not attract durable demand.",
                response="Downgrade long timing; reassess at the next support rather than assuming immediate mean reversion.",
                invalidation="Recovery above the failed level followed by a successful retest.",
                action_boundary="defensive / reassess", sizing_tier="none",
                price_reference=_refs(ORL=orl, S1=s1, S2=s2, VWAP=vwap),
            ),
        ],
    )

    gap_down = _node(
        "gap_down", "GAP DOWN / 低開", "Open below prior close; stronger downside branch if the open also loses S1.",
        watch=["Whether S1 becomes resistance", "VWAP/ORL once formed", "Reversal volume", "Gap fill attempt"],
        interpretation="A low open can either be accepted weakness or an exhaustion/reversal setup. The first reclaim attempt separates them.",
        response="Do not catch the first decline blindly; classify acceptance versus reversal.",
        invalidation="Gap state changes if price reclaims the lost reference zone.",
        price_reference=common_refs,
        children=[
            _node(
                "gap_down_accept", "ACCEPTANCE / 弱勢延續", "Failed retest of S1/prior close/VWAP followed by lower lows or ORL failure.",
                watch=["Failed reclaim", "Lower high", "S2/ATR downside room"],
                interpretation="The market is accepting the lower opening auction and treating the lost support as resistance.",
                response="Keep long exposure defensive; wait for a new base/reclaim rather than averaging down.",
                invalidation="Recovery above the failed level and a successful retest from above.",
                action_boundary="defensive / no new long confirmation", sizing_tier="none",
                price_reference=_refs(S1=s1, S2=s2, prior_close=prior_close, VWAP=vwap, ORL=orl),
            ),
            _node(
                "gap_down_reversal", "REVERSAL / 低開反轉", "Probes support, reclaims S1/VWAP or ORH, then holds the reclaim on retest.",
                watch=["Reclaim level", "Retest volume", "Gap-fill progress", "Distance to R1"],
                interpretation="Initial downside was rejected; this is a tactical reversal candidate, not proof of a long-term trend change.",
                response="A confirmed reclaim can restore a small tactical long setup with a structural invalidation below the reclaimed zone.",
                invalidation="Rejection back below the reclaimed level.",
                action_boundary="allow confirmed reversal setup / otherwise wait", sizing_tier="quarter",
                price_reference=_refs(S1=s1, ORH=orh, VWAP=vwap, R1=r1),
            ),
        ],
    )

    intraday_root = _node(
        "open", "OPEN / 開盤", "Classify the opening auction relative to the prior close and nearest structure.",
        watch=["Overnight material events", "Gap versus ATR/current RV", "First 15-minute opening range", "VWAP after formation"],
        interpretation="The opening state chooses which conditional branch is relevant; it is not itself a directional trade signal.",
        response="Select the observed branch, then wait for its confirmation/invalidation sequence.",
        invalidation="N/A",
        action_boundary="observe -> classify -> confirm", sizing_tier="none",
        price_reference=common_refs,
        children=[gap_up, flat, gap_down],
    )

    short_root = _node(
        "short_term_root", "NEXT DAYS-WEEKS / 短期", "Re-evaluate after each completed session and material catalyst.",
        watch=["Closes versus EMA20/SMA50", "S1/R1 acceptance", "RV compression/expansion", "Catalyst/financing completion"],
        interpretation="Short-term state asks whether the current pullback/reclaim develops into repair, digestion or breakdown.",
        response="Keep short-term exposure conditional on completed-session evidence rather than one intraday print.",
        invalidation="Each child branch has its own invalidation.",
        action_boundary="reassess each completed session", sizing_tier="quarter",
        price_reference=_refs(current=price, EMA20=ema20, SMA50=sma50, S1=s1, R1=r1, ATR14=atr, RV20=rv),
        children=[
            _node(
                "short_repair", "REPAIR / RECLAIM", "Price closes back above the first reclaim level/EMA20 and subsequently holds it.",
                watch=["Follow-through close", "SMA50/R1", "RV normalization", "Catalyst confirmation"],
                interpretation="The pullback is repairing rather than accelerating into a structural breakdown.",
                response="Tactical confidence can improve; do not infer long-term thesis confirmation from price repair alone.",
                invalidation="Close back below the reclaimed level with failed recovery.",
                action_boundary="quarter guidance; half only with stronger validated setup evidence", sizing_tier="quarter",
                price_reference=_refs(EMA20=ema20, SMA50=sma50, R1=r1),
            ),
            _node(
                "short_range", "DIGESTION / RANGE", "Price remains between nearby support/resistance while catalyst information is absorbed.",
                watch=["RV trend", "Range boundaries", "Volume contraction/expansion", "New estimates/news"],
                interpretation="The market is repricing uncertainty without resolving direction.",
                response="Avoid forcing full exposure; use the range to define what would upgrade or invalidate the setup.",
                invalidation="Sustained break and acceptance outside the range.",
                action_boundary="small/quarter guidance or wait", sizing_tier="quarter",
                price_reference=_refs(S1=s1, R1=r1),
            ),
            _node(
                "short_breakdown", "BREAKDOWN / 延續走弱", "S1/medium-term support fails and recovery attempts cannot reclaim it.",
                watch=["Next support", "RV expansion", "Negative catalyst propagation", "Estimate revisions"],
                interpretation="The pullback is becoming a more persistent short-term deterioration.",
                response="Reduce tactical confidence and require a new base/reclaim before restoring sizing.",
                invalidation="Sustained recovery above the failed support with follow-through.",
                action_boundary="reduce / wait", sizing_tier="none",
                price_reference=_refs(S1=s1, S2=s2, SMA50=sma50),
            ),
        ],
    )

    strengthen_trigger = long_term_context.get("strengthen_trigger") or "Core operating KPIs improve and the valuation/capital requirements remain supportable."
    mixed_trigger = long_term_context.get("mixed_trigger") or "Some operating evidence improves, but margins/cash flow/capital intensity/competition offset the progress."
    weaken_trigger = long_term_context.get("weaken_trigger") or "The core operating mechanism fails or required capital/valuation becomes inconsistent with the thesis."
    long_root = _node(
        "long_term_root", "QUARTERS+ / 長期", "Update only when business/valuation evidence changes materially.",
        watch=long_term_context.get("watch", ["Revenue/margin/cash-flow KPI", "Capital intensity/dilution", "Competitive position", "Valuation support"]),
        interpretation="Long-term scenarios are driven by business economics and valuation, not by today's opening range.",
        response="Map new primary evidence into thesis-strengthening, mixed-execution or thesis-weakening branches.",
        invalidation="Use claim-level invalidation from the evidence/claim graph.",
        action_boundary="research posture update", sizing_tier="quarter",
        children=[
            _node("long_strengthen", "THESIS STRENGTHENS / 論點增強", strengthen_trigger,
                  watch=long_term_context.get("strengthen_watch", []),
                  interpretation="Operating evidence is moving toward the thesis while valuation remains defensible.",
                  response="Confidence may increase only after the KPI change is frozen in primary evidence and valuation is refreshed.",
                  invalidation=long_term_context.get("strengthen_invalidation", "Key KPI reverses or valuation/capital assumptions become unsupportable."),
                  action_boundary="re-underwrite; sizing may expand only through the risk module", sizing_tier="quarter"),
            _node("long_mixed", "MIXED EXECUTION / 混合", mixed_trigger,
                  watch=long_term_context.get("mixed_watch", []),
                  interpretation="Progress is real but offset by another economic variable, so a one-dimensional bull/bear label is misleading.",
                  response="Keep scenario weights dispersed and identify the next discriminating KPI.",
                  invalidation=long_term_context.get("mixed_invalidation", "Evidence resolves decisively toward strengthen or weaken branch."),
                  action_boundary="conditional / wait for discriminating evidence", sizing_tier="quarter"),
            _node("long_weaken", "THESIS WEAKENS / 論點轉弱", weaken_trigger,
                  watch=long_term_context.get("weaken_watch", []),
                  interpretation="The economic mechanism or valuation support required by the thesis is deteriorating.",
                  response="Downgrade research state or re-underwrite; do not let a tactical bounce override thesis invalidation.",
                  invalidation=long_term_context.get("weaken_invalidation", "Primary evidence repairs the failed KPI/mechanism and valuation is refreshed."),
                  action_boundary="reduce confidence / possible thesis invalidation", sizing_tier="none"),
        ],
    )

    return [
        {"id": "intraday", "horizon": "intraday", "title": "INTRADAY / 日內情景樹", "evidence_status": intraday_status,
         "opening_range_minutes": 15, "root": intraday_root},
        {"id": "short_term", "horizon": "short_term", "title": "SHORT TERM / 短期情景樹", "evidence_status": "completed_session_structure",
         "root": short_root},
        {"id": "long_term", "horizon": "long_term", "title": "LONG TERM / 長期情景樹", "evidence_status": "requires_fundamental_refresh_on_material_change",
         "root": long_root},
    ]
