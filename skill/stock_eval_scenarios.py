#!/usr/bin/env python3
"""Evidence-anchored multi-horizon scenario-tree construction.

The intraday tree is composed from observable price-event primitives rather than
from a fixed gap-up/flat/gap-down template. Every numeric price shown in a node
is carried as an anchor with provenance. Prior close may remain contextual
metadata, but it is never the primary structural trigger when deterministic
support/resistance or same-session levels exist.
"""
from __future__ import annotations

from typing import Any


def _number(value: Any) -> float | None:
    try:
        x = float(value)
        return x if x == x and abs(x) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _anchor(anchor_id: str, label: str, value: Any, *, role: str, source: str,
            method: str, confidence: str = "medium", status: str = "observed") -> dict[str, Any] | None:
    price = _number(value)
    if price is None or price <= 0:
        return None
    return {
        "id": anchor_id, "label": label, "value": price, "role": role,
        "source": source, "method": method, "confidence": confidence, "status": status,
    }


def _unique_anchors(items: list[dict[str, Any] | None], tolerance: float = 0.0015) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items:
        if not item:
            continue
        if any(abs(item["value"] / old["value"] - 1) <= tolerance for old in out if old["value"]):
            continue
        out.append(item)
    return out


def _build_anchor_book(technical: dict[str, Any], intraday_context: dict[str, Any]) -> dict[str, Any]:
    price = _number(intraday_context.get("current_price")) or _number(technical.get("last_price"))
    same_session = bool(intraday_context.get("same_session"))
    sr = technical.get("support_resistance", {}) or {}
    ma = technical.get("ma", {}) or {}
    momentum = technical.get("momentum", {}) or {}
    bb = momentum.get("bollinger", {}) or {}
    atr = _number(momentum.get("atr14"))

    supports = sorted({_number(x) for x in sr.get("supports", []) if _number(x) is not None and (price is None or _number(x) < price)}, reverse=True)
    resistances = sorted({_number(x) for x in sr.get("resistances", []) if _number(x) is not None and (price is None or _number(x) > price)})
    lower: list[dict[str, Any] | None] = []
    upper: list[dict[str, Any] | None] = []
    dynamic: list[dict[str, Any] | None] = []
    volatility: list[dict[str, Any] | None] = []

    for index, value in enumerate(supports[:4]):
        lower.append(_anchor(
            f"S{index + 1}", f"支撐 S{index + 1}", value, role="support",
            source=f"stock_eval.json:technical.support_resistance.supports[{index}]",
            method="deterministic support candidate from swing/Fibonacci support bundle",
            confidence="medium"))
    for index, value in enumerate(resistances[:4]):
        upper.append(_anchor(
            f"R{index + 1}", f"壓力 R{index + 1}", value, role="resistance",
            source=f"stock_eval.json:technical.support_resistance.resistances[{index}]",
            method="deterministic resistance candidate from swing/Fibonacci resistance bundle",
            confidence="medium"))

    for key, label in (("ema20", "EMA20"), ("sma50", "SMA50"), ("sma200", "SMA200")):
        value = _number(ma.get(key))
        if value is not None:
            dynamic.append(_anchor(
                key.upper(), label, value, role="moving_average",
                source=f"stock_eval.json:technical.ma.{key}",
                method=f"deterministic {label} from completed daily bars", confidence="medium"))

    if same_session:
        dynamic.extend([
            _anchor("VWAP", "當日 VWAP", intraday_context.get("vwap"), role="intraday",
                    source=f"{intraday_context.get('source_artifact', 'intraday')}:same-session-bars",
                    method="same-session volume-weighted average price", confidence="high"),
            _anchor("ORH", "15 分鐘開盤區間高點", intraday_context.get("orh"), role="intraday_resistance",
                    source=f"{intraday_context.get('source_artifact', 'intraday')}:first-15m",
                    method="first 15 one-minute bars high", confidence="high"),
            _anchor("ORL", "15 分鐘開盤區間低點", intraday_context.get("orl"), role="intraday_support",
                    source=f"{intraday_context.get('source_artifact', 'intraday')}:first-15m",
                    method="first 15 one-minute bars low", confidence="high"),
        ])

    volume_nodes = technical.get("close_weighted_volume_nodes", []) or []
    if price is not None:
        nearest_nodes = sorted(
            [row for row in volume_nodes if _number(row.get("mid")) is not None],
            key=lambda row: abs(_number(row.get("mid")) - price))[:3]
        for index, row in enumerate(nearest_nodes):
            value = _number(row.get("mid"))
            role = "volume_node_support" if value < price else "volume_node_resistance"
            target = lower if value < price else upper
            target.append(_anchor(
                f"VOLNODE{index + 1}", f"成交量節點 {index + 1}", value, role=role,
                source=f"stock_eval.json:technical.close_weighted_volume_nodes[{index}]",
                method="daily close-weighted volume node; not a true intraday volume profile",
                confidence="low"))

    if price is not None and atr:
        volatility.extend([
            _anchor("ATR_UP", "+1 ATR", price + atr, role="volatility",
                    source="stock_eval.json:technical.momentum.atr14",
                    method="reference price + ATR14; volatility room, not resistance", confidence="medium"),
            _anchor("ATR_DN", "-1 ATR", max(0.01, price - atr), role="volatility",
                    source="stock_eval.json:technical.momentum.atr14",
                    method="reference price - ATR14; volatility room, not support", confidence="medium"),
        ])
    volatility.extend([
        _anchor("BB_UP", "布林上軌", bb.get("upper"), role="volatility",
                source="stock_eval.json:technical.momentum.bollinger.upper", method="20D mean + 2σ", confidence="low"),
        _anchor("BB_DN", "布林下軌", bb.get("lower"), role="volatility",
                source="stock_eval.json:technical.momentum.bollinger.lower", method="20D mean - 2σ", confidence="low"),
    ])

    current = _anchor(
        "CURRENT", "當前/最近有效價格", price, role="current",
        source=(f"{intraday_context.get('source_artifact')}:latest" if same_session else "stock_eval.json:technical.last_price"),
        method=("same-session latest intraday close" if same_session else "latest completed daily close used only as reference"),
        confidence=("high" if same_session else "medium"),
        status=("same_session" if same_session else "reference_only"))

    lower_clean = _unique_anchors(lower)
    upper_clean = _unique_anchors(upper)
    dynamic_clean = _unique_anchors(dynamic)
    volatility_clean = _unique_anchors(volatility)
    return {
        "current": current, "supports": lower_clean, "resistances": upper_clean,
        "dynamic": dynamic_clean, "volatility": volatility_clean,
        "all": [x for x in ([current] if current else []) + lower_clean + upper_clean + dynamic_clean + volatility_clean if x],
        "same_session": same_session,
    }


