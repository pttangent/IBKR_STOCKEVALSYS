from __future__ import annotations

import argparse
import signal

from .engine import DEFAULT_SYMBOLS, RadarEngine
from .http_server import serve_http


def main() -> None:
    parser = argparse.ArgumentParser(description="IBKR realtime radar + executed order-flow UI")
    parser.add_argument("--host", default="127.0.0.1", help="dashboard bind host")
    parser.add_argument("--port", type=int, default=8765, help="dashboard HTTP port")
    parser.add_argument("--tws-host", default="127.0.0.1")
    parser.add_argument("--tws-port", type=int, default=7497, help="7497 paper TWS; 7496 live TWS by default")
    parser.add_argument("--client-id", type=int, default=4711)
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--mode", choices=("auto", "radar", "flow"), default="auto")
    parser.add_argument("--market-data-lines", type=int, default=100)
    parser.add_argument("--flow-quote-source", choices=("mktdata", "tick"), default="mktdata", help="mktdata = true trade ticks + 250ms top-of-book; tick = AllLast + BidAsk tick-by-tick")
    parser.add_argument("--db", default=None)
    args = parser.parse_args()

    engine = RadarEngine(args.symbols, mode=args.mode, market_data_lines=args.market_data_lines, flow_quote_source=args.flow_quote_source, storage_path=args.db)
    engine.set_connection(args.tws_host, args.tws_port, args.client_id)
    engine.start()
    server = serve_http(engine, args.host, args.port)
    stopping = False

    def stop(*_: object) -> None:
        nonlocal stopping
        if stopping:
            return
        stopping = True
        engine.stop()
        server.shutdown()

    signal.signal(signal.SIGINT, stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, stop)
    print(f"IBKR radar: http://{args.host}:{args.port}/radar | mode={engine.plan.mode} | symbols={','.join(engine.plan.symbols)} | quality={engine.plan.quality}", flush=True)
    try:
        server.serve_forever()
    finally:
        engine.close()
        server.server_close()


if __name__ == "__main__":
    main()
