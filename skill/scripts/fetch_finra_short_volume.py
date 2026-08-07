#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from research_http import request_json, source_packet, write_json

FINRA_URL = "https://api.finra.org/data/group/otcMarket/name/regShoDaily"


def aggregate_rows(rows: list[dict[str, Any]], symbol: str, as_of: str | None = None) -> list[dict[str, Any]]:
    target = symbol.upper()
    daily: dict[str, dict[str, float]] = defaultdict(lambda: {"short": 0.0, "short_exempt": 0.0, "total": 0.0, "facilities": 0.0})
    for row in rows:
        if str(row.get("securitiesInformationProcessorSymbolIdentifier", "")).upper() != target:
            continue
        day = str(row.get("tradeReportDate") or "")
        if not day or (as_of and day > as_of):
            continue
        bucket = daily[day]
        bucket["short"] += float(row.get("shortParQuantity") or 0)
        bucket["short_exempt"] += float(row.get("shortExemptParQuantity") or 0)
        bucket["total"] += float(row.get("totalParQuantity") or 0)
        bucket["facilities"] += 1
    output = []
    for day in sorted(daily):
        values = daily[day]
        total = values["total"]
        output.append(
            {
                "date": day,
                "short_sale_volume": values["short"],
                "short_exempt_volume": values["short_exempt"],
                "total_reported_volume": total,
                "short_sale_volume_ratio": values["short"] / total if total else None,
                "reporting_facility_rows": int(values["facilities"]),
                "label": "SHORT_SALE_FLOW_PROXY",
            }
        )
    return output


def fetch_symbol(symbol: str) -> list[dict[str, Any]]:
    payload = {
        "limit": 5000,
        "fields": [
            "tradeReportDate",
            "securitiesInformationProcessorSymbolIdentifier",
            "shortParQuantity",
            "shortExemptParQuantity",
            "totalParQuantity",
            "reportingFacilityCode",
            "marketCode",
        ],
        "compareFilters": [
            {
                "compareType": "equal",
                "fieldName": "securitiesInformationProcessorSymbolIdentifier",
                "fieldValue": symbol.upper(),
            }
        ],
    }
    response = request_json(FINRA_URL, method="POST", payload=payload)
    if not isinstance(response, list):
        raise RuntimeError(f"Unexpected FINRA response shape: {type(response).__name__}")
    return response


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch FINRA Reg SHO daily short-sale volume for one symbol.")
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--as-of", help="YYYY-MM-DD local cutoff; dataset itself is rolling 12 months")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    symbol = args.symbol.upper()
    as_of = args.as_of or date.today().isoformat()
    raw = fetch_symbol(symbol)
    daily = aggregate_rows(raw, symbol, as_of)
    packet = source_packet(
        provider="FINRA",
        source_type="reg_sho_daily_short_sale_volume",
        source_id=f"finra-regsho:{symbol}:{as_of}",
        as_of=as_of,
        available_at=as_of,
        reliability="primary_regulatory",
        source_url=FINRA_URL,
        data={"symbol": symbol, "daily": daily},
        warnings=[
            "FINRA daily short-sale volume is transaction-flow data reported to FINRA facilities; it is not short interest or outstanding short positioning.",
            "The public dataset covers a rolling 12-month period, so it cannot by itself support longer historical replay.",
            "Do not infer directional conviction from the ratio without market-structure context.",
        ],
    )
    write_json(args.output, packet)
    print(f"OK FINRA {symbol} days={len(daily)} -> {args.output}")


if __name__ == "__main__":
    main()
