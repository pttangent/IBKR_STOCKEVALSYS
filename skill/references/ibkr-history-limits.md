# IBKR historical high-frequency data limits

These limits are provider constraints, not guarantees of entitlement or completeness. Confirm Level 1 market-data permissions and the TWS/API version before collecting.

The API's exact bar-size strings matter: use `1 secs`, `5 secs`, and `10 secs` (plural). The string `1 sec` is rejected with error 321 even though the conceptual bar size is one second. A wrapper that does not surface the error event may make this look like a timeout.

## History depth

- Historical tick-by-tick / Time & Sales: up to the last 3 years; each request returns at most 1,000 ticks and does not span multiple trading sessions. Page by session and timestamp.
- Historical bars of 30 seconds or less: IBKR documents that data older than six months is unavailable. A 14-calendar-day window is therefore within the documented age limit for 1s/5s/10s bars.
- Live tick-by-tick subscriptions are not historical backfill. The local radar database contains only the period during which the service was running.

## Historical bar step sizes

| Request duration | Smallest supported bar sizes |
|---|---|
| 60 seconds | 1s–1m |
| 120 seconds | 1s–2m |
| 1,800 seconds | 1s–30m |
| 3,600 seconds | 5s–1h |
| 14,400 seconds | 10s–3h |
| 28,800 seconds | 30s–8h |
| 1 day | 1m–1 day |

For 14 regular sessions, a rough minimum is 182 requests for 1-second bars (13 half-hour chunks/session), 98 requests for 5-second bars (7 hourly chunks/session), or 28 requests for 10-second bars (2 four-hour chunks/session). Include pre/post-market and holidays in the scheduler rather than assuming 390 minutes every day.

## Pacing and interpretation

For small bars, avoid identical requests within 15 seconds, six or more requests for the same contract/exchange/tick type within two seconds, and more than 60 requests in ten minutes. BID_ASK requests count twice. Historical ticks require Level 1 data. Trade-side labels are inferred unless a synchronized quote stream is available; historical TRADES and BID_ASK are separate request types.

IBKR real-time bars support 5 seconds only. Build 1s/10s live bars from the live tick stream or use historical bar requests; do not imply that a 5-second real-time subscription supplies true 1-second history.
