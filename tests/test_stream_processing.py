from __future__ import annotations

from datetime import UTC, datetime

from meteovoid.live import LiveConfig
from meteovoid.stream import process_observation


def test_process_observation_emits_report() -> None:
    cfg = LiveConfig(window_s=60, stable_threshold=0.05, unstable_threshold=0.20)
    windows = {}

    fields = {
        "ts": str(datetime(2026, 1, 1, tzinfo=UTC).timestamp()),
        "station_id": "S1",
        "variable": "wind_gust_ms",
        "value": "1.0",
    }
    r = process_observation(fields, "1-0", cfg, windows)
    assert r is not None
    assert r["station_id"] == "S1"
    assert r["variable"] == "wind_gust_ms"
    assert "score" in r and "state" in r


def test_process_observation_rejects_bad_payload() -> None:
    cfg = LiveConfig(window_s=60)
    windows = {}

    bad = {"ts": "0", "station_id": "", "variable": "x", "value": "1.0"}
    assert process_observation(bad, "1-0", cfg, windows) is None
