from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from typing import Iterator

from .stream import make_redis, stream_observations


def synthetic_wind_gust_series(
    *,
    start: datetime,
    seconds: int,
    interval_s: int = 60,
    base: float = 8.0,
    seed: int = 7,
) -> Iterator[dict]:
    """Generate a stable -> transition -> unstable synthetic gust time series."""
    rng = random.Random(seed)
    n = max(int(seconds // interval_s), 1)

    for i in range(n):
        t = start + timedelta(seconds=i * interval_s)
        phase = i / max(n - 1, 1)

        # Stable: low variance
        if phase < 0.45:
            sigma = 0.6
            drift = 0.0
        # Transition: variance increases + slight drift
        elif phase < 0.75:
            sigma = 1.8
            drift = 0.02 * (i - 0.45 * n)
        # Unstable: high variance + bursts
        else:
            sigma = 3.5
            drift = 0.05 * (i - 0.75 * n)

        burst = 0.0
        if phase > 0.80 and rng.random() < 0.15:
            burst = rng.uniform(6.0, 14.0)

        seasonal = 1.2 * math.sin(2 * math.pi * i / 24.0)
        value = base + seasonal + drift + rng.gauss(0.0, sigma) + burst

        yield {
            "ts": t.isoformat().replace("+00:00", "Z"),
            "station_id": "DEMO_BE_0001",
            "lat": 50.85,
            "lon": 4.35,
            "variable": "wind_gust_ms",
            "value": round(float(value), 3),
            "quality": 0.98,
        }


def publish_synthetic(
    *,
    redis_url: str,
    stream: str,
    seconds: int = 3 * 3600,
    interval_s: int = 60,
    seed: int = 7,
) -> None:
    r = make_redis(redis_url)
    start = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    for obs in synthetic_wind_gust_series(start=start, seconds=seconds, interval_s=interval_s, seed=seed):
        stream_observations(r, stream, obs)
