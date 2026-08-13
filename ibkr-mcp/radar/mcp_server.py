from __future__ import annotations

import threading

from mcp.server.fastmcp import FastMCP

from .engine import DEFAULT_SYMBOLS, RadarEngine
from .http_server import serve_http

engine = RadarEngine(DEFAULT_SYMBOLS, mode="auto")
mcp = FastMCP("ibkr-realtime-radar")


@mcp.tool()
def ibkr_radar_plan(symbols: list[str] | None = None, mode: str = "auto", marketDataLines: int = 100, flowQuoteSource: str = "mktdata") -> dict:
    """Plan reqMktData vs tick-by-tick subscriptions before opening scarce IBKR lines."""
    if engine.connection_status()["running"]:
        return {"error": "radar is running; stop it before reconfiguration", "plan": engine.plan_status()}
    return engine.configure(symbols=symbols or DEFAULT_SYMBOLS, mode=mode, market_data_lines=marketDataLines, flow_quote_source=flowQuoteSource)


@mcp.tool()
def ibkr_radar_start() -> dict:
    """Start the already-planned radar using a dedicated read-only TWS client ID."""
    return {"started": True, "connection": engine.start(), "plan": engine.plan_status()}


@mcp.tool()
def ibkr_radar_snapshot(symbol: str | None = None) -> dict:
    """Return pressure, absorption, footprint/proxy footprint, candidate levels and data-quality labels."""
    return engine.snapshot(symbol)


@mcp.tool()
def ibkr_radar_alerts(limit: int = 40) -> dict:
    """Return material flow/absorption alerts."""
    return engine.alerts(limit)


@mcp.tool()
def ibkr_radar_pause() -> dict:
    """Release market-data subscriptions while leaving the local process alive."""
    return engine.pause()


@mcp.tool()
def ibkr_radar_stop() -> dict:
    """Stop subscriptions and close the dedicated TWS connection."""
    return engine.stop()


def main() -> None:
    engine.start()
    http = serve_http(engine)
    threading.Thread(target=http.serve_forever, name="radar-http", daemon=True).start()
    try:
        mcp.run(transport="stdio")
    finally:
        engine.close()


if __name__ == "__main__":
    main()
