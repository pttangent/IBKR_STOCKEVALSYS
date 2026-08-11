#!/usr/bin/env python3
"""Fetch Massive minute aggregates as a non-IBKR fallback/cross-check."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env.local")


def get_json(url: str) -> dict:
    # Massive may reject Python's default urllib user-agent with HTTP 403 even
    # when the same authenticated URL succeeds from a normal browser client.
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "CODEX_USSTOCK/1.0 research-client",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code != 403:
            raise
        # On some Windows/network combinations Massive still blocks the
        # Python TLS fingerprint. curl.exe is the same authenticated REST
        # request and is used only as a transport fallback, not a new source.
        completed = subprocess.run(
            ["curl.exe", "-sS", "-A", "CODEX_USSTOCK/1.0 research-client", url],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)


def fetch(symbol: str, start: str, end: str, multiplier: int = 1, timespan: str = "minute", rth_only: bool = False) -> dict:
    key = os.environ.get("MASSIVE_API_KEY")
    if not key:
        raise RuntimeError("MASSIVE_API_KEY is not set")
    base = os.environ.get("MASSIVE_BASE_URL", "https://api.massive.com").rstrip("/")
    path = f"/v2/aggs/ticker/{symbol.upper()}/range/{multiplier}/{timespan}/{start}/{end}"
    params = urllib.parse.urlencode({"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": key})
    response = get_json(f"{base}{path}?{params}")
    eastern = ZoneInfo("America/New_York")
    bars = []
    for row in response.get("results", []):
        timestamp = dt.datetime.fromtimestamp(row["t"] / 1000, dt.timezone.utc).astimezone(eastern)
        bars.append({"date": timestamp.isoformat(), "open": row.get("o"), "high": row.get("h"), "low": row.get("l"),
                     "close": row.get("c"), "volume": row.get("v"), "count": row.get("n"), "wap": row.get("vw")})
    if rth_only:
        bars = [bar for bar in bars if dt.time.fromisoformat(bar["date"][11:19]) >= dt.time(9, 30)
                and dt.time.fromisoformat(bar["date"][11:19]) < dt.time(16, 0)]
    return {"provider": "massive-rest", "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "symbol": symbol.upper(), "request": {"path": path, "start": start, "end": end, "multiplier": multiplier,
            "timespan": timespan, "adjusted": True, "limit": 50000, "rth_only": rth_only},
            "response": {k: response.get(k) for k in ("status", "request_id", "resultsCount", "queryCount", "next_url") if k in response},
            "bars": bars}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--multiplier", type=int, default=1)
    ap.add_argument("--timespan", default="minute")
    ap.add_argument("--rth-only", action="store_true")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    packet = fetch(args.symbol, args.start, args.end, args.multiplier, args.timespan, args.rth_only)
    Path(args.out).write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"written": args.out, "provider": packet["provider"], "bars": len(packet["bars"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