def _find(book: dict[str, Any], anchor_id: str) -> dict[str, Any] | None:
    return next((item for item in book.get("all", []) if item.get("id") == anchor_id), None)


def _first(book: dict[str, Any], group: str, index: int = 0) -> dict[str, Any] | None:
    rows = book.get(group, []) or []
    return rows[index] if len(rows) > index else None


def _dynamic_near(book: dict[str, Any], preferred: tuple[str, ...]) -> dict[str, Any] | None:
    for anchor_id in preferred:
        item = _find(book, anchor_id)
        if item:
            return item
    return None


def _node(node_id: str, label: str, trigger: str, *, watch: list[str] | None = None,
          interpretation: str = "", response: str = "", invalidation: str = "",
          action_boundary: str = "等待 / 重新評估", sizing_tier: str = "none",
          anchors: list[dict[str, Any] | None] | None = None,
          children: list[dict[str, Any]] | None = None,
          probability: float | None = None) -> dict[str, Any]:
    price_anchors = [item for item in (anchors or []) if item]
    out: dict[str, Any] = {
        "id": node_id, "label": label, "trigger": trigger, "watch": watch or [],
        "interpretation": interpretation, "response": response, "invalidation": invalidation,
        "action_boundary": action_boundary, "sizing_tier": sizing_tier,
        "price_reference": {item["id"]: item["value"] for item in price_anchors},
        "price_anchors": price_anchors, "children": children or [],
    }
    if probability is not None:
        out["probability"] = probability
    return out


