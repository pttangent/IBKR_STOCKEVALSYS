#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent))
from research_http import request_json, source_packet, write_json

FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"

DEFAULT_SERIES: dict[str, str] = {
    "DFF": "Effective Federal Funds Rate",
    "DGS2": "2-Year Treasury Yield",
    "DGS10": "10-Year Treasury Yield",
    "T10Y2Y": "10Y minus 2Y Treasury Spread",
    "CPIAUCSL": "Consumer Price Index",
    "PCEPILFE": "Core PCE Price Index",
    "UNRATE": "Unemployment Rate",
    "PAYEMS": "Nonfarm Payrolls",
    "INDPRO": "Industrial Production",
    "BAMLH0A0HYM2": "US High Yield Option-Adjusted Spread",
    "DCOILWTICO": "WTI Crude Oil Spot Price",
}


def build_observation_url(
    *,
    series_id: str,
    api_key: str,
    observation_start: str,
    observation_end: str,
    as_of: str | None,
) -> str:
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": observation_start,
        "observation_end": observation_end,
        "sort_order": "asc",
    }
    if as_of:
        # FRED real-time periods expose what was known on a historical date. This is the
        # single-vintage path used for PIT research/replay.
        params["realtime_start"] = as_of
        params["realtime_end"] = as_of
    return f"{FRED_OBSERVATIONS_URL}?{urlencode(params)}"


def normalize_observations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in payload.get("observations") or []:
        raw = item.get("value")
        value: float | None
        try:
            value = None if raw in {None, ".", ""} else float(raw)
        except (TypeError, ValueError):
            value = None
        rows.append(
            {
                "date": item.get("date"),
                "value": value,
                "realtime_start": item.get("realtime_start"),
                "realtime_end": item.get("realtime_end"),
            }
        )
    return rows


def fetch_series(
    series_id: str,
    *,
    api_key: str,
    start: str,
    end: str,
    as_of: str | None,
) -> dict[str, Any]:
    url = build_observation_url(
        series_id=series_id,
        api_key=api_key,
        observation_start=start,
        observation_end=end,
        as_of=as_of,
    )
    payload = request_json(url)
    rows = normalize_observations(payload)
    non_null = [r for r in rows if r["value"] is not None]
    return {
        "series_id": series_id,
        "description": DEFAULT_SERIES.get(series_id),
        "observations": rows,
        "latest_available_observation": non_null[-1] if non_null else None,
        "realtime_start": payload.get("realtime_start"),
        "realtime_end": payload.get("realtime_end"),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch FRED/ALFRED macro evidence with optional historical vintage cutoff.")
    ap.add_argument("--as-of", help="YYYY-MM-DD. When supplied, uses FRED real-time period as a point-in-time vintage.")
    ap.add_argument("--lookback-days", type=int, default=730)
    ap.add_argument("--series", default=",".join(DEFAULT_SERIES), help="Comma-separated FRED series IDs")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    api_key = os.environ.get("FRED_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Missing FRED_API_KEY")
    as_of = args.as_of or date.today().isoformat()
    end = as_of
    start = (datetime.strptime(as_of, "%Y-%m-%d").date() - timedelta(days=args.lookback_days)).isoformat()
    series_ids = [s.strip() for s in args.series.split(",") if s.strip()]

    data = {
        "pit_mode": bool(args.as_of),
        "series": [
            fetch_series(s, api_key=api_key, start=start, end=end, as_of=as_of if args.as_of else None)
            for s in series_ids
        ],
    }
    packet = source_packet(
        provider="FRED_ALFRED",
        source_type="macro_vintage" if args.as_of else "macro_current",
        source_id=f"fred:{as_of}:{'-'.join(series_ids)}",
        as_of=as_of,
        available_at=as_of if args.as_of else None,
        reliability="primary_official",
        source_url=FRED_OBSERVATIONS_URL,
        data=data,
        warnings=[
            "Macro series have different release lags and frequencies; observation date is not publication time.",
            "PIT mode uses the FRED real-time period boundary so later revisions are excluded for the requested as-of date.",
        ],
        metadata={"observation_start": start, "observation_end": end},
    )
    write_json(args.output, packet)
    print(f"OK FRED series={len(series_ids)} pit={bool(args.as_of)} -> {args.output}")


if __name__ == "__main__":
    main()

