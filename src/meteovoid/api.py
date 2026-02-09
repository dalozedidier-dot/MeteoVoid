from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
import redis

app = FastAPI(title="MeteoVoid Live API", version="0.2.0")


def _make_redis(url: str) -> redis.Redis:
    return redis.Redis.from_url(url, decode_responses=True)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/latest")
def latest(
    station_id: str = Query(..., description="Station identifier"),
    variable: str = Query(..., description="Variable name"),
    redis_url: str = Query("redis://redis:6379/0", description="Redis URL"),
) -> dict[str, Any]:
    r = _make_redis(redis_url)
    key = f"meteovoid:latest:{station_id}:{variable}"
    payload = r.get(key)
    if payload is None:
        raise HTTPException(status_code=404, detail="No report found")
    return json.loads(payload)


@app.get("/stations")
def stations(
    pattern: str = Query("*", description="Pattern for station_id match, glob-style"),
    redis_url: str = Query("redis://redis:6379/0", description="Redis URL"),
) -> dict[str, Any]:
    r = _make_redis(redis_url)
    # Keys are meteovoid:latest:<station_id>:<variable>
    keys = r.keys(f"meteovoid:latest:{pattern}:*")
    stations: dict[str, set[str]] = {}
    for k in keys:
        parts = k.split(":")
        if len(parts) < 4:
            continue
        station = parts[2]
        var = parts[3]
        stations.setdefault(station, set()).add(var)
    return {"stations": {s: sorted(list(vs)) for s, vs in stations.items()}}