def _intraday_tree(book: dict[str, Any]) -> dict[str, Any]:
    s1, s2 = _first(book, "supports", 0), _first(book, "supports", 1)
    r1, r2 = _first(book, "resistances", 0), _first(book, "resistances", 1)
    vwap, orh, orl = _find(book, "VWAP"), _find(book, "ORH"), _find(book, "ORL")
    mid = _dynamic_near(book, ("VWAP", "EMA20", "SMA50"))
    atr_up, atr_dn = _find(book, "ATR_UP"), _find(book, "ATR_DN")
    same_session = bool(book.get("same_session"))
    upper_test = orh or r1 or _dynamic_near(book, ("EMA20", "SMA50")) or atr_up
    upper_next = r2 or atr_up
    lower_test = orl or s1 or _dynamic_near(book, ("EMA20", "SMA50")) or atr_dn
    lower_next = s2 or atr_dn

    up_break_hold = _node(
        "up_break_retest_hold", "突破後回踩不破 → 再攻",
        "價格有效站上第一上方結構錨點後，第一次回踩沒有跌回其下方；若 VWAP/ORH 已形成，回踩同時守住至少一個當日動態錨點。",
        watch=["回踩量能是否縮減", "是否形成更高低點", "再次上攻時量能是否重新擴張", "距離下一壓力與 ATR 空間"],
        interpretation="這是比『單純衝高』更高品質的接受訊號：市場先突破，再用回踩證明上方價格被接受。",
        response="可以把戰術判斷從『等待突破』升級為『確認後的延續候選』，但先看下一壓力是否留下足夠報酬空間。",
        invalidation="回踩收回突破錨點下方，並且下一次反彈無法重新站回；若同時跌破 VWAP/ORH，視為假突破風險升高。",
        action_boundary="確認回踩守住後才允許小倉位；未確認不追價", sizing_tier="quarter",
        anchors=[upper_test, mid, upper_next, atr_up],
        children=[
            _node("up_reaccelerate", "二次放量突破 → 延續",
                  "回踩守住後再次突破前高/ORH，並朝下一個已計算壓力區推進。",
                  watch=["突破量能", "前高是否轉為支撐", "下一壓力前的盈虧比"],
                  interpretation="價格完成『突破—回踩—再突破』三段確認，延續品質高於直接追第一根長陽。",
                  response="若 setup/樣本也匹配，可在風險模組允許的範圍內考慮由 quarter 升至 half；不是自動加倉。",
                  invalidation="再突破後快速跌回前高與回踩錨點下方。",
                  action_boundary="只有歷史 setup 驗證與風險空間同時成立才考慮提高層級", sizing_tier="half",
                  anchors=[upper_test, upper_next, orh, atr_up]),
            _node("up_hold_but_stall", "回踩守住但無法再攻 → 高位整理",
                  "回踩沒有破壞結構，但多次上攻仍無法突破前高/下一壓力。",
                  watch=["高位成交量是否萎縮", "VWAP 是否仍在下方提供支撐", "壓力附近是否連續出現上影/賣壓"],
                  interpretation="多頭結構尚未失效，但動能不足；『守住』不等於『必然再漲』。",
                  response="維持小倉位/等待，不因盤整自行升級 Kelly 層級。",
                  invalidation="跌破回踩錨點或向上真正突破下一壓力。",
                  action_boundary="等待下一次方向確認", sizing_tier="quarter",
                  anchors=[upper_test, mid, upper_next]),
        ])

    up_break_fail = _node(
        "up_break_retest_fail", "突破後回踩失守 → 假突破",
        "價格曾站上第一上方結構錨點，但回踩直接跌回其下方，且反抽無法重新站回。",
        watch=["VWAP 是否同步失守", "反抽是否形成更低高點", "下方第一支撐是否快速被測試"],
        interpretation="突破沒有被市場接受；比單純『衝高回落』更明確，因為失敗發生在可驗證的結構錨點上。",
        response="取消追價邏輯，轉為觀察中軸/VWAP或第一支撐是否止跌。",
        invalidation="重新站回突破錨點，並完成一次從上方的有效回踩。",
        action_boundary="不追；等待重新收復或下一支撐出現新的 setup", sizing_tier="none",
        anchors=[upper_test, mid, s1, lower_test],
        children=[
            _node("up_fail_mid_hold", "假突破後守住中軸 → 二次嘗試",
                  "雖失守突破位，但在 VWAP/EMA20/第一支撐附近止跌，並重新形成更高低點。",
                  watch=["中軸附近成交量", "再次測試上方錨點時是否更乾淨", "是否形成窄幅壓縮"],
                  interpretation="第一次突破失敗，但沒有演變成全面走弱；市場仍可能進入第二次突破準備。",
                  response="保持等待；只有重新突破並回踩確認才恢復 quarter 層級。",
                  invalidation="中軸與第一支撐一起失守。", action_boundary="等待二次突破確認", sizing_tier="none",
                  anchors=[mid, s1, upper_test]),
            _node("up_fail_deep", "假突破 + 中軸失守 → 回撤擴大",
                  "突破失敗後進一步跌破 VWAP/EMA20 或第一支撐，反抽仍被壓回。",
                  watch=["下一支撐 S2", "-1 ATR 波動空間", "賣出量是否擴張"],
                  interpretation="上方失敗已由局部假突破擴散為更深回撤，原本的多頭日內 setup 失效。",
                  response="轉為防守，只在下一個有證據支持的支撐重新評估。",
                  invalidation="重新收復中軸和第一支撐並保持。", action_boundary="觀望 / 降低暴露", sizing_tier="none",
                  anchors=[mid, s1, s2, atr_dn]),
        ])

    up_reject = _node(
        "up_test_reject", "衝高但未突破壓力 → 回落",
        "價格向上測試第一上方結構錨點，但未能有效站上，出現明顯拒絕。",
        watch=["回落是否守住 VWAP/EMA20", "回撤量能", "是否形成更高低點再次測試壓力"],
        interpretation="壓力位仍有效；這與『突破後回踩』不同，因為市場從未真正接受壓力上方價格。",
        response="不追高；看回落是淺回踩還是轉成更深的拒絕。",
        invalidation="真正站上壓力並完成回踩確認。", action_boundary="等待回踩結果", sizing_tier="none",
        anchors=[upper_test, mid, s1],
        children=[
            _node("up_reject_shallow_hold", "回踩中軸/支撐不破 → 二次攻壓力",
                  "衝高受阻後只回踩至 VWAP/EMA20/第一支撐附近便止跌，且低點沒有破壞。",
                  watch=["回踩是否縮量", "二次上攻是否放量", "壓力被測試次數"],
                  interpretation="賣壓仍在，但回撤被較高位置吸收；若再次突破，品質通常高於第一次直接衝擊。",
                  response="把下一步聚焦在『二次突破 + 回踩』，而不是在支撐上直接假設必漲。",
                  invalidation="中軸/第一支撐失守。", action_boundary="二次突破前等待；確認後才考慮 quarter", sizing_tier="none",
                  anchors=[upper_test, mid, s1]),
            _node("up_reject_deep", "回踩失守 → 壓力拒絕確認",
                  "衝高受阻後連中軸/第一支撐也失守，反抽無法收復。",
                  watch=["下一支撐", "ORL（若已形成）", "賣出量是否擴張"],
                  interpretation="這不是健康回踩，而是壓力拒絕後的結構轉弱。",
                  response="取消多頭日內 setup，等待下方重新形成支撐。",
                  invalidation="重新收復失守支撐並完成回踩。", action_boundary="觀望", sizing_tier="none",
                  anchors=[mid, s1, lower_next]),
        ])

    up_impulse = _node(
        "upward_impulse", "向上衝擊 / 測試上方結構",
        "開盤後第一輪主動價格行為朝上方結構錨點推進；先判斷『是否突破』，而不是先假設高開等於看多。",
        watch=["上方錨點是否被有效站上", "突破後第一回踩", "VWAP/ORH 是否形成並提供同向確認"],
        interpretation="向上衝擊只是一個事件起點；真正有資訊的是突破後能否回踩守住，或未突破後回撤在哪裡被承接。",
        response="進入突破/受阻分支。", invalidation="價格完全轉向下方結構測試。",
        action_boundary="先分類，再等待第二步確認", sizing_tier="none", anchors=[upper_test, upper_next, mid],
        children=[
            _node("up_break", "有效突破上方錨點",
                  "價格站上第一上方結構錨點並保持足夠時間/成交量，進入回踩驗證。",
                  watch=["第一次回踩", "回踩是否縮量", "是否仍在 VWAP/ORH 上方"],
                  interpretation="突破本身仍不是終點；回踩結果決定它是接受還是假突破。",
                  response="切換至回踩守住/失守分支。", invalidation="立即跌回突破位下方。",
                  action_boundary="不追第一個突破；等回踩", sizing_tier="none", anchors=[upper_test, mid, orh],
                  children=[up_break_hold, up_break_fail]),
            up_reject,
        ])

    range_up = _node(
        "range_break_up", "區間向上突破 → 回踩驗證",
        "窄幅整理後有效突破區間上緣/ORH或第一上方錨點。",
        watch=["突破後是否回踩上緣不破", "VWAP 是否在下方", "下一壓力空間"],
        interpretation="先壓縮再突破通常比雜亂震盪中的單根上衝更容易定義失效點。",
        response="仍需完成回踩驗證；復用突破後回踩不破/失守兩個分支。",
        invalidation="突破後重新跌回區間內。", action_boundary="回踩確認前等待", sizing_tier="none",
        anchors=[orh or upper_test, mid, upper_next], children=[up_break_hold, up_break_fail])
    range_down = _node(
        "range_break_down", "區間向下跌破 → 反抽驗證",
        "窄幅整理後跌破區間下緣/ORL或第一支撐。",
        watch=["跌破後第一次反抽", "能否收復支撐", "VWAP 是否轉為壓力"],
        interpretation="向下跌破也需要反抽確認；若迅速收復，可能是 bear trap。",
        response="切換到反抽不過或收復支撐分支。", invalidation="快速收復區間下緣並保持。",
        action_boundary="等待反抽結果", sizing_tier="none", anchors=[orl or lower_test, mid, lower_next])
    compression = _node(
        "compression", "窄幅震盪 / 壓縮",
        "價格沒有有效離開上下結構錨點，反覆穿越中軸或成交區間逐步收窄。",
        watch=["ORH/ORL（形成後）", "VWAP 穿越次數", "量能是否收縮", "哪一側先出現接受"],
        interpretation="沒有方向接受就沒有必要強迫方向；壓縮的價值是讓之後的突破失效點更清楚。",
        response="等待向上突破、向下跌破或繼續無方向。", invalidation="價格在區間外完成接受。",
        action_boundary="區間內不強行建立方向倉位", sizing_tier="none",
        anchors=[lower_test, mid, upper_test, orl, orh],
        children=[
            range_up,
            _node("range_continue", "持續區間 → 不交易/等待",
                  "多次測試上下邊界都沒有形成接受，價格繼續在中軸兩側反覆。",
                  watch=["假突破次數", "成交量是否持續衰減", "午盤/事件時點是否可能改變波動"],
                  interpretation="邊界都沒有被市場接受時，方向性訊號品質低。",
                  response="保留風險預算，不因『總要選一邊』而交易。",
                  invalidation="區間外完成突破—回踩或跌破—反抽確認。", action_boundary="等待", sizing_tier="none",
                  anchors=[lower_test, mid, upper_test]),
            range_down,
        ])

    support_hold = _node(
        "support_test_hold", "下探支撐不破 → 反彈",
        "價格向下測試第一支撐/ORL後沒有形成有效跌破，並重新站回支撐上方。",
        watch=["反彈是否收復 VWAP/EMA20", "支撐附近是否縮量止跌", "反彈高點是否抬高"],
        interpretation="支撐被實際測試後仍能吸收賣壓，比單純『價格還在支撐上方』更有資訊。",
        response="進入反彈收復/反彈失敗分支。", invalidation="再次跌破支撐並反抽不過。",
        action_boundary="先等收復中軸再考慮反轉 setup", sizing_tier="none", anchors=[lower_test, mid, upper_test],
        children=[
            _node("support_hold_reclaim", "反彈收復中軸 → 回踩不破",
                  "支撐反彈後收復 VWAP/EMA20，且第一次回踩中軸沒有再次跌破。",
                  watch=["回踩量能", "是否形成更高低點", "下一壓力/ORH"],
                  interpretation="下探失敗 + 中軸收復 + 回踩守住構成較完整的日內反轉鏈。",
                  response="可升級為小倉位反轉候選；仍不代表長期趨勢反轉。",
                  invalidation="重新跌回中軸和第一支撐下方。", action_boundary="確認後才考慮 quarter", sizing_tier="quarter",
                  anchors=[lower_test, mid, upper_test, orh]),
            _node("support_hold_rebound_fail", "支撐反彈但中軸受阻 → 再測支撐",
                  "支撐雖暫時守住，但反彈在 VWAP/EMA20 下方被壓回。",
                  watch=["第二次測試支撐是否出現更弱反應", "支撐測試次數", "賣量是否增加"],
                  interpretation="支撐仍在，但買方沒有奪回中軸；多次測試會增加支撐被消耗的風險。",
                  response="不把第一次反彈視為反轉確認，等待第二次支撐測試結果。",
                  invalidation="收復中軸並完成回踩，或有效跌破支撐。", action_boundary="等待", sizing_tier="none",
                  anchors=[lower_test, mid]),
        ])

    support_break = _node(
        "support_break", "跌破支撐 → 反抽驗證",
        "價格有效跌破第一支撐/ORL，下一步觀察第一次反抽能否收復。",
        watch=["反抽是否在原支撐下方受阻", "VWAP 是否在上方形成壓力", "下一支撐/ATR 空間"],
        interpretation="真正重要的是原支撐跌破後是否轉為壓力；單次刺穿不足以確認延續走弱。",
        response="切換到反抽不過/迅速收復分支。", invalidation="快速收復原支撐並維持。",
        action_boundary="等待反抽", sizing_tier="none", anchors=[lower_test, lower_next, mid, atr_dn],
        children=[
            _node("support_break_retest_fail", "反抽支撐不過 → 弱勢延續",
                  "跌破後反抽原支撐，但價格無法站回其上並再度轉弱。",
                  watch=["是否形成更低高點", "下一支撐 S2", "賣量是否擴張"],
                  interpretation="原支撐轉成壓力，構成『跌破—反抽失敗』的完整確認鏈。",
                  response="多頭戰術 setup 失效；等待下一支撐或新的收復結構。",
                  invalidation="重新站回原支撐並完成回踩守住。", action_boundary="防守 / 不逆勢加倉", sizing_tier="none",
                  anchors=[lower_test, lower_next, mid, atr_dn]),
            _node("support_break_reclaim", "跌破後迅速收復 → Bear Trap",
                  "價格跌破第一支撐後快速收回其上，隨後回踩支撐不破。",
                  watch=["收復速度", "回踩量能", "VWAP/EMA20 是否進一步被收復"],
                  interpretation="向下突破沒有被接受，可能形成 bear trap；需要第二步收復中軸提高可信度。",
                  response="由純防守轉回反轉觀察，不能因一根反包立即提高倉位。",
                  invalidation="再次跌破支撐且反抽不過。", action_boundary="先等中軸收復；完成後才考慮 quarter", sizing_tier="none",
                  anchors=[lower_test, mid, upper_test]),
        ])

    downward_impulse = _node(
        "downward_impulse", "向下衝擊 / 測試下方結構",
        "開盤後第一輪主動價格行為朝第一支撐/區間下緣推進；先判斷支撐是否真正失效。",
        watch=["第一支撐的實際反應", "ORL/VWAP（形成後）", "第一次反彈是否能收復失地"],
        interpretation="向下衝擊不是自動看空；支撐守住與跌破後反抽不過是兩種完全不同的狀態。",
        response="進入支撐守住/支撐跌破分支。", invalidation="價格轉為上方結構測試。",
        action_boundary="先分類，再等待反彈/反抽確認", sizing_tier="none", anchors=[lower_test, lower_next, mid],
        children=[support_hold, support_break])

    root = _node(
        "intraday_root", "日內第一輪價格事件",
        "開盤後先觀察價格相對『已計算結構錨點』的第一輪主動行為：向上測試、區間壓縮、或向下測試。不要用前收漲跌本身決定方向。",
        watch=["第一個被測試的結構錨點", "15 分鐘 ORH/ORL（形成後）", "VWAP（形成後）", "量能與 ATR/RV 是否支持波動擴張"],
        interpretation="情景樹由市場實際事件驅動，不要求每支股票都經過同一組 gap branches。",
        response="選擇市場實際走出的事件分支，下一節點再依突破/受阻、回踩/反抽結果更新。",
        invalidation="N/A；根節點只負責事件分類。", action_boundary="觀察 → 分類 → 確認；確認前不使用 Kelly 提高倉位",
        sizing_tier="none", anchors=[book.get("current"), lower_test, mid, upper_test, atr_dn, atr_up],
        children=[up_impulse, compression, downward_impulse])

    return {
        "id": "intraday_event_tree", "horizon": "intraday",
        "title": "日內情景樹 / 價格事件 → 驗證 → 下一步",
        "evidence_status": "same_session" if same_session else "next_session_conditional",
        "opening_range_minutes": 15, "construction_policy": "compositional_event_tree",
        "price_anchor_policy": "Every numeric price comes from deterministic technical or same-session intraday evidence; prior close is not a structural trigger.",
        "anchor_book": book.get("all", []), "root": root,
    }


