from __future__ import annotations

from datetime import UTC, datetime

import meteovoid.simulate as sim
from meteovoid.simulate import synthetic_series


def test_synthetic_series_generates_points() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    pts = synthetic_series(start=start, steps=10, dt_s=1.0, station_id="X", variable="wind", seed=0)

    assert len(pts) == 10
    assert pts[0]["station_id"] == "X"
    assert pts[0]["variable"] == "wind"
    assert isinstance(pts[0]["value"], float)

    assert pts[1]["ts"] > pts[0]["ts"]


def test_push_synthetic_stream_writes_xadd(monkeypatch) -> None:
    calls = []

    class FakeRedis:
        def xadd(self, stream, fields):  # noqa: ANN001
            calls.append((stream, fields))

    monkeypatch.setattr(sim, "make_redis", lambda _url: FakeRedis())

    sim.push_synthetic_stream(
        redis_url="redis://example/0",
        stream="meteovoid:observations",
        station_id="S1",
        variable="wind",
        steps=3,
        sleep=0.0,
    )

    assert len(calls) == 3
    assert calls[0][0] == "meteovoid:observations"
    assert calls[0][1]["station_id"] == "S1"
