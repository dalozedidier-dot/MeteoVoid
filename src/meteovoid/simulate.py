from __future__ import annotations

import random
import time
from datetime import datetime, timedelta
from typing import Any

from redis.typing import EncodableT

from .utils import make_redis


def synthetic_series(
    start: datetime,
    steps: int = 200,
    dt_s: float = 1.0,
    station_id: str = "DEMO",
    variable: str = "wind",
    seed: int | None = 0,
) -> list[dict[str, Any]]:
    """Generate a deterministic synthetic series (handy for tests + smoke)."""
    if start.tzinfo is None:
        raise ValueError("start must be timezone-aware")

    if steps <= 0:
        return []

    rng = random.Random(seed) if seed is not None else random.Random()

    out: list[dict[str, Any]] = []
    for i in range(steps):
        ts = start + timedelta(seconds=i * dt_s)
        out.append(
            {
                "ts": ts.timestamp(),
                "station_id": station_id,
                "variable": variable,
                "value": float(rng.random()),
            }
        )
    return out


def push_synthetic_stream(
    redis_url: str,
    stream: str,
    station_id: str,
    variable: str,
    steps: int,
    sleep: float,
) -> None:
    r = make_redis(redis_url)

    # deterministic enough for CI; timestamps are current wallclock
    start = datetime.now(tz=datetime.now().astimezone().tzinfo)
    series = synthetic_series(start=start, steps=steps, dt_s=max(0.001, sleep), station_id=station_id, variable=variable)

    for point in series:
        fields: dict[EncodableT, EncodableT] = {
            "ts": f"{float(point['ts']):.6f}",
            "station_id": str(point["station_id"]),
            "variable": str(point["variable"]),
            "value": f"{float(point['value']):.6f}",
        }
        r.xadd(stream, fields)
        time.sleep(sleep)
