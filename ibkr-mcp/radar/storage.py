from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from queue import Empty, Full, Queue
from typing import Any


DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "realtime_radar.sqlite3"


class RadarStore:
    """Append-only local store for replay/audit without blocking the market-data loop."""

    def __init__(self, path: str | Path | None = None) -> None:
        configured = path or os.environ.get("IBKR_RADAR_DB")
        self.path = Path(configured).expanduser() if configured else DEFAULT_DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._queue: Queue[tuple[str, dict[str, Any]] | None] = Queue(maxsize=200_000)
        self._closed = False
        self._session_id: str | None = None
        self._lock = threading.RLock()
        self._written_events = 0
        self._written_snapshots = 0
        self._dropped = 0
        self._last_write_at: float | None = None
        self._init_schema()
        self._writer = threading.Thread(target=self._writer_loop, name="radar-store", daemon=True)
        self._writer.start()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.path), timeout=30)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        con.execute("PRAGMA busy_timeout=30000")
        return con

    def _init_schema(self) -> None:
        with self._connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    started_at REAL NOT NULL,
                    ended_at REAL,
                    symbols_json TEXT NOT NULL,
                    plan_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    event_time REAL NOT NULL,
                    received_time REAL NOT NULL,
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_radar_events_symbol_time ON events(symbol,event_time);
                CREATE INDEX IF NOT EXISTS idx_radar_events_session_time ON events(session_id,event_time);
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    generated_at REAL NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_radar_snapshots_session_time ON snapshots(session_id,generated_at);
                """
            )

    def begin_session(self, symbols: list[str], plan: dict[str, Any]) -> str:
        self.end_session()
        session_id = uuid.uuid4().hex
        with self._lock:
            self._session_id = session_id
            self._written_events = 0
            self._written_snapshots = 0
            self._dropped = 0
        self._enqueue("session_start", {"session_id": session_id, "started_at": time.time(), "symbols": symbols, "plan": plan})
        return session_id

    def end_session(self) -> None:
        with self._lock:
            session_id = self._session_id
        if not session_id:
            return
        self._enqueue("session_end", {"session_id": session_id, "ended_at": time.time()})
        self.flush()
        with self._lock:
            if self._session_id == session_id:
                self._session_id = None

    def record_event(self, symbol: str, kind: str, event_time: float, payload: dict[str, Any]) -> None:
        with self._lock:
            session_id = self._session_id
        if not session_id:
            return
        self._enqueue("event", {"session_id": session_id, "symbol": symbol, "event_time": float(event_time), "received_time": time.time(), "kind": kind, "payload": payload})

    def record_snapshot(self, payload: dict[str, Any]) -> None:
        with self._lock:
            session_id = self._session_id
        if not session_id:
            return
        self._enqueue("snapshot", {"session_id": session_id, "generated_at": time.time(), "payload": payload})

    def info(self) -> dict[str, Any]:
        with self._lock:
            return {"path": str(self.path), "sessionId": self._session_id, "writtenEvents": self._written_events, "writtenSnapshots": self._written_snapshots, "queueDepth": self._queue.qsize(), "dropped": self._dropped, "lastWriteAt": self._last_write_at}

    def flush(self, timeout: float = 3.0) -> None:
        deadline = time.time() + timeout
        while self._queue.qsize() and time.time() < deadline:
            time.sleep(0.02)

    def close(self) -> None:
        if self._closed:
            return
        self.end_session()
        self._closed = True
        try:
            self._queue.put_nowait(None)
        except Full:
            pass
        self._writer.join(timeout=3)

    def _enqueue(self, kind: str, payload: dict[str, Any]) -> None:
        try:
            self._queue.put_nowait((kind, payload))
        except Full:
            with self._lock:
                self._dropped += 1

    def _writer_loop(self) -> None:
        con = self._connect()
        pending = 0
        try:
            while True:
                try:
                    item = self._queue.get(timeout=0.5)
                except Empty:
                    item = "timeout"
                if item is None:
                    break
                if item == "timeout":
                    if pending:
                        con.commit()
                        pending = 0
                    continue
                kind, payload = item
                if kind == "session_start":
                    con.execute("INSERT OR REPLACE INTO sessions(session_id,started_at,symbols_json,plan_json) VALUES(?,?,?,?)", (payload["session_id"], payload["started_at"], json.dumps(payload["symbols"], separators=(",", ":")), json.dumps(payload["plan"], separators=(",", ":"))))
                elif kind == "session_end":
                    con.execute("UPDATE sessions SET ended_at=? WHERE session_id=?", (payload["ended_at"], payload["session_id"]))
                elif kind == "event":
                    con.execute("INSERT INTO events(session_id,symbol,event_time,received_time,kind,payload_json) VALUES(?,?,?,?,?,?)", (payload["session_id"], payload["symbol"], payload["event_time"], payload["received_time"], payload["kind"], json.dumps(payload["payload"], ensure_ascii=False, separators=(",", ":"))))
                    with self._lock:
                        self._written_events += 1
                elif kind == "snapshot":
                    con.execute("INSERT INTO snapshots(session_id,generated_at,payload_json) VALUES(?,?,?)", (payload["session_id"], payload["generated_at"], json.dumps(payload["payload"], ensure_ascii=False, separators=(",", ":"))))
                    with self._lock:
                        self._written_snapshots += 1
                pending += 1
                with self._lock:
                    self._last_write_at = time.time()
                if pending >= 250:
                    con.commit()
                    pending = 0
            if pending:
                con.commit()
        finally:
            con.close()
