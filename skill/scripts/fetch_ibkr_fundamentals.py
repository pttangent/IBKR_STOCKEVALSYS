#!/usr/bin/env python3
"""Read-only IBKR Reuters Fundamentals probe and evidence packet."""
from __future__ import annotations

import argparse
import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from research_http import write_json


async def fetch(args: argparse.Namespace) -> dict:
    try:
        from ib_async import IB, Stock
    except ImportError as exc:
        return {"status": "unavailable", "reason": "ib_async is not installed", "error": str(exc)}
    ib = IB()
    retrieved_at = datetime.now(timezone.utc).isoformat()
    reports = [x.strip() for x in args.report_types.split(",") if x.strip()]
    output = {"symbol": args.symbol.upper(), "retrieved_at": retrieved_at, "host": args.host, "port": args.port, "reports": {}}
    try:
        await ib.connectAsync(args.host, args.port, clientId=args.client_id, readonly=True, timeout=10)
        contracts = await ib.qualifyContractsAsync(Stock(args.symbol.upper(), "SMART", "USD"))
        if not contracts:
            return {**output, "status": "error", "reason": "IBKR contract qualification returned no contract"}
        contract = contracts[0]
        for report_type in reports:  # sequential to respect TWS pacing
            try:
                xml = await ib.reqFundamentalDataAsync(contract, report_type)
                text = str(xml or "")
                if text:
                    output["reports"][report_type] = {"status": "ok", "bytes": len(text.encode("utf-8")), "raw_xml": text}
                else:
                    output["reports"][report_type] = {"status": "empty", "raw_xml": ""}
            except Exception as exc:
                message = str(exc)[:500]
                output["reports"][report_type] = {"status": "not_entitled" if "fundamental" in message.lower() or "subscription" in message.lower() or "not available" in message.lower() else "error", "error": message}
        output["status"] = "ok" if any(x.get("status") == "ok" for x in output["reports"].values()) else "not_entitled_or_empty"
        return output
    except Exception as exc:
        return {**output, "status": "connection_error", "error": str(exc)[:500]}
    finally:
        if ib.isConnected():
            ib.disconnect()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--as-of", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--host", default=os.getenv("IBKR_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.getenv("IBKR_PORT", "7497")))
    ap.add_argument("--client-id", type=int, default=int(os.getenv("IBKR_FUNDAMENTALS_CLIENT_ID", "37")))
    ap.add_argument("--report-types", default="ReportsFinSummary,ReportsFinStatements,ReportsOwnership")
    args = ap.parse_args()
    result = asyncio.run(fetch(args))
    packet = {"schema_version": "1.0", "source_id": f"ibkr-fundamentals:{args.symbol.upper()}:{args.as_of}", "provider": "IBKR_REUTERS_FUNDAMENTALS", "source_type": "secondary_fundamentals_cross_check", "symbol": args.symbol.upper(), "as_of": args.as_of, "available_at": None, "retrieved_at": result.get("retrieved_at"), "reliability": "secondary_entitlement_dependent", "source_url": "https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-ref/", "data": result, "warnings": ["Requires IBKR Reuters Fundamentals entitlement; unavailable/empty is a data-access result, not a company result.", "Raw Reuters data is a cross-check only and must not override SEC/IR or mix reporting periods.", "The adapter is read-only and does not place orders."]}
    write_json(args.output, packet)
    print(f"OK IBKR fundamentals {args.symbol.upper()}: {result.get('status')} -> {args.output}")


if __name__ == "__main__":
    main()
