#!/usr/bin/env python3
"""Reconcile normalized IBKR MCP, Massive, and yfinance option packets."""
from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any


def num(value: Any):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def expiry(value: Any):
    text = str(value or "")
    if len(text) >= 8 and text[:8].isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text[:10]


def rows(packet: dict[str, Any], source: str):
    result = {}
    for row in packet.get("options", []) or []:
        if not isinstance(row, dict):
            continue
        typ = str(row.get("type", row.get("right", ""))).lower()
        typ = "call" if typ in ("c", "call") else "put" if typ in ("p", "put") else typ
        strike = num(row.get("strike", row.get("strike_price")))
        exp = expiry(row.get("expiry", row.get("expiration", row.get("expiration_date"))))
        if typ not in ("call", "put") or strike is None or not exp:
            continue
        last = num(row.get("last", row.get("close", row.get("c", row.get("last_price")))))
        key = f"{exp}|{strike:g}|{typ}"
        result[key] = {"source": source, "key": key, "expiry": exp, "strike": strike,
                       "type": typ, "last": last, "bid": num(row.get("bid")),
                       "ask": num(row.get("ask")), "volume": num(row.get("volume")),
                       "open_interest": num(row.get("open_interest", row.get("oi"))),
                       "quote_quality": row.get("quote_quality"),
                       "retrieved_at": packet.get("retrieved_at")}
    return result


def source_spot(packet: dict[str, Any]):
    return num(packet.get("spot", packet.get("_ref_price")))


def compare(values: list[dict[str, Any]]):
    usable = [x for x in values if x.get("last") is not None and x["last"] > 0]
    if len(usable) < 2:
        return {"status": "not_observed", "sources": [x["source"] for x in values]}
    prices = [x["last"] for x in usable]
    center = statistics.median(prices)
    max_rel = max(abs(x - center) / center for x in prices) if center else None
    if max_rel is not None and max_rel <= 0.02:
        status = "agree"
    elif max_rel is not None and max_rel <= 0.10:
        status = "soft_conflict"
    else:
        status = "hard_conflict"
    return {"status": status, "sources": [x["source"] for x in usable],
            "prices": {x["source"]: x["last"] for x in usable},
            "median_last": center, "max_relative_dispersion": max_rel}


def reconcile(packets: dict[str, dict[str, Any]]):
    all_rows = {}
    source_manifest = {}
    spots = []
    for source, packet in packets.items():
        source_manifest[source] = {"provider": packet.get("provider", source),
                                   "source_role": packet.get("source_role"),
                                   "retrieved_at": packet.get("retrieved_at"),
                                   "rows": len(packet.get("options", []) or []),
                                   "spot": source_spot(packet),
                                   "quote_coverage": packet.get("quote_coverage", {})}
        if source_spot(packet) is not None:
            spots.append({"source": source, "spot": source_spot(packet)})
        for key, row in rows(packet, source).items():
            all_rows.setdefault(key, []).append(row)
    spot_values = [x["spot"] for x in spots]
    spot_median = statistics.median(spot_values) if spot_values else None
    spot_dispersion = max(abs(x - spot_median) / spot_median for x in spot_values) if spot_median else None
    spot_status = "not_observed" if len(spot_values) < 2 else "agree" if spot_dispersion <= 0.005 else "soft_conflict" if spot_dispersion <= 0.02 else "hard_conflict"
    comparisons = [compare(values) for values in all_rows.values()]
    counts = {status: sum(x.get("status") == status for x in comparisons) for status in ("agree", "soft_conflict", "hard_conflict", "not_observed")}
    return {"status": "ok", "source_manifest": source_manifest,
            "spot_reconciliation": {"status": spot_status, "values": {x["source"]: x["spot"] for x in spots}, "median": spot_median, "max_relative_dispersion": spot_dispersion},
            "contract_overlap": {"keys": len(all_rows), "two_or_more_sources": sum(len(x) >= 2 for x in all_rows.values()), "source_agreement_counts": counts},
            "contract_comparisons": comparisons,
            "complementary_evidence": ["IBKR MCP supplies local recent historical option bars", "Massive supplies contract reference and historical EOD option bars when the plan includes the endpoint", "yfinance supplies an independent research chain view and recent Yahoo fields"],
            "warnings": ["different sessions are not conflicts until timestamps are aligned", "missing and zero fields are not interchangeable", "put/call volume and OI are not directional flow", "consensus last price is diagnostic and does not create an executable quote"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ibkr")
    ap.add_argument("--massive", action="append", help="Massive packet; repeat for multiple expiries")
    ap.add_argument("--yfinance")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    packets = {}
    for name in ("ibkr", "yfinance"):
        path = getattr(args, name)
        if path:
            packets[name] = json.loads(Path(path).read_text(encoding="utf-8"))
    if args.massive:
        massive_packets = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.massive]
        if len(massive_packets) == 1:
            packets["massive"] = massive_packets[0]
        else:
            merged = dict(massive_packets[0])
            merged["options"] = [row for packet in massive_packets for row in packet.get("options", [])]
            merged["source_role"] = "historical_option_contract_and_underlying_bars_multiple_expiries"
            merged["contract_discovery"] = {"packets": len(massive_packets), "selected": [row for packet in massive_packets for row in packet.get("contract_discovery", {}).get("selected", [])]}
            merged["api_audit"] = {"calls": sum(packet.get("api_audit", {}).get("calls", 0) for packet in massive_packets), "packets": [packet.get("api_audit", {}) for packet in massive_packets]}
            packets["massive"] = merged
    result = reconcile(packets)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"written": args.out, "sources": list(packets), "status": result["status"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
