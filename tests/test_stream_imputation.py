from __future__ import annotations

from datetime import UTC, datetime, timedelta

from meteovoid.live import LiveConfig
from meteovoid.stream import process_observation


def test_imputation_stats_added_when_gaps() -> None:
    cfg = LiveConfig(
        window_s=60,
        stable_threshold=0.05,
        unstable_threshold=0.20,
        max_gap_s=3.0,
        impute_mode="ffill",
        use_imputed_for_score=True,
        max_imputed_frac=0.10,
        max_impute_points=100,
    )
    windows = {}

    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    t1 = t0 + timedelta(seconds=1)
    t2 = t0 + timedelta(seconds=11)

    fields0 = {"ts": str(t0.timestamp()), "station_id": "S1", "variable": "x", "value": "1.0"}
    fields1 = {"ts": str(t1.timestamp()), "station_id": "S1", "variable": "x", "value": "1.0"}
    fields2 = {"ts": str(t2.timestamp()), "station_id": "S1", "variable": "x", "value": "1.0"}

    assert process_observation(fields0, "1-0", cfg, windows) is not None
    assert process_observation(fields1, "2-0", cfg, windows) is not None

    r = process_observation(fields2, "3-0", cfg, windows)
    assert r is not None
    stats = r["stats"]
    assert stats["gap_count"] >= 1
    assert stats["impute_mode"] == "ffill"
    assert stats["imputed_points"] > 0
    assert stats["imputed_frac"] > 0.0
    assert "meteo" in r
    assert "imputed" in r["meteo"]["flags"]
