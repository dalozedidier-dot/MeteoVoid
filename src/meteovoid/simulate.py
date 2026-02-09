from __future__ import annotations

import random
import time

from redis.typing import EncodableT

from .utils import make_redis


def push_synthetic_stream(
    redis_url: str,
    stream: str,
    station_id: str,
    variable: str,
    steps: int,
    sleep: float,
) -> None:
    r = make_redis(redis_url)

    for _i in range(steps):
        fields: dict[EncodableT, EncodableT] = {
            "ts": f"{time.time():.6f}",
            "station_id": station_id,
            "variable": variable,
            "value": f"{random.random():.6f}",
        }
        r.xadd(stream, fields)
        time.sleep(sleep)
