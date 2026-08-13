"""Streamlined MCP server entry point with modular tool structure."""

import json
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator
from mcp.server.fastmcp import FastMCP
from starlette.routing import Route
from starlette.middleware.cors import CORSMiddleware

from .tws_client import TWSClient
from .models import AppContext
from .tools import (
    register_connection_tools,
    register_contract_tools,
    register_market_data_tools,
    register_order_tools,
    register_account_tools,
    register_news_tools,
    register_options_tools,
    register_scanner_tools,
    register_advanced_tools,
    register_fundamentals_tools
)
from .resources import (
    register_market_data_resource,
    register_portfolio_resource,
    register_news_resource
)
from .prompts import register_all_prompts


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Manage TWS client lifecycle."""
    tws = TWSClient()
    try:
        # TWS client is initialized but not connected here. Connection is done via the ibkr_connect tool.
        yield AppContext(tws=tws)
    finally:
        # Ensure TWS client is disconnected on shutdown
        if tws.is_connected():
            tws.disconnect()


# Create MCP server with lifespan
mcp = FastMCP(
    "IBKR TWS MCP Server",
    lifespan=app_lifespan,
    streamable_http_path="/api/v1/mcp"
)

# Register all tools
register_connection_tools(mcp)
register_contract_tools(mcp)
register_market_data_tools(mcp)
register_order_tools(mcp)
register_account_tools(mcp)
register_news_tools(mcp)
register_options_tools(mcp)
register_scanner_tools(mcp)
register_advanced_tools(mcp)
register_fundamentals_tools(mcp)

# Register all resources
register_market_data_resource(mcp)
register_portfolio_resource(mcp)
register_news_resource(mcp)

# Register all prompts
register_all_prompts(mcp)


# Resource state remains owned by the modular resource modules.  These imports
# preserve the legacy inspection surface used by existing local integrations.
from .resources.market_data import (
    _market_data_cache,
    _market_data_resource_subscriptions,
    _resource_background_streams,
)
from .resources.portfolio import (
    _portfolio_cache,
    _portfolio_resource_subscriptions,
    _portfolio_background_streams,
)
from .resources.news import _news_cache, _news_resource_subscription, _news_background_stream


def _task_status(task) -> str:
    if task is None:
        return "unknown"
    if task.done():
        return "cancelled" if task.cancelled() else "done"
    return "running"


async def ibkr_list_active_resource_streams() -> str:
    """Return a compatibility summary of active resource-based streams."""
    market_streams = [
        {
            "resource_id": resource_id,
            "resource_uri": f"ibkr://market-data/{resource_id}",
            "task_status": _task_status(_resource_background_streams.get(resource_id)),
            "last_update": _market_data_cache.get(resource_id, {}).get("timestamp", 0),
            "has_data": bool(_market_data_cache.get(resource_id, {}).get("data")),
            "contract": _market_data_cache.get(resource_id, {}).get("params", {}),
        }
        for resource_id in _market_data_resource_subscriptions
    ]
    portfolio_streams = [
        {
            "account": account,
            "resource_uri": f"ibkr://portfolio/{account}",
            "task_status": _task_status(_portfolio_background_streams.get(account)),
            "last_update": _portfolio_cache.get(account, {}).get("timestamp", 0),
            "has_data": bool(_portfolio_cache.get(account, {}).get("data")),
        }
        for account in _portfolio_resource_subscriptions
    ]
    news_streams = []
    if _news_resource_subscription:
        news_streams.append(
            {
                "resource_uri": "ibkr://news-bulletins",
                "task_status": _task_status(_news_background_stream),
                "last_update": _news_cache.get("timestamp", 0),
                "bulletin_count": len(_news_cache.get("bulletins", [])),
            }
        )
    return json.dumps(
        {
            "market_data": {"streams": market_streams, "count": len(market_streams)},
            "portfolio": {"streams": portfolio_streams, "count": len(portfolio_streams)},
            "news": {"streams": news_streams, "count": len(news_streams)},
        }
    )


# Backward-compatible Python exports for local tests and direct integrations.
# FastMCP keeps the callable functions in its tool registry after registration;
# exposing the same names here preserves the pre-modular import surface without
# creating a second implementation or bypassing MCP registration.
def _registered_tool(name: str):
    return mcp._tool_manager._tools[name].fn


ibkr_connect = _registered_tool("ibkr_connect")
ibkr_disconnect = _registered_tool("ibkr_disconnect")
ibkr_get_status = _registered_tool("ibkr_get_status")
ibkr_get_positions = _registered_tool("ibkr_get_positions")
ibkr_get_account_summary = _registered_tool("ibkr_get_account_summary")
ibkr_start_market_data_resource = _registered_tool("ibkr_start_market_data_resource")
ibkr_stop_market_data_resource = _registered_tool("ibkr_stop_market_data_resource")
ibkr_start_portfolio_resource = _registered_tool("ibkr_start_portfolio_resource")
ibkr_stop_portfolio_resource = _registered_tool("ibkr_stop_portfolio_resource")
ibkr_start_news_resource = _registered_tool("ibkr_start_news_resource")
ibkr_stop_news_resource = _registered_tool("ibkr_stop_news_resource")
ibkr_get_pnl = _registered_tool("ibkr_get_pnl")
ibkr_get_pnl_single = _registered_tool("ibkr_get_pnl_single")
ibkr_place_order = _registered_tool("ibkr_place_order")
ibkr_cancel_order = _registered_tool("ibkr_cancel_order")
ibkr_get_open_orders = _registered_tool("ibkr_get_open_orders")
ibkr_get_executions = _registered_tool("ibkr_get_executions")
ibkr_get_news_providers = _registered_tool("ibkr_get_news_providers")
ibkr_get_news_articles = _registered_tool("ibkr_get_news_articles")
ibkr_get_news_article = _registered_tool("ibkr_get_news_article")


# Health check endpoint
async def health_check(request):
    """Health check endpoint."""
    from starlette.responses import JSONResponse
    return JSONResponse({"status": "healthy"})


# Get the MCP streamable HTTP app
mcp_base_app = mcp.streamable_http_app()

# Add custom routes
mcp_base_app.routes.extend([
    Route("/health", health_check),
])


# Enhanced lifespan that combines MCP's session manager with Starlette app lifecycle
@asynccontextmanager
async def combined_lifespan(app_instance):
    """Wrap the Starlette app to initialize MCP session manager."""
    # Get the MCP session manager and run it (initializes task group)
    # The TWS client is already managed by app_lifespan above
    async with mcp.session_manager.run():
        yield


# Replace the lifespan context - this combines MCP's task group init with our TWS setup
mcp_base_app.router.lifespan_context = combined_lifespan

# Add CORS middleware for browser-based MCP clients
app = CORSMiddleware(
    mcp_base_app,
    allow_origins=["*"],  # Allow all origins for browser-based clients
    allow_credentials=True,  # Allow credentials (cookies, authorization headers)
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"],
    allow_headers=[
        "*",
        "Content-Type",
        "Authorization",
        "X-Requested-With",
        "Accept",
        "Accept-Encoding",
        "Accept-Language",
        "Cache-Control",
        "Connection",
        "Host",
        "Origin",
        "Referer",
        "Sec-Fetch-Dest",
        "Sec-Fetch-Mode",
        "Sec-Fetch-Site",
        "User-Agent",
        "Mcp-Session-Id",
        "Mcp-Initialize-Request",
    ],
    expose_headers=[
        "Mcp-Session-Id",
        "Access-Control-Allow-Origin",
        "Access-Control-Allow-Credentials",
        "Access-Control-Allow-Methods",
        "Access-Control-Allow-Headers",
    ],
    max_age=86400,  # Cache preflight for 24 hours
)


if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("SERVER_PORT", 8000))
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info"
    )
