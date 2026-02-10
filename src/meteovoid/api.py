from __future__ import annotations

import json
import os
from typing import Any, Protocol, cast

from fastapi import FastAPI, Query

from .utils import make_redis

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")


class RedisLike(Protocol):
    def get(self, key: str) -> str | bytes | bytearray | None: ...

    def keys(self, pattern: str) -> list[Any]: ...


def _make_redis(url: str) -> RedisLike:
    """Module-level hook, monkeypatched in tests."""
    return cast(RedisLike, make_redis(url))


def latest(station_id: str, variable: str, redis_url: str = REDIS_URL) -> dict[str, Any]:
    r = _make_redis(redis_url)
    key = f"meteovoid:latest:{station_id}:{variable}"
    raw = r.get(key)
    if raw is None:
        return {"status": "not_found"}

    try:
        payload: Any = json.loads(raw)
    except json.JSONDecodeError:
        return {"status": "invalid_payload"}

    return payload if isinstance(payload, dict) else {"status": "invalid_payload"}


def stations(pattern: str = "*", redis_url: str = REDIS_URL) -> dict[str, dict[str, list[str]]]:
    r = _make_redis(redis_url)
    keys_any = r.keys(pattern)

    keys = [
        k.decode("utf-8") if isinstance(k, bytes | bytearray) else str(k)
        for k in keys_any
        if str(k).startswith("meteovoid:latest:")
    ]

    out: dict[str, list[str]] = {}
    for k in keys:
        parts = k.split(":")
        if len(parts) < 4:
            continue
        station_id = parts[2]
        variable = ":".join(parts[3:])
        out.setdefault(station_id, [])
        if variable not in out[station_id]:
            out[station_id].append(variable)

    for sid in out:
        out[sid].sort()

    return {"stations": out}


app = FastAPI()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/stations")
def stations_http(pattern: str = Query("*")) -> dict[str, dict[str, list[str]]]:  # pragma: no cover
    return stations(pattern=pattern, redis_url=REDIS_URL)


@app.get("/latest")
def latest_http(
    station_id: str = Query(...),
    variable: str = Query(...),
) -> dict[str, Any]:  # pragma: no cover
    return latest(station_id=station_id, variable=variable, redis_url=REDIS_URL)
