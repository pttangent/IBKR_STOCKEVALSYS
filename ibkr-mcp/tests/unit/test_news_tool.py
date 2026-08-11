from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.server.fastmcp import FastMCP

from src.tools.news import register_news_tools
from src.tws_client import TWSClient


@pytest.mark.asyncio
async def test_historical_news_qualifies_underlying_contract():
    """The MCP news route must pass a real qualified conId to TWS."""
    mcp = FastMCP("news-test")
    register_news_tools(mcp)
    tool = mcp._tool_manager._tools["ibkr_get_news_articles"].fn

    tws = MagicMock(spec=TWSClient)
    tws.is_connected.return_value = True
    tws.ib = MagicMock()
    tws.ib.qualifyContractsAsync = AsyncMock(return_value=[MagicMock(conId=4815747)])
    tws.ib.reqHistoricalNewsAsync = AsyncMock(return_value=[
        SimpleNamespace(
            time="2026-08-06 15:00:00",
            providerCode="BRFG",
            articleId="BRFG$test",
            headline="NVIDIA test headline",
        )
    ])
    ctx = MagicMock()
    ctx.request_context.lifespan_context.tws = tws

    result = await tool(ctx, "NVDA", "BRFG", 5, "SMART", "USD", "", "")

    assert result["count"] == 1
    assert result["conId"] == 4815747
    assert result["articles"][0]["articleId"] == "BRFG$test"
    tws.ib.qualifyContractsAsync.assert_awaited_once()
    request = tws.ib.reqHistoricalNewsAsync.await_args.kwargs
    assert request["conId"] == 4815747
    assert request["providerCodes"] == "BRFG"


@pytest.mark.asyncio
async def test_historical_news_reports_unqualified_contract():
    mcp = FastMCP("news-test")
    register_news_tools(mcp)
    tool = mcp._tool_manager._tools["ibkr_get_news_articles"].fn

    tws = MagicMock(spec=TWSClient)
    tws.is_connected.return_value = True
    tws.ib = MagicMock()
    tws.ib.qualifyContractsAsync = AsyncMock(return_value=[])
    tws.ib.reqHistoricalNewsAsync = AsyncMock()
    ctx = MagicMock()
    ctx.request_context.lifespan_context.tws = tws

    result = await tool(ctx, "NOT_A_REAL_SYMBOL")

    assert result["count"] == 0
    assert result["articles"] == []
    assert "could not be qualified" in result["error"]
    tws.ib.reqHistoricalNewsAsync.assert_not_awaited()
