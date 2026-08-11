#!/usr/bin/env python3
"""Read-only capability smoke tests for the stock-eval external sources.

The script records status and small schema summaries only. It never writes
credentials or raw provider payloads. Use the project environment:

    python skill/scripts/test_external_sources.py --symbol NVDA
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env.local")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def result(source: str, capability: str, status: str, **fields: Any) -> dict[str, Any]:
    return {
        "source": source,
        "capability": capability,
        "status": status,
        "retrieved_at": now(),
        **fields,
    }


def get_json(url: str, *, params: dict[str, Any] | None = None,
             headers: dict[str, str] | None = None, timeout: int = 20) -> tuple[int, Any, str]:
    response = requests.get(url, params=params, headers=headers, timeout=timeout)
    text = response.text[:2000]
    try:
        payload = response.json()
    except ValueError:
        payload = None
    return response.status_code, payload, text


def test_sec(symbol: str) -> list[dict[str, Any]]:
    headers = {"User-Agent": os.getenv("SEC_USER_AGENT", "stock-eval-system/1.0")}
    out: list[dict[str, Any]] = []
    try:
        code, tickers, text = get_json("https://www.sec.gov/files/company_tickers.json", headers=headers)
        row = next((v for v in tickers.values() if str(v.get("ticker", "")).upper() == symbol.upper()), None) if isinstance(tickers, dict) else None
        if code == 200 and row:
            cik = f"{int(row['cik_str']):010d}"
            out.append(result("SEC EDGAR", "ticker_to_cik", "ok", cik=cik, company=row.get("title")))
        else:
            # Keep the smoke test useful when SEC blocks the mapping file because
            # the local User-Agent lacks a real contact email. The CIK override is
            # only for the explicitly requested NVDA test; production must set a
            # compliant SEC_USER_AGENT and use the official mapping file.
            known_ciks = {"NVDA": "0001045810"}
            cik = known_ciks.get(symbol.upper())
            out.append(result("SEC EDGAR", "ticker_to_cik", "blocked_or_invalid_user_agent",
                              http_status=code, known_cik_used=bool(cik), error=text[:240]))
            if not cik:
                return out

        code, submissions, text = get_json(f"https://data.sec.gov/submissions/CIK{cik}.json", headers=headers)
        recent = submissions.get("filings", {}).get("recent", {}) if isinstance(submissions, dict) else {}
        forms = recent.get("form", []) if isinstance(recent, dict) else []
        wanted = {"10-K", "10-Q", "8-K", "4", "SC 13D", "SC 13G", "144"}
        out.append(result("SEC EDGAR", "submissions", "ok" if code == 200 else "failed",
                          http_status=code, recent_matches=sum(f in wanted for f in forms),
                          latest_filing_date=(recent.get("filingDate") or [None])[0] if recent else None,
                          error=None if code == 200 else text[:240]))

        if code == 200 and isinstance(recent, dict):
            accession_numbers = recent.get("accessionNumber", [])
            primary_documents = recent.get("primaryDocument", [])
            cik_number = str(int(cik))
            for form in ("10-K", "10-Q", "8-K", "4"):
                try:
                    index = forms.index(form)
                    accession = accession_numbers[index].replace("-", "")
                    primary = primary_documents[index]
                    filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik_number}/{accession}/{primary}"
                    filing = requests.get(filing_url, headers=headers, timeout=20)
                    out.append(result("SEC EDGAR", f"latest_{form}",
                                      "ok" if filing.status_code == 200 and filing.content else "failed",
                                      http_status=filing.status_code, filing_date=recent.get("filingDate", [None])[index],
                                      accession=recent.get("accessionNumber", [None])[index],
                                      content_length=len(filing.content),
                                      error=None if filing.status_code == 200 else filing.text[:240]))
                except (ValueError, IndexError, KeyError):
                    out.append(result("SEC EDGAR", f"latest_{form}", "not_found"))

        code, facts, text = get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json", headers=headers)
        facts_count = len(facts.get("facts", {}).get("us-gaap", {})) if isinstance(facts, dict) else 0
        out.append(result("SEC EDGAR", "companyfacts", "ok" if code == 200 and facts_count else "failed",
                          http_status=code, us_gaap_fact_count=facts_count,
                          error=None if code == 200 else text[:240]))
    except Exception as exc:
        out.append(result("SEC EDGAR", "request", "error", error=f"{type(exc).__name__}: {exc}"))
    return out


def test_ir() -> list[dict[str, Any]]:
    urls = {
        "NVIDIA": "https://investor.nvidia.com/",
        "Vistra": "https://investor.vistracorp.com/",
        "GE Vernova": "https://www.gevernova.com/investors",
    }
    out = []
    for name, url in urls.items():
        try:
            response = requests.get(url, headers={"User-Agent": "stock-eval-system/1.0"}, timeout=20)
            out.append(result("Company IR", name, "ok" if response.status_code < 400 else "failed",
                              http_status=response.status_code, final_url=response.url,
                              content_type=response.headers.get("content-type")))
        except Exception as exc:
            out.append(result("Company IR", name, "error", error=f"{type(exc).__name__}: {exc}"))
    return out


def test_fred() -> list[dict[str, Any]]:
    key = os.getenv("FRED_API_KEY", "")
    if not key:
        return [result("FRED/ALFRED", "DGS10", "not_configured")]
    base = "https://api.stlouisfed.org/fred/series/observations"
    common = {"series_id": "DGS10", "api_key": key, "file_type": "json", "limit": 1, "sort_order": "desc"}
    out = []
    try:
        code, payload, text = get_json(base, params=common)
        observations = payload.get("observations", []) if isinstance(payload, dict) else []
        out.append(result("FRED/ALFRED", "DGS10", "ok" if code == 200 and observations else "failed",
                          http_status=code, observation_count=len(observations),
                          latest_observation=observations[0] if observations else None,
                          error=None if code == 200 else text[:240]))
        vintage = {**common, "vintage_dates": "2025-01-02"}
        code, payload, text = get_json(base, params=vintage)
        observations = payload.get("observations", []) if isinstance(payload, dict) else []
        out.append(result("FRED/ALFRED", "vintage_date", "ok" if code == 200 and observations else "failed",
                          http_status=code, vintage_date="2025-01-02", observation_count=len(observations),
                          error=None if code == 200 else text[:240]))
    except Exception as exc:
        out.append(result("FRED/ALFRED", "request", "error", error=f"{type(exc).__name__}: {exc}"))
    return out


def test_alpha(symbol: str) -> list[dict[str, Any]]:
    key = os.getenv("ALPHA_VANTAGE_API_KEY", "")
    if not key:
        return [result("Alpha Vantage", "configured_key", "not_configured")]
    out = []
    queries = [
        ("EARNINGS_ESTIMATES", {"function": "EARNINGS_ESTIMATES", "symbol": symbol}),
        ("EARNINGS_CALL_TRANSCRIPT", {"function": "EARNINGS_CALL_TRANSCRIPT", "symbol": symbol, "quarter": "2025Q4"}),
        ("EARNINGS_CALENDAR", {"function": "EARNINGS_CALENDAR", "symbol": symbol, "horizon": "3month"}),
    ]
    for capability, params in queries:
        try:
            params["apikey"] = key
            response = requests.get("https://www.alphavantage.co/query", params=params, timeout=30)
            body = response.text[:300]
            content_type = response.headers.get("content-type", "")
            try:
                payload = response.json()
                keys = list(payload.keys())[:10] if isinstance(payload, dict) else []
                has_data = isinstance(payload, dict) and not ("Error Message" in payload or "Note" in payload or "Information" in payload)
            except ValueError:
                keys = []
                has_data = bool(body)
            out.append(result("Alpha Vantage", capability, "ok" if response.status_code == 200 and has_data else "failed",
                              http_status=response.status_code, response_keys=keys,
                              content_type=content_type,
                              payload_type="json" if payload is not None else "text",
                              error=None if has_data else body))
            time.sleep(0.25)
        except Exception as exc:
            out.append(result("Alpha Vantage", capability, "error", error=f"{type(exc).__name__}: {exc}"))
    return out


def test_finnhub(symbol: str) -> list[dict[str, Any]]:
    key = os.getenv("FINNHUB_API_KEY", "")
    if not key:
        return [result("Finnhub", "quote", "not_configured")]
    out = []
    try:
        code, payload, text = get_json("https://finnhub.io/api/v1/quote", params={"symbol": symbol, "token": key})
        out.append(result("Finnhub", "quote", "ok" if code == 200 and isinstance(payload, dict) and "c" in payload else "failed",
                          http_status=code, fields=list(payload.keys()) if isinstance(payload, dict) else [],
                          error=None if code == 200 else text[:240]))
        code, payload, text = get_json("https://finnhub.io/api/v1/company-news",
                                       params={"symbol": symbol, "from": "2026-08-01", "to": "2026-08-07", "token": key})
        out.append(result("Finnhub", "company_news", "ok" if code == 200 and isinstance(payload, list) else "failed",
                          http_status=code, row_count=len(payload) if isinstance(payload, list) else 0,
                          error=None if code == 200 else text[:240]))
    except Exception as exc:
        out.append(result("Finnhub", "quote", "error", error=f"{type(exc).__name__}: {exc}"))
    return out


def test_nasdaq() -> list[dict[str, Any]]:
    key = os.getenv("NASDAQ_DATA_LINK_API_KEY", "")
    params = {"limit": 1}
    if key:
        params["api_key"] = key
    try:
        code, payload, text = get_json("https://data.nasdaq.com/api/v3/datasets/FRED/GDP.json", params=params)
        return [result("Nasdaq Data Link", "public_dataset", "ok" if code == 200 and isinstance(payload, dict) else "failed",
                       http_status=code, authenticated=bool(key),
                       row_count=len(payload.get("dataset", {}).get("data", [])) if isinstance(payload, dict) else 0,
                       error=None if code == 200 else text[:240])]
    except Exception as exc:
        return [result("Nasdaq Data Link", "public_dataset", "error", error=f"{type(exc).__name__}: {exc}")]


def test_massive(symbol: str) -> list[dict[str, Any]]:
    key = os.getenv("MASSIVE_API_KEY", "")
    if not key:
        return [result("Massive", "previous_aggregate", "not_configured")]
    base = os.getenv("MASSIVE_BASE_URL", "https://api.massive.com").rstrip("/")
    try:
        code, payload, text = get_json(f"{base}/v2/aggs/ticker/{symbol}/prev",
                                       params={"adjusted": "true", "apiKey": key})
        rows = payload.get("results", []) if isinstance(payload, dict) else []
        return [result("Massive", "previous_aggregate", "ok" if code == 200 and rows else "failed",
                       http_status=code, row_count=len(rows),
                       error=None if code == 200 else text[:240])]
    except Exception as exc:
        return [result("Massive", "previous_aggregate", "error", error=f"{type(exc).__name__}: {exc}")]


def test_yfinance(symbol: str) -> list[dict[str, Any]]:
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        history = ticker.history(period="5d", auto_adjust=False)
        out = [result("yfinance", "history", "ok" if not history.empty else "failed",
                       rows=len(history), columns=list(history.columns),
                       latest=str(history.index[-1]) if not history.empty else None)]
        try:
            expirations = ticker.options
            out.append(result("yfinance", "options_expirations", "ok" if expirations else "empty",
                              expiration_count=len(expirations)))
        except Exception as exc:
            out.append(result("yfinance", "options_expirations", "error",
                              error=f"{type(exc).__name__}: {exc}"))
        return out
    except Exception as exc:
        return [result("yfinance", "history", "error", error=f"{type(exc).__name__}: {exc}")]


def test_polymarket() -> list[dict[str, Any]]:
    out = []
    for capability, url in [
        ("gamma_events", "https://gamma-api.polymarket.com/events?limit=1&active=true"),
        ("clob_markets", "https://clob.polymarket.com/markets?limit=1"),
    ]:
        try:
            code, payload, text = get_json(url)
            out.append(result("Polymarket", capability, "ok" if code == 200 and payload is not None else "failed",
                              http_status=code, payload_type=type(payload).__name__,
                              error=None if code == 200 else text[:240]))
        except Exception as exc:
            out.append(result("Polymarket", capability, "error", error=f"{type(exc).__name__}: {exc}"))
    return out


def test_finra() -> list[dict[str, Any]]:
    url = "https://api.finra.org/data/group/otcMarket/name/regShoDaily"
    try:
        response = requests.get(url, params={"limit": 1}, headers={"User-Agent": "stock-eval-system/1.0"}, timeout=30)
        content_type = response.headers.get("content-type", "")
        lines = [line for line in response.text.splitlines() if line.strip()]
        return [result("FINRA", "reg_sho_daily", "ok" if response.status_code == 200 and len(lines) >= 2 else "failed",
                       http_status=response.status_code, content_type=content_type,
                       payload_type="csv" if "text/csv" in content_type or response.text.startswith("tradeReportDate") else "unknown",
                       row_count=max(0, len(lines) - 1),
                       error=None if response.status_code == 200 else response.text[:240])]
    except Exception as exc:
        return [result("FINRA", "reg_sho_daily", "error", error=f"{type(exc).__name__}: {exc}")]


def test_stocktwits(symbol: str) -> list[dict[str, Any]]:
    try:
        response = requests.get(f"https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json",
                                headers={"User-Agent": "stock-eval-system/1.0"}, timeout=20)
        try:
            payload = response.json()
        except ValueError:
            payload = None
        messages = payload.get("messages", []) if isinstance(payload, dict) else []
        return [result("Stocktwits", "public_symbol_stream",
                       "ok" if response.status_code == 200 and isinstance(payload, dict) else "not_authorized",
                       http_status=response.status_code, message_count=len(messages),
                       fields=list(payload.keys())[:10] if isinstance(payload, dict) else [],
                       note="Firestream credentials were not supplied")]
    except Exception as exc:
        return [result("Stocktwits", "public_symbol_stream", "error", error=f"{type(exc).__name__}: {exc}")]


def test_reddit(symbol: str) -> list[dict[str, Any]]:
    try:
        response = requests.get("https://www.reddit.com/r/stocks/search.json",
                                params={"q": symbol, "restrict_sr": 1, "limit": 1},
                                headers={"User-Agent": "stock-eval-system/1.0"}, timeout=20)
        return [result("Reddit", "data_api_without_oauth", "ok" if response.status_code == 200 else "not_authorized",
                       http_status=response.status_code,
                       note="No OAuth client/token supplied; do not use Reddit as a source until approved")]
    except Exception as exc:
        return [result("Reddit", "data_api_without_oauth", "error", error=f"{type(exc).__name__}: {exc}")]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="NVDA")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    checks: list[dict[str, Any]] = []
    checks.extend(test_sec(args.symbol))
    checks.extend(test_ir())
    checks.extend(test_fred())
    checks.extend(test_alpha(args.symbol))
    checks.extend(test_finnhub(args.symbol))
    checks.extend(test_nasdaq())
    checks.extend(test_massive(args.symbol))
    checks.extend(test_yfinance(args.symbol))
    checks.extend(test_polymarket())
    checks.extend(test_finra())
    checks.extend(test_stocktwits(args.symbol))
    checks.extend(test_reddit(args.symbol))

    report = {
        "as_of": now(),
        "symbol": args.symbol,
        "secret_values_recorded": False,
        "checks": checks,
    }
    output = json.dumps(report, ensure_ascii=False, indent=2)
    print(output)
    if args.out:
        Path(args.out).write_text(output + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
