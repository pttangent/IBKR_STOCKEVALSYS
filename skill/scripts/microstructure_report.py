#!/usr/bin/env python3
"""Read-only microstructure report from ibkr_tick_radar SQLite history."""
from __future__ import annotations
import argparse, datetime as dt, json, math, sqlite3
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

NY=ZoneInfo("America/New_York")

def _iso(ts): return dt.datetime.fromtimestamp(ts,dt.timezone.utc).isoformat()
def _num(x):
    try:
        x=float(x); return x if math.isfinite(x) else None
    except (TypeError,ValueError): return None

def report(db: str, symbols: list[str], days: int) -> dict:
    con=sqlite3.connect(f"file:{db}?mode=ro",uri=True)
    max_ts=con.execute("select max(event_time) from ticks").fetchone()[0]
    if max_ts is None: return {"status":"unavailable","reason":"no ticks"}
    start=max_ts-days*86400
    result={"status":"ok","window_start":_iso(start),"window_end":_iso(max_ts),"requested_days":days,"symbols":{}}
    for symbol in [x.upper() for x in symbols]:
        rows=con.execute("select event_time,price,size,side,bid,ask,bid_size,ask_size,exchange,market_data_type,status from ticks where symbol=? and event_time between ? and ? order by event_time",(symbol,start,max_ts)).fetchall()
        if not rows:
            result["symbols"][symbol]={"status":"unavailable","reason":"no local tick history"}; continue
        prices=[r[1] for r in rows if _num(r[1]) is not None]; sizes=[r[2] for r in rows if _num(r[2]) is not None]
        buy=sum(r[2] for r in rows if r[3]>0); sell=sum(r[2] for r in rows if r[3]<0); unknown=sum(r[2] for r in rows if r[3]==0); total=buy+sell+unknown
        spreads=[]; spread_bps=[]; quote_rows=0
        for r in rows:
            bid,ask=r[4],r[5]
            if bid and ask and bid>0 and ask>=bid:
                quote_rows+=1; spreads.append(ask-bid); spread_bps.append((ask-bid)/((ask+bid)/2)*10000)
        large=sum(1 for r in rows if r[1]*r[2]>=100000)
        by_hour=defaultdict(lambda:{"ticks":0,"shares":0.0,"net_shares":0.0})
        for r in rows:
            h=dt.datetime.fromtimestamp(r[0],dt.timezone.utc).astimezone(NY).strftime("%H:%M")
            by_hour[h]["ticks"]+=1; by_hour[h]["shares"]+=r[2]; by_hour[h]["net_shares"]+=r[2]*r[3]
        net=buy-sell
        result["symbols"][symbol]={"status":"ok","ticks":len(rows),"coverage_start":_iso(rows[0][0]),"coverage_end":_iso(rows[-1][0]),"coverage_hours":(rows[-1][0]-rows[0][0])/3600,"first_price":prices[0],"last_price":prices[-1],"intrawindow_return":prices[-1]/prices[0]-1 if prices[0] else None,"high":max(prices),"low":min(prices),"total_shares":total,"buy_shares":buy,"sell_shares":sell,"unknown_shares":unknown,"buy_share_pct":buy/total if total else None,"sell_share_pct":sell/total if total else None,"unknown_share_pct":unknown/total if total else None,"net_flow_ratio":net/(buy+sell) if buy+sell else None,"vwap":sum(r[1]*r[2] for r in rows)/sum(r[2] for r in rows) if total else None,"avg_trade_size":sum(sizes)/len(sizes) if sizes else None,"median_trade_size":sorted(sizes)[len(sizes)//2] if sizes else None,"large_trade_count_ge_100k":large,"quoted_ticks":quote_rows,"quote_coverage_pct":quote_rows/len(rows),"median_spread":sorted(spreads)[len(spreads)//2] if spreads else None,"median_spread_bps":sorted(spread_bps)[len(spread_bps)//2] if spread_bps else None,"by_ny_hour":dict(sorted(by_hour.items())),"caveats":["side is a quote/price heuristic, not confirmed customer buy/sell or open/close direction","local history does not cover the requested full 14 days if coverage_hours is materially below 336","AllLast and market-data entitlement/delay status are source-specific"]}
    con.close(); return result

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--db",default="data/radar_history.sqlite3"); ap.add_argument("--symbols",nargs="+",default=["XE"]); ap.add_argument("--days",type=int,default=14); ap.add_argument("--out",required=True); args=ap.parse_args(); result=report(args.db,args.symbols,args.days); Path(args.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); print(json.dumps(result,ensure_ascii=False))
if __name__ == "__main__": main()
