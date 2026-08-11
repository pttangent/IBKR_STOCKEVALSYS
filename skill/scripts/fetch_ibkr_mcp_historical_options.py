#!/usr/bin/env python3
"""Call the project-local IBKR MCP historical option-chain path.

This intentionally calls ibkr_get_option_chain, which uses historical 5-minute
TRADES bars in the local MCP implementation. It never calls reqMktData and is
therefore suitable for accounts without live/OPRA option permission.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def result_json(result):
    if getattr(result, "structuredContent", None):
        return result.structuredContent
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
    return {"error": "MCP tool returned no JSON content"}


def unwrap_chain(value):
    """Flatten an MCP tool wrapper while retaining the raw chain objects."""
    if isinstance(value, dict) and isinstance(value.get("result"), dict):
        return value["result"]
    return value


async def collect(args):
    server = Path(args.server).resolve()
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(server)],
        env={**os.environ, "IB_HOST": args.host, "IB_PORT": str(args.port),
             "TWS_CLIENT_ID": str(args.client_id), "TWS_PAPER_ACCOUNT": args.paper_account},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            connected = result_json(await session.call_tool("ibkr_connect", arguments={
                "host": args.host, "port": args.port, "clientId": args.client_id}))
            chain_params = unwrap_chain(result_json(await session.call_tool(
                "ibkr_get_option_chain_params", arguments={"symbol": args.symbol})))
            expiries = []
            for chain in chain_params.get("chains", []) or []:
                expiries.extend(chain.get("expirations", []) or [])
            selected = args.expiries or sorted(set(expiries))[:args.expiries_count]
            chains = []
            for expiry in selected:
                raw = result_json(await session.call_tool(
                    "ibkr_get_option_chain", arguments={
                        "symbol": args.symbol, "expiration": expiry,
                        "num_strikes": args.num_strikes}))
                chains.append(unwrap_chain(raw))
            options = []
            for chain in chains:
                for row in chain.get("chain", []) if isinstance(chain, dict) else []:
                    item = dict(row)
                    item["expiration"] = chain.get("expiration")
                    options.append(item)
            return {
                "provider": "ibkr-local-mcp",
                "symbol": args.symbol.upper(),
                "status": "ok" if chains else "unavailable",
                "source_role": "historical_option_bars_via_project_local_mcp",
                "retrieved_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                "request": {"expiries": selected, "num_strikes": args.num_strikes,
                            "quote_path": "reqHistoricalDataAsync 1 D / 5 mins / TRADES",
                            "live_reqMktData": False},
                "connection": connected,
                "chain_params": chain_params,
                "chains": chains,
                "options": options,
                "limitations": [
                    "last/high/low/volume are historical bar fields, not executable bid/ask",
                    "no live OPRA quote, open interest, or Greeks are inferred",
                ],
            }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--server", default=str(Path(__file__).resolve().parents[2] / "ibkr-mcp" / "run_stdio.py"))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7497)
    ap.add_argument("--client-id", type=int, default=6170)
    ap.add_argument("--paper-account", default="DUO919088")
    ap.add_argument("--expiries-count", type=int, default=2)
    ap.add_argument("--expiries", nargs="*")
    ap.add_argument("--num-strikes", type=int, default=20)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    packet = asyncio.run(collect(args))
    Path(args.out).write_text(json.dumps(packet, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"written": args.out, "status": packet.get("status"),
                      "symbol": packet.get("symbol"), "chains": len(packet.get("chains", []))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
