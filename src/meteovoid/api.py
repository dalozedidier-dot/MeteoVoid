from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, Query

from .utils import make_redis

app = FastAPI()
r = make_redis("redis://redis:6379/0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/latest")
def latest(station_id: str = Query(...), variable: str = Query(...)) -> dict[str, Any]:
    key = f"meteovoid:latest:{station_id}:{variable}"
    raw = r.get(key)
    if raw is None:
        return {"status": "not_found"}

    payload: Any = json.loads(raw)
    if isinstance(payload, dict):
        return payload

    return {"status": "invalid_payload"}