def _short_term_tree(book: dict[str, Any]) -> dict[str, Any]:
    s1, s2 = _first(book, "supports", 0), _first(book, "supports", 1)
    r1, r2 = _first(book, "resistances", 0), _first(book, "resistances", 1)
    ema20, sma50 = _find(book, "EMA20"), _find(book, "SMA50")
    atr_up, atr_dn = _find(book, "ATR_UP"), _find(book, "ATR_DN")
    repair_level = ema20 or r1
    breakdown_level = s1 or sma50
    root = _node(
        "short_root", "短期：未來數日到數週", "每個完成交易日重新判斷：結構修復、區間消化、或破位延續。",
        watch=["收盤相對 EMA20/SMA50", "支撐/壓力是否由一側轉為另一側", "RV 收斂或擴張", "催化/融資/估值事件"],
        interpretation="短期樹依賴完成交易日證據，不拿一個日內尖峰直接外推數週。",
        response="只有結構完成跨日確認後才升級短期信心。", invalidation="由各分支定義。",
        action_boundary="每個完成交易日更新", sizing_tier="quarter",
        anchors=[book.get("current"), s1, repair_level, sma50, r1],
        children=[
            _node("short_repair_hold", "修復：收復關鍵均線/壓力後守住",
                  "完成日收盤站上第一修復錨點，之後一到數個交易日回踩仍不破。",
                  watch=["下一壓力", "成交量/廣度是否支持", "RV 是否從高位收斂", "基本面催化是否同步改善"],
                  interpretation="短期結構由回撤轉向修復，但價格修復仍不能替代基本面證據。",
                  response="短期戰術信心提高；若 setup 驗證充分，可在 risk cap 內考慮 higher tier。",
                  invalidation="重新跌回修復錨點下方並連續無法收復。",
                  action_boundary="quarter；只有 validated setup 才考慮 half", sizing_tier="quarter",
                  anchors=[repair_level, sma50, r1, r2, atr_up]),
            _node("short_range", "消化：支撐與壓力之間震盪",
                  "數個交易日維持在第一支撐與第一壓力之間，沒有一側形成持續接受。",
                  watch=["區間寬度", "RV 是否下降", "量能是否收縮", "新估值/基本面資訊"],
                  interpretation="市場在消化不確定性；區間本身提供更清晰的未來失效邊界。",
                  response="保持小倉位或等待，不因時間經過就自動提高倉位。",
                  invalidation="完成日收盤突破並後續守住，或跌破並反抽不過。",
                  action_boundary="quarter 或等待", sizing_tier="quarter", anchors=[s1, r1, ema20]),
            _node("short_breakdown", "走弱：支撐跌破且反彈無法收復",
                  "完成日跌破第一中期支撐，後續反彈無法站回。",
                  watch=["下一支撐", "RV 是否擴張", "負面催化是否延續", "估值/盈利預期是否下修"],
                  interpretation="原本的回撤正在演變成更持久的短期惡化。",
                  response="降低戰術信心；等待新的底部/收復結構。",
                  invalidation="重新站回失守支撐並完成跨日確認。",
                  action_boundary="降低暴露 / 等待", sizing_tier="none", anchors=[breakdown_level, s2, atr_dn]),
        ])
    return {"id": "short_term_tree", "horizon": "short_term", "title": "短期情景樹 / 數日—數週",
            "evidence_status": "completed_session_structure", "construction_policy": "structure_and_catalyst",
            "anchor_book": book.get("all", []), "root": root}


