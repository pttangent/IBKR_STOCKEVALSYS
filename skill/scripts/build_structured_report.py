#!/usr/bin/env python3
"""Build the canonical structured report from deterministic artifacts plus structured research content.

Production report renderers consume only the resulting JSON. Markdown is never
used as a semantic input. `research_content.json` is intentionally structured so
LLM/research synthesis is explicit and auditable before presentation.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
from pathlib import Path
from typing import Any

MODULE_TITLES = {
    "overview": "RESEARCH POSTURE / 研究結論",
    "fundamentals": "FUNDAMENTALS / 基本面",
    "valuation": "VALUATION / 估值",
    "technical": "TECHNICAL / 技術結構",
    "options": "OPTIONS / 期權與波動",
    "governance": "GOVERNANCE / 證據與審查",
    "risk": "RISK / 風險與倉位",
    "scenarios": "SCENARIOS / 情景",
    "evidence": "EVIDENCE / 證據鏈",
}


def load(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return {} if default is None else default
    return json.loads(path.read_text(encoding="utf-8"))


def merge(a: dict, b: dict) -> dict:
    out = copy.deepcopy(a)
    for key, value in b.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def default_charts(name: str, run: Path, stock: dict, options: dict, gamma: dict) -> list[dict]:
    charts: list[dict] = []
    tech = stock.get("technical", {})
    if name == "technical":
        if (run / "market_ibkr_daily_full.json").exists():
            charts.append({
                "id": "price_structure",
                "kind": "price_structure",
                "title": "PRICE STRUCTURE / 價格結構",
                "source_artifact": "market_ibkr_daily_full.json",
                "interpretation": {
                    "what": "近一年價格、EMA20、SMA50、SMA200 與成交量放在同一時間軸。",
                    "read": f"最新價 {tech.get('last_price', '—')}；20D/90D 報酬與均線位置應按短、中、長週期分開判讀。",
                    "why": "它用來辨識趨勢、回撤與長短週期衝突，決定 tactical setup 是否與長期 thesis 同向。",
                    "limit": "均線與價格結構是描述性證據，不自行證明未來方向；成交量口徑跨 provider 也可能不同。"
                }
            })
        charts.append({
            "id": "technical_snapshot",
            "kind": "technical_snapshot",
            "title": "TECHNICAL STATE / 技術狀態",
            "source_artifact": "stock_eval.json",
            "interpretation": {
                "what": "把 20D、90D 報酬、RSI 與 20D 實現波動集中展示。",
                "read": "同時看動量與風險，而不是用單一 RSI 或單一均線貼標籤。",
                "why": "同一股票可以短期轉弱、長期仍強；多週期衝突本身就是 timing 資訊。",
                "limit": "不同指標量綱不同，圖用於狀態掃描，不應把柱高直接互相比較。"
            }
        })
        charts.append({
            "id": "level_map",
            "kind": "level_map",
            "title": "OBSERVED LEVELS / 結構價位",
            "source_artifact": "stock_eval.json",
            "interpretation": {
                "what": "顯示 deterministic engine 找到的最近支撐、阻力與當前價格。",
                "read": "把價位視為候選反應區，而不是精確單點。",
                "why": "可用於設計 entry / invalidation / stop 的結構基準。",
                "limit": "swing/Fibonacci 等是啟發式結構；沒有當日 order flow 時不能稱為已確認支撐或壓力。"
            }
        })
    if name == "options":
        if options:
            charts.append({
                "id": "options_variance",
                "kind": "options_variance",
                "title": "OPTION VARIANCE PROXY / 期權波動代理",
                "source_artifact": "options_features.json",
                "interpretation": {
                    "what": "比較可用到期日的 ATM straddle/IV/總變異診斷。",
                    "read": "重點是前後到期日風險是否集中，而不是把少量合約稱為完整 volatility surface。",
                    "why": "事件風險前置時，短期期權通常承擔更高的時間密度風險，可影響 position haircut。",
                    "limit": "歷史 last 或缺 bid/ask 時只是 proxy；不能視為可成交即時 IV。"
                }
            })
        if gamma:
            status = gamma.get("gamma_status") or gamma.get("status")
            charts.append({
                "id": "gamma_structure",
                "kind": "gamma_structure",
                "title": "GROSS GAMMA STRUCTURE / Gamma 結構",
                "source_artifact": "options_gamma_structure.json",
                "interpretation": {
                    "what": "以可用 IV 與 OI 計算的 unsigned gross gamma concentration。",
                    "read": f"目前 Gamma 狀態：{status or 'unknown'}。只有 OI/IV 品質足夠且有經濟量級時才解讀 concentration。",
                    "why": "高 gross gamma 區可能改變 hedging sensitivity，但只有在 dealer sign 可辯護時才能談正/負 dealer GEX。",
                    "limit": "OI 不告訴 dealer/customer side；零或不可信 OI 必須 suppress wall，不能硬選最大值。"
                }
            })
    return charts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--research-content", help="structured analyst synthesis JSON; optional for diagnostic scaffold")
    ap.add_argument("--out", default="structured_report.json")
    args = ap.parse_args()
    run = Path(args.run_dir)

    manifest = load(run / "report_manifest.json")
    evidence = load(run / "evidence.json")
    stock = load(run / "stock_eval.json")
    valuation = load(run / "valuation_snapshot.json")
    options = load(run / "options_features.json")
    gamma = load(run / "options_gamma_structure.json")
    content = load(Path(args.research_content), {}) if args.research_content else {}

    run_id = manifest.get("run_id") or evidence.get("run_id") or run.name
    symbol = manifest.get("symbol") or evidence.get("symbol") or stock.get("symbol") or run_id.split("_")[0]
    report = {
        "schema_version": "2.0",
        "run_id": run_id,
        "symbol": symbol,
        "title": content.get("title") or f"{symbol} STOCK EVALUATION / 證據鏈研究報告",
        "as_of": manifest.get("as_of") or evidence.get("as_of") or stock.get("as_of"),
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "evidence_cutoff": manifest.get("evidence_cutoff") or evidence.get("evidence_cutoff"),
        "price_timestamp": manifest.get("price_timestamp"),
        "research_state": manifest.get("research_state") or content.get("research_state") or "NEEDS_EVIDENCE",
        "summary": content.get("summary", {}),
        "global_limitations": manifest.get("global_limitations", []) + content.get("global_limitations", []),
        "modules": {},
        "package_hints": {
            "evidence_packet": "evidence.json",
            "reader_outputs": ["markdown", "html"],
            "package_type": "evidence_chain_report_package"
        }
    }

    manifest_modules = manifest.get("modules", {})
    content_modules = content.get("modules", {})
    for name in MODULE_TITLES:
        base = copy.deepcopy(manifest_modules.get(name, {}))
        module = {
            "title": MODULE_TITLES[name],
            "status": base.get("status", "not_run"),
            "confidence": base.get("confidence"),
            "module_as_of": base.get("module_as_of"),
            "freshness_status": base.get("freshness_status", "unknown"),
            "source_artifacts": base.get("source_artifacts", []),
            "evidence_ids": base.get("evidence_ids", []),
            "missing_fields": base.get("missing_fields", []),
            "metrics": {},
            "blocks": [],
            "judgments": [],
            "knowledge_notes": [],
            "charts": [],
            "tables": [],
            "limitations": []
        }
        if name == "technical":
            module["metrics"] = stock.get("technical", {})
        elif name == "valuation":
            module["metrics"] = valuation
        elif name == "options":
            module["metrics"] = {"features": options, "gamma": gamma}
        module["charts"] = default_charts(name, run, stock, options, gamma)
        module = merge(module, content_modules.get(name, {}))
        report["modules"][name] = module

    out = run / args.out if not Path(args.out).is_absolute() else Path(args.out)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"written": str(out), "run_id": run_id, "modules": len(report["modules"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
