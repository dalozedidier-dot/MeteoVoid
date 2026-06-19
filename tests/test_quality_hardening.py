from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import meteovoid.api as api_mod
from meteovoid.core import interstation_spatial_consistency, scan_series_for_voids
from meteovoid.radar_cache import fetch_json_with_file_cache
from meteovoid.scoring import compute_composite_score
from meteovoid.stream import process_observation, run_live_worker


def test_scan_exposes_flatline_segments(tmp_path: Path) -> None:
    p = tmp_path / "flat.csv"
    rows = ["timestamp,value"]
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(8):
        rows.append(f"{(base + timedelta(minutes=i)).isoformat()},{12.0}")
    p.write_text("\n".join(rows) + "\n", encoding="utf-8")

    report = scan_series_for_voids(p, flatline_min_run=5)

    assert report["flatline_count"] == 1
    assert report["flatlines"][0]["run_length"] == 8


def test_core_interstation_spatial_consistency_flags_sensor_drift() -> None:
    rows = [
        {"timestamp": "t0", "station_id": "A", "value": 10.0},
        {"timestamp": "t0", "station_id": "B", "value": 10.2},
        {"timestamp": "t0", "station_id": "C", "value": 9.9},
        {"timestamp": "t0", "station_id": "D", "value": 40.0},
    ]

    out = interstation_spatial_consistency(rows, min_peer_count=2, z_threshold=3.0)

    assert out["flag_count"] >= 1
    assert any(flag["station_id"] == "D" for flag in out["flags"])


def test_scoring_uses_month_specific_thresholds() -> None:
    samples = [
        (datetime(2026, 7, 1, 12, i, tzinfo=UTC), float(v))
        for i, v in enumerate([10, 10, 10, 10, 10, 13, 10, 10, 10, 10])
    ]
    values = [v for _t, v in samples]

    score = compute_composite_score(
        samples=samples,
        values=values,
        window_s=600,
        missing_time_frac=0.0,
        overrides={
            "outlier_z_thresh": 3.5,
            "seasonal_thresholds": {"outlier_z_thresh": {"summer": 8.0}},
        },
    )

    assert score.meta["seasonality"]["month"] == 7
    assert score.meta["seasonality"]["outlier_z_thresh"] == 8.0
    assert score.meta["seasonality"]["outlier_z_source"] == "seasonal:summer"


def test_stream_adds_spatial_std_context() -> None:
    windows: dict[tuple[str, str], Any] = {}
    peer_state = {"temperature": {"B": 10.0, "C": 10.5, "D": 9.5}}

    report = process_observation(
        {"station_id": "A", "variable": "temperature", "value": "16", "ts": "0"},
        windows=windows,
        peer_state=peer_state,
    )

    assert report is not None
    ctx = report["stats"]["spatial_context"]
    assert ctx["available"] is True
    assert ctx["peer_count"] == 3
    assert ctx["peer_std"] > 0


class FakeRedisForWorker:
    def __init__(self) -> None:
        self.streams: dict[str, list[tuple[str, dict[str, str]]]] = {
            "meteovoid:observations": [("1-0", {"station_id": "S1", "variable": "temperature"})]
        }
        self.added: list[tuple[str, dict[str, str]]] = []

    def xread(
        self,
        streams: dict[str, str],
        block: int,  # noqa: ARG002
        count: int,  # noqa: ARG002
    ) -> list[tuple[str, list[tuple[str, dict[str, str]]]]]:
        name = next(iter(streams))
        items = self.streams.get(name, [])
        self.streams[name] = []
        return [(name, items)] if items else []

    def xadd(self, stream: str, fields: dict[str, str]) -> str:
        self.added.append((stream, dict(fields)))
        return "2-0"

    def set(self, key: str, value: str) -> None:  # pragma: no cover
        pass


def test_live_worker_dead_letters_invalid_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRedisForWorker()
    monkeypatch.setattr("meteovoid.stream.make_redis", lambda _url: fake)
    monkeypatch.setattr("meteovoid.stream.load_station_config", lambda _path: None)
    monkeypatch.setattr("meteovoid.stream._db.ensure_schema", lambda: None)

    run_live_worker(
        "redis://x",
        "meteovoid:observations",
        "meteovoid:reports",
        max_messages=1,
        max_idle_s=0.01,
    )

    assert fake.added
    stream, fields = fake.added[0]
    assert stream == "meteovoid:observations:dlq"
    assert fields["reason"] == "invalid_payload"


def test_api_rate_limit_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    class EmptyRedis:
        def keys(self, _pattern: str) -> list[str]:
            return []

        def get(self, _key: str) -> None:
            return None

    monkeypatch.setattr(api_mod, "_make_redis", lambda _url: EmptyRedis())
    monkeypatch.setattr(api_mod, "RATE_LIMIT_PER_MINUTE", 1)
    api_mod._RATE_BUCKETS.clear()
    client = TestClient(api_mod.app)

    first = client.get("/stations")
    second = client.get("/stations")

    assert first.status_code == 200
    assert second.status_code == 429
    monkeypatch.setattr(api_mod, "RATE_LIMIT_PER_MINUTE", 240)
    api_mod._RATE_BUCKETS.clear()


def test_radar_cache_uses_cached_payload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"ok": true}'

    def fake_urlopen(_request: object, timeout: float) -> FakeResponse:  # noqa: ARG001
        calls["count"] += 1
        return FakeResponse()

    monkeypatch.setattr("meteovoid.radar_cache.urlopen", fake_urlopen)

    one = fetch_json_with_file_cache("https://example.test/radar.json", cache_dir=tmp_path)
    two = fetch_json_with_file_cache("https://example.test/radar.json", cache_dir=tmp_path)

    assert one["_cache"]["status"] == "miss"
    assert two["_cache"]["status"] == "hit"
    assert calls["count"] == 1
