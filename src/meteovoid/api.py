from __future__ import annotations

import json
import os
from typing import Any, cast

from fastapi import FastAPI, Query

from .utils import make_redis

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

app = FastAPI()


def _make_redis(url: str):
    # kept as a module-level hook for tests (monkeypatch).
    return make_redis(url)


def _get_redis():
    return _make_redis(REDIS_URL)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/stations")
def stations() -> dict[str, list[str]]:
    r = _get_redis()
    keys_any = r.keys("meteovoid:latest:*")
    keys = [str(k) for k in keys_any]
    station_ids: set[str] = set()
    for k in keys:
        parts = k.split(":")
        if len(parts) >= 4:
            station_ids.add(parts[2])
    return {"stations": sorted(station_ids)}


@app.get("/latest")
def latest(station_id: str = Query(...), variable: str = Query(...)) -> dict[str, Any]:
    r = _get_redis()
    key = f"meteovoid:latest:{station_id}:{variable}"
    raw_any = r.get(key)
    raw = cast(str | bytes | bytearray | None, raw_any)
    if raw is None:
        return {"status": "not_found"}

    payload: Any = json.loads(raw)
    if isinstance(payload, dict):
        return payload

    return {"status": "invalid_payload"}