def _long_term_tree(long_term_context: dict[str, Any]) -> dict[str, Any]:
    strengthen = long_term_context.get("strengthen_trigger") or "核心營運 KPI、現金流/毛利與競爭位置同步改善，且新增資本需求沒有吞噬改善。"
    mixed = long_term_context.get("mixed_trigger") or "產品/收入有改善，但毛利、現金流、資本強度、稀釋或競爭使經濟價值改善有限。"
    weaken = long_term_context.get("weaken_trigger") or "核心營運機制惡化、資本需求升高或估值無法由更新後的經濟性支持。"
    invalid = long_term_context.get("invalidation_trigger") or "原投資論點的核心因果鏈被連續兩個以上高品質證據否定。"
    watch = long_term_context.get("watch") or ["收入/毛利/營業利益", "自由現金流與資本支出", "市場份額/產品採用", "融資/稀釋", "估值與資本成本"]
    root = _node(
        "long_root", "長期：季度以上", "只有當公司營運、資本效率、競爭或估值證據 materially changed 時更新。",
        watch=watch, interpretation="長期情景由企業經濟性與估值主導，不用 ORH/VWAP 或單日價格替代基本面證據。",
        response="根據營運證據落入強化、有限改善、惡化或論點失效分支。", invalidation="N/A；根節點負責框架分類。",
        action_boundary="更新研究狀態，不由單一技術訊號改變長期論點", sizing_tier="quarter",
        children=[
            _node("long_strengthen", "論點強化", strengthen, watch=watch,
                  interpretation="企業經濟性與投資論點中的核心機制同向改善。",
                  response="提高長期 thesis confidence；重新估值並檢查價格是否已反映改善。",
                  invalidation="改善只停留在收入/敘事，未傳導到利潤、現金流或資本效率。",
                  action_boundary="先更新估值與風險上限，再考慮提高長期配置", sizing_tier="half"),
            _node("long_mixed", "有限改善 / 仍需驗證", mixed, watch=watch,
                  interpretation="部分證據改善，但價值創造仍被另一組變數抵消。",
                  response="維持條件式研究狀態，要求下一組 KPI 提供方向。",
                  invalidation="核心 KPI 明確向強化或惡化分支收斂。",
                  action_boundary="不因單一亮點升級整體 thesis", sizing_tier="quarter"),
            _node("long_weaken", "論點轉弱", weaken, watch=watch,
                  interpretation="原先預期的經濟改善沒有出現，或所需資本/估值代價變得更差。",
                  response="降低長期 confidence；重做估值與資本需求假設。",
                  invalidation="高品質營運與現金流證據重新改善並持續。",
                  action_boundary="降低長期配置上限 / 等待新證據", sizing_tier="none"),
            _node("long_invalidated", "論點失效", invalid, watch=watch,
                  interpretation="不是單季噪音，而是原 thesis 的核心因果鏈失效。",
                  response="切換到 THESIS_INVALIDATED 候選，重新建立新論點而不是替舊論點找藉口。",
                  invalidation="只有新的、不同的可驗證投資論點才能重啟，而非價格反彈本身。",
                  action_boundary="停止沿用舊 thesis 的 sizing logic", sizing_tier="none"),
        ])
    return {"id": "long_term_tree", "horizon": "long_term", "title": "長期情景樹 / 季度以上",
            "evidence_status": "fundamental_and_valuation", "construction_policy": "company_specific_operating_economics",
            "anchor_book": [], "root": root}


def build_scenario_trees(technical: dict[str, Any], daily_context: dict[str, Any] | None = None,
                         intraday_context: dict[str, Any] | None = None,
                         long_term_context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return evidence-anchored intraday, short-term and long-term trees."""
    del daily_context  # yesterday's close is audit context, not the structural branch generator.
    book = _build_anchor_book(technical, intraday_context or {})
    return [_intraday_tree(book), _short_term_tree(book), _long_term_tree(long_term_context or {})]
