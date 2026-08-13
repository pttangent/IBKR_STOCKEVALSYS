from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def connect(path: str | Path) -> sqlite3.Connection:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS decisions (
            decision_id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            as_of TEXT NOT NULL,
            horizon TEXT,
            evidence_freeze_hash TEXT NOT NULL,
            thesis_state TEXT,
            decision_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_decisions_symbol_asof ON decisions(symbol, as_of);

        CREATE TABLE IF NOT EXISTS outcomes (
            outcome_id TEXT PRIMARY KEY,
            decision_id TEXT NOT NULL REFERENCES decisions(decision_id) ON DELETE CASCADE,
            evaluated_at TEXT NOT NULL,
            horizon_label TEXT,
            asset_return REAL,
            benchmark_return REAL,
            alpha REAL,
            actual_scenario TEXT,
            max_adverse_excursion REAL,
            max_favorable_excursion REAL,
            outcome_json TEXT NOT NULL,
            UNIQUE(decision_id, evaluated_at, horizon_label)
        );
        CREATE INDEX IF NOT EXISTS idx_outcomes_decision ON outcomes(decision_id);
        """
    )
    return conn


def record_decision(conn: sqlite3.Connection, decision: dict[str, Any]) -> str:
    decision_id = str(decision.get("decision_id") or uuid.uuid4())
    symbol = str(decision.get("symbol") or "").upper()
    as_of = str(decision.get("as_of") or "")
    evidence_hash = str(decision.get("evidence_freeze_hash") or "")
    if not symbol or not as_of or not evidence_hash:
        raise ValueError("decision requires symbol, as_of, and evidence_freeze_hash")
    conn.execute(
        "INSERT INTO decisions(decision_id,symbol,as_of,horizon,evidence_freeze_hash,thesis_state,decision_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
        (
            decision_id,
            symbol,
            as_of,
            decision.get("horizon"),
            evidence_hash,
            decision.get("thesis_state"),
            json.dumps({**decision, "decision_id": decision_id}, ensure_ascii=False, sort_keys=True),
            now_iso(),
        ),
    )
    conn.commit()
    return decision_id


def record_outcome(conn: sqlite3.Connection, decision_id: str, outcome: dict[str, Any]) -> str:
    exists = conn.execute("SELECT 1 FROM decisions WHERE decision_id=?", (decision_id,)).fetchone()
    if not exists:
        raise ValueError(f"unknown decision_id {decision_id}")
    asset = outcome.get("asset_return")
    bench = outcome.get("benchmark_return")
    alpha = outcome.get("alpha")
    if alpha is None and isinstance(asset, (int, float)) and isinstance(bench, (int, float)):
        alpha = float(asset) - float(bench)
    outcome_id = str(outcome.get("outcome_id") or uuid.uuid4())
    conn.execute(
        "INSERT INTO outcomes(outcome_id,decision_id,evaluated_at,horizon_label,asset_return,benchmark_return,alpha,actual_scenario,max_adverse_excursion,max_favorable_excursion,outcome_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            outcome_id,
            decision_id,
            outcome.get("evaluated_at") or now_iso(),
            outcome.get("horizon_label"),
            asset,
            bench,
            alpha,
            outcome.get("actual_scenario"),
            outcome.get("max_adverse_excursion"),
            outcome.get("max_favorable_excursion"),
            json.dumps({**outcome, "outcome_id": outcome_id, "alpha": alpha}, ensure_ascii=False, sort_keys=True),
        ),
    )
    conn.commit()
    return outcome_id


def _probabilities(decision: dict[str, Any]) -> dict[str, float] | None:
    scenarios = decision.get("scenarios") or {}
    values: dict[str, float] = {}
    for name in ("bear", "base", "bull", "unknown"):
        entry = scenarios.get(name)
        p = entry.get("probability") if isinstance(entry, dict) else None
        if not isinstance(p, (int, float)):
            return None
        values[name] = float(p)
    if abs(sum(values.values()) - 1.0) > 1e-6:
        return None
    return values


def calibration_summary(conn: sqlite3.Connection, symbol: str | None = None) -> dict[str, Any]:
    query = """
        SELECT d.decision_json, o.actual_scenario, o.asset_return, o.alpha,
               o.max_adverse_excursion, o.max_favorable_excursion
        FROM decisions d JOIN outcomes o ON d.decision_id=o.decision_id
    """
    params: tuple[Any, ...] = ()
    if symbol:
        query += " WHERE d.symbol=?"
        params = (symbol.upper(),)
    rows = conn.execute(query, params).fetchall()
    brier_values: list[float] = []
    scenario_counts = {k: {"predicted_probability_sum": 0.0, "actual_count": 0, "qualified_count": 0} for k in ("bear", "base", "bull", "unknown")}
    asset_returns: list[float] = []
    alphas: list[float] = []
    for row in rows:
        decision = json.loads(row["decision_json"])
        probs = _probabilities(decision)
        actual = row["actual_scenario"]
        if probs and actual in probs:
            brier = sum((p - (1.0 if name == actual else 0.0)) ** 2 for name, p in probs.items())
            brier_values.append(brier)
            for name, p in probs.items():
                scenario_counts[name]["predicted_probability_sum"] += p
                scenario_counts[name]["qualified_count"] += 1
                if name == actual:
                    scenario_counts[name]["actual_count"] += 1
        if isinstance(row["asset_return"], (int, float)):
            asset_returns.append(float(row["asset_return"]))
        if isinstance(row["alpha"], (int, float)):
            alphas.append(float(row["alpha"]))
    calibration = {}
    for name, values in scenario_counts.items():
        n = values["qualified_count"]
        calibration[name] = {
            "observations": n,
            "mean_predicted_probability": values["predicted_probability_sum"] / n if n else None,
            "actual_frequency": values["actual_count"] / n if n else None,
        }
    return {
        "outcomes": len(rows),
        "scenario_scored_outcomes": len(brier_values),
        "mean_multiclass_brier_score": sum(brier_values) / len(brier_values) if brier_values else None,
        "scenario_calibration": calibration,
        "mean_asset_return": sum(asset_returns) / len(asset_returns) if asset_returns else None,
        "mean_alpha": sum(alphas) / len(alphas) if alphas else None,
        "note": "Calibration is descriptive; use comparable horizons/regimes and enough observations before treating it as skill evidence.",
    }

