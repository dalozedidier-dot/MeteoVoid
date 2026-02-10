from __future__ import annotations

import json
import os
from typing import Any, Protocol, cast

from fastapi import FastAPI

from .utils import make_redis

REDIS_URL_DEFAULT = os.getenv("REDIS_URL", "redis://redis:6379/0")


class RedisLike(Protocol):
    def get(self, key: str) -> str | bytes | bytearray | None: ...
    def keys(self, pattern: str) -> list[Any]: ...


def _make_redis(url: str) -> RedisLike:
    # kept as a module-level hook for tests (monkeypatch).
    return make_redis(url)


def latest(station_id: str, variable: str, redis_url: str = REDIS_URL_DEFAULT) -> dict[str, Any]:
    r = _make_redis(redis_url)
    key = f"meteovoid:latest:{station_id}:{variable}"
    raw = r.get(key)
    if raw is None:
        return {"status": "not_found"}

    payload_any: Any = json.loads(raw)
    if isinstance(payload_any, dict):
        return cast(dict[str, Any], payload_any)

    return {"status": "invalid_payload"}


def stations(pattern: str = "meteovoid:latest:*", redis_url: str = REDIS_URL_DEFAULT) -> dict[str, dict[str, list[str]]]:
    r = _make_redis(redis_url)
    keys = [str(k) for k in r.keys(pattern)]

    grouped: dict[str, set[str]] = {}
    for k in keys:
        parts = k.split(":")
        if len(parts) < 4:
            continue
        if parts[0] != "meteovoid" or parts[1] != "latest":
            continue
        station_id = parts[2]
        variable = ":".join(parts[3:])
        grouped.setdefault(station_id, set()).add(variable)

    return {"stations": {sid: sorted(vars_) for sid, vars_ in grouped.items()}}


app = FastAPI()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/latest")
def latest_http(station_id: str, variable: str) -> dict[str, Any]:
    return latest(station_id=station_id, variable=variable, redis_url=REDIS_URL_DEFAULT)


@app.get("/stations")
def stations_http(pattern: str = "meteovoid:latest:*") -> dict[str, dict[str, list[str]]]:
    return stations(pattern=pattern, redis_url=REDIS_URL_DEFAULT)
