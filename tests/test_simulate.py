from __future__ import annotations

from datetime import datetime, timezone

from meteovoid.simulate import synthetic_wind_gust_series


def test_synthetic_series_generates_points() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    points = list(synthetic_wind_gust_series(start=start, seconds=3600, interval_s=60, seed=1))
    assert len(points) == 60
    assert points[0]["station_id"] == "DEMO_BE_0001"
    assert points[0]["variable"] == "wind_gust_ms"
