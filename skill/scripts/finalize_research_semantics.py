#!/usr/bin/env python3
"""Enforce research-semantic invariants that are not merely JSON schema rules."""
from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path
from typing import Any

TECHNICAL_VALUATION_TOKENS = ("支撐", "阻力", "壓力", "VWAP", "ORH", "ORL", "EMA", "SMA", "突破", "跌破", "回踩", "反抽")
NEGATIVE_CONVERSION_RE = re.compile(r"[^。；\n]*營運現金流(?:只有|約為)淨利的\s*[-+]?\d+(?:\.\d+)?\s*倍[^。；\n]*[。；]?")


def load(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return {} if default is None else default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def _net_income(sec: dict) -> float | None:
    try:
        value = (((sec.get("data") or {}).get("canonical_financials") or {}).get("facts") or {}).get("net_income", {}).get("value")
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _repair_negative_conversion_text(value: Any) -> Any:
    if isinstance(value, str):
        replacement = "淨利與營運現金流皆為負，因此不使用 OCF/淨利倍數判斷現金轉換；改看虧損與營運現金流缺口是否同步收窄。"
        return NEGATIVE_CONVERSION_RE.sub(replacement, value)
    if isinstance(value, list):
        return [_repair_negative_conversion_text(item) for item in value]
    if isinstance(value, dict):
        return {key: _repair_negative_conversion_text(item) for key, item in value.items()}
    return value


def _valuation_has_reproducible_price_model(metrics: dict) -> bool:
    if not isinstance(metrics, dict):
        return False
    keys = {str(key).lower() for key in metrics}
    return any(key in keys for key in ("fair_value", "fair_value_range", "dcf", "price_target", "implied_price", "multiple_valuation"))


def _contains_technical_valuation_language(module: dict) -> bool:
    texts: list[str] = []
    for block in module.get("blocks", []) or []:
        if isinstance(block, dict):
            texts.extend([str(block.get("title") or ""), str(block.get("text") or "")])
    for row in module.get("judgments", []) or []:
        if isinstance(row, dict):
            texts.extend([str(row.get("conclusion") or ""), str(row.get("why") or "")])
    joined = " ".join(texts)
    return any(token in joined for token in TECHNICAL_VALUATION_TOKENS)


def finalize_semantics(report: dict, run: Path) -> dict:
    out = copy.deepcopy(report)
    sec = load(run / "sec_research.json")
    stock = load(run / "stock_eval.json")
    valuation_snapshot = load(run / "valuation_snapshot.json")
    limitations = list(out.get("global_limitations", []) or [])

    net_income = _net_income(sec)
    if net_income is not None and net_income <= 0:
        repaired = _repair_negative_conversion_text(out)
        if repaired != out:
            out = repaired
            note = "語義修正：淨利 <= 0 時不把 OCF/淨利的正比值解讀成現金轉換率；改看虧損與營運現金流缺口的絕對值與改善方向。"
            limitations = list(out.get("global_limitations", []) or [])
            if note not in limitations:
                limitations.append(note)

    valuation = out.get("modules", {}).get("valuation", {})
    metrics = valuation.get("metrics", {}) or valuation_snapshot
    no_pit = "no_pit_consensus" in str(metrics.get("status") or valuation_snapshot.get("status") or "")
    if no_pit and not _valuation_has_reproducible_price_model(metrics) and _contains_technical_valuation_language(valuation):
        message = (
            "目前沒有可核驗的時間點一致預期或可重現估值模型，因此本次不輸出以技術支撐/阻力替代的下行、基準或上行 fair value。"
            "已報告盈利、現金流與資產負債表仍保留為估值輸入；待 PIT 預期、可比公司或 DCF/倍數模型齊備後再建立價格區間。"
        )
        for block in valuation.get("blocks", []) or []:
            if isinstance(block, dict) and "估值判斷" in str(block.get("title") or ""):
                block["text"] = message
        for row in valuation.get("judgments", []) or []:
            if isinstance(row, dict) and "估值" in str(row.get("label") or ""):
                row["conclusion"] = message
                row["why"] = "技術價位只屬 timing/technical 模組；在沒有 valuation model 時不是 fair value。"
        valuation["status"] = "conditional"
        valuation["confidence"] = "low"
        valuation.setdefault("limitations", []).append("沒有可重現估值模型，因此不提供價格型 fair-value scenario。")
        note = "估值語義修正：沒有 PIT 預期或可重現估值模型時，不用技術支撐/阻力冒充 fair value。"
        limitations = list(out.get("global_limitations", []) or limitations)
        if note not in limitations:
            limitations.append(note)

    technical = out.get("modules", {}).get("technical", {})
    technical_as_of = str((stock.get("technical", {}) or {}).get("as_of") or "")[:10]
    report_as_of = str(out.get("as_of") or "")[:10]
    if technical_as_of and report_as_of and technical_as_of != report_as_of:
        old = f"{report_as_of} 可用的最新完整收盤"
        new = f"{technical_as_of} 可用的最新完整收盤"
        for block in technical.get("blocks", []) or []:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                block["text"] = block["text"].replace(old, new)

    out["global_limitations"] = limitations
    out.setdefault("package_hints", {})["semantic_finalization_status"] = "CASH_CONVERSION_AND_VALUATION_CHECKED"
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--output")
    args = ap.parse_args()
    source = Path(args.report)
    target = Path(args.output) if args.output else source
    report = json.loads(source.read_text(encoding="utf-8"))
    final = finalize_semantics(report, Path(args.run_dir))
    target.write_text(json.dumps(final, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"written": str(target), "status": final.get("package_hints", {}).get("semantic_finalization_status")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
