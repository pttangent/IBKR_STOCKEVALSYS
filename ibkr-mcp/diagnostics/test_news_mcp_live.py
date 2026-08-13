"""Live MCP news smoke test against a local TWS session.

Usage: run the MCP server first, then execute this script from the project
environment. It is read-only and does not request market data or place orders.
"""

import asyncio
import argparse
import json
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


def result_value(result):
    if getattr(result, "structuredContent", None):
        value = result.structuredContent
        if isinstance(value, dict) and set(value) == {"result"}:
            return value["result"]
        return value
    blocks = getattr(result, "content", []) or []
    for block in blocks:
        if getattr(block, "type", None) == "text":
            try:
                return json.loads(block.text)
            except json.JSONDecodeError:
                return {"text": block.text}
    return {}


async def main(symbol: str, provider_codes: str):
    async with streamablehttp_client("http://127.0.0.1:8765/api/v1/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            connected = result_value(await session.call_tool(
                "ibkr_connect",
                {"host": "127.0.0.1", "port": 7497, "clientId": 6283},
            ))
            providers = result_value(await session.call_tool("ibkr_get_news_providers", {}))
            articles = result_value(await session.call_tool(
                "ibkr_get_news_articles",
                {"symbol": symbol, "providerCodes": provider_codes, "totalResults": 5},
            ))

            payload = {
                "symbol": symbol,
                "connected": connected,
                "provider_count": providers.get("count"),
                "providers": providers.get("providers"),
                "article_count": articles.get("count"),
                "conId": articles.get("conId"),
                "articles": articles.get("articles", []),
                "error": articles.get("error"),
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))

            first = (articles.get("articles") or [None])[0]
            if first:
                body = result_value(await session.call_tool(
                    "ibkr_get_news_article",
                    {
                        "providerCode": first["providerCode"],
                        "articleId": first["articleId"],
                    },
                ))
                print(json.dumps({
                    "body_providerCode": body.get("providerCode"),
                    "body_articleId": body.get("articleId"),
                    "articleType": body.get("articleType"),
                    "body_available": bool(body.get("articleText")),
                    "body_chars": len(body.get("articleText") or ""),
                }, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="NVDA")
    parser.add_argument("--providers", default="BRFG")
    args = parser.parse_args()
    asyncio.run(main(args.symbol.upper(), args.providers))
