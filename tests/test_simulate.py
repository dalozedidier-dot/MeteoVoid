from __future__ import annotations

from datetime import UTC, datetime

from meteovoid.simulate import synthetic_series


def test_synthetic_series_generates_points() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    pts = synthetic_series(start=start, steps=10, dt_s=1.0, station_id="X", variable="wind", seed=0)

    assert len(pts) == 10
    assert pts[0]["station_id"] == "X"
    assert pts[0]["variable"] == "wind"
    assert isinstance(pts[0]["value"], float)

    assert pts[1]["ts"] > pts[0]["ts"]
