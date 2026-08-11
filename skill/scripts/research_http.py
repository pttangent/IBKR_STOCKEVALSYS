#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def request_bytes(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    method: str = "GET",
    body: bytes | None = None,
    timeout: float = 30.0,
    retries: int = 2,
    backoff: float = 1.0,
) -> bytes:
    req_headers = {"Accept": "application/json", **(headers or {})}
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        request = Request(url, headers=req_headers, method=method, data=body)
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.read()
        except HTTPError as exc:
            last_error = exc
            # Retry only transient server/rate-limit errors. 4xx auth/shape errors should fail loudly.
            if exc.code not in {429, 500, 502, 503, 504} or attempt >= retries:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                raise RuntimeError(f"HTTP {exc.code} for {url}: {detail}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt >= retries:
                raise RuntimeError(f"Request failed for {url}: {exc}") from exc
        time.sleep(backoff * (2**attempt))
    raise RuntimeError(f"Request failed for {url}: {last_error}")


def request_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    method: str = "GET",
    payload: Any | None = None,
    timeout: float = 30.0,
    retries: int = 2,
) -> Any:
    body = None
    req_headers = dict(headers or {})
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    raw = request_bytes(
        url,
        headers=req_headers,
        method=method,
        body=body,
        timeout=timeout,
        retries=retries,
    )
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        preview = raw[:500].decode("utf-8", errors="replace")
        raise RuntimeError(f"Expected JSON from {url}, got: {preview}") from exc


def write_json(path: str | Path, payload: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def source_packet(
    *,
    provider: str,
    source_type: str,
    source_id: str,
    as_of: str | None,
    available_at: str | None,
    reliability: str,
    data: Any,
    source_url: str | None = None,
    warnings: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "source_id": source_id,
        "provider": provider,
        "source_type": source_type,
        "as_of": as_of,
        "available_at": available_at,
        "retrieved_at": utc_now_iso(),
        "reliability": reliability,
        "source_url": source_url,
        "warnings": warnings or [],
        "metadata": metadata or {},
        "data": data,
    }

