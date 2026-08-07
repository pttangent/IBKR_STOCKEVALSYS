# Structured decision memory and calibration

The useful part of TradingAgents-style memory is not prose recall by itself; it is a durable link between the evidence available at decision time, the scenario distribution, and the realized outcome.

## Record at decision time

After arbitration/final risk synthesis, persist a `decision-record.schema.json` object with:

- symbol / as-of / horizon;
- `evidence_freeze_hash`;
- thesis state;
- bear/base/bull/unknown probabilities when estimated;
- expected range when modeled;
- key claim IDs and invalidations.

Use:

```bash
python scripts/decision_memory.py --db runs/decision_memory.sqlite record --decision decision.json
```

## Settle later

Outcome ingestion is intentionally separate from research generation. Record comparable horizons such as T+1, T+5, T+20, or next-earnings. Include asset return, benchmark return, actual scenario classification when defensible, MAE/MFE, and volatility-forecast error when available.

```bash
python scripts/decision_memory.py --db runs/decision_memory.sqlite outcome \
  --decision-id <id> --outcome outcome.json
```

The helper calculates alpha as asset return minus benchmark return when both are supplied.

## Calibration

```bash
python scripts/decision_memory.py --db runs/decision_memory.sqlite summary --symbol NVDA
```

The first implementation reports multiclass Brier score, predicted-vs-actual scenario frequency, mean realized return and mean alpha. Do not treat tiny samples or mixed horizons as proof of forecasting skill. Segment calibration by comparable horizon, event type, sector, and regime before using it to change research weights.

LLM reflection may be added **after** deterministic calibration. The model should explain observed error patterns; it must not overwrite the quantitative record or invent why a scenario occurred.
