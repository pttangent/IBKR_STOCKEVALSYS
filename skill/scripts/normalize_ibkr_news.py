#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from research_http import source_packet, write_json


def normalize_news(payload: dict[str, Any]) -> list[dict[str, Any]]:
    articles = payload.get("articles") or []
    normalized = []
    for item in articles:
        normalized.append(
            {
                "published_at": item.get("time") or item.get("published_at"),
                "provider_code": item.get("providerCode") or item.get("provider_code"),
                "article_id": item.get("articleId") or item.get("article_id"),
                "headline": item.get("headline"),
                "article_text": item.get("articleText") or item.get("article_text"),
                "evidence_label": "FACT" if item.get("headline") else "UNVERIFIED",
            }
        )
    return normalized


def main() -> None:
    ap = argparse.ArgumentParser(description="Normalize output from the existing ibkr_get_news_articles MCP tool.")
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--input", required=True)
    ap.add_argument("--as-of")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    raw = json.loads(Path(args.input).read_text(encoding="utf-8"))
    as_of = args.as_of or date.today().isoformat()
    articles = normalize_news(raw)
    packet = source_packet(
        provider="IBKR_NEWS",
        source_type="company_market_news",
        source_id=f"ibkr-news:{args.symbol.upper()}:{as_of}",
        as_of=as_of,
        available_at=as_of,
        reliability="licensed_provider_via_ibkr",
        data={"symbol": args.symbol.upper(), "articles": articles},
        warnings=[
            "Headline publication time must be at or before the research cutoff for PIT use.",
            "A headline is evidence of a reported event, not proof of the headline's interpretation; retrieve article text or primary filings for material claims.",
        ],
        metadata={"input_tool": "ibkr_get_news_articles", "mcp_changed": False},
    )
    write_json(args.output, packet)
    print(f"OK IBKR news {args.symbol.upper()} articles={len(articles)} -> {args.output}")


if __name__ == "__main__":
    main()
