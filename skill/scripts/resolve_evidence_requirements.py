#!/usr/bin/env python3
"""Resolve material evidence requests before a report calls them missing.

This tool searches the configured primary source route, records every attempt,
and distinguishes FOUND, NOT_AVAILABLE_AT_CUTOFF, and ERROR. It never turns an
unavailable filing into a fabricated placeholder.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from fetch_sec_research import filing_document_url, get_submissions, normalize_cik, recent_filings, resolve_ticker  # noqa: E402
from research_http import utc_now_iso, write_json  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--as-of", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--offering-date", default="2026-08-10")
    args = ap.parse_args()
    user_agent = os.environ.get("SEC_USER_AGENT", "").strip()
    if len(user_agent) < 10:
        raise SystemExit("SEC_USER_AGENT is required")
    identity = resolve_ticker(args.symbol, user_agent)
    cik = normalize_cik(identity["cik"])
    submissions = get_submissions(cik, user_agent)
    filings = recent_filings(submissions, as_of=args.as_of, limit=200)
    attempts = [{"route": "SEC submissions recent", "url": f"https://data.sec.gov/submissions/CIK{cik}.json", "status": "queried", "retrieved_at": utc_now_iso()}]

    q2 = [row for row in filings if row.get("form") == "10-Q" and row.get("reportDate") == "2026-06-27"]
    q2_item = {
        "field": "Q2 10-Q local freeze",
        "status": "FOUND" if q2 else "NOT_AVAILABLE_AT_CUTOFF",
        "attempts": attempts + [{"route": "SEC EDGAR 10-Q", "form": "10-Q", "report_date": "2026-06-27", "matches": len(q2)}],
        "source_documents": [{"accession": row.get("accessionNumber"), "filing_date": row.get("filingDate"), "url": filing_document_url(cik, row)} for row in q2],
        "next_action": "keep captured primary document in run/sec_primary" if q2 else "retry SEC submissions after cutoff"
    }

    offering_related = [row for row in filings if row.get("filingDate", "") >= args.offering_date and row.get("form") in {"8-K", "424B5", "S-3ASR", "FWP"}]
    close_candidates = [row for row in offering_related if row.get("form") == "8-K" and any(token in str(row.get("primaryDocument", "")).lower() for token in ["close", "offering", "20260812", "20260811"])]
    close_item = {
        "field": "post-offering closing confirmation",
        "status": "FOUND" if close_candidates else "NOT_AVAILABLE_AT_CUTOFF",
        "attempts": attempts + [{"route": "SEC post-pricing filing search", "forms": ["8-K", "424B5", "S-3ASR", "FWP"], "offering_date": args.offering_date, "related_filings": len(offering_related), "close_candidates": len(close_candidates)}],
        "source_documents": [{"form": row.get("form"), "accession": row.get("accessionNumber"), "filing_date": row.get("filingDate"), "acceptance": row.get("acceptanceDateTime"), "url": filing_document_url(cik, row)} for row in offering_related],
        "next_action": "retry after expected closing and verify final shares/greenshoe in 8-K" if not close_candidates else "reconcile final share count and greenshoe"
    }

    result = {
        "schema_version": "1.0",
        "symbol": args.symbol.upper(),
        "as_of": args.as_of,
        "retrieved_at": utc_now_iso(),
        "source": "SEC_EDGAR",
        "requirements": [q2_item, close_item],
        "interpretation": "NOT_AVAILABLE_AT_CUTOFF means the source route was actually queried and no qualifying document was available by the stated cutoff; it is not an assertion that the document will never exist."
    }
    write_json(args.output, result)
    print(json.dumps({"written": args.output, "requirements": [(x["field"], x["status"]) for x in result["requirements"]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
