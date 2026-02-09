from typing import Any, Dict
import json
from fastapi import FastAPI, Query
from redis import Redis

app = FastAPI(title="MeteoVoid Live API")

def make_redis(url: str) -> Redis:
    return Redis.from_url(url, decode_responses=True)

REDIS_URL = "redis://redis:6379/0"
r = make_redis(REDIS_URL)


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/latest")
def latest(
    station_id: str = Query(...),
    variable: str = Query(...),
) -> Dict[str, Any]:
    key = f"meteovoid:latest:{station_id}:{variable}"
    raw = r.get(key)

    if raw is None:
        return {"status": "not_found"}

    return json.loads(raw)
