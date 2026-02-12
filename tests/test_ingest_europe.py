from __future__ import annotations

from typing import Any

import pytest

from meteovoid.ingest_europe import _build_openmeteo_url, _extract_current, ingest_once
from meteovoid.stations_config import StationSpec


class FakeRedis:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[Any, Any]]] = []

    def xadd(self, stream: str, fields: dict[Any, Any], **kwargs: Any) -> str:  # noqa: ANN401
        self.calls.append((stream, dict(fields)))
        return "0-1"


def test_build_openmeteo_url_contains_expected_query() -> None:
    st = StationSpec(
        station_id="BE_UCCLE",
        name="Uccle",
        region="belgium",
        lat=50.8,
        lon=4.35,
        source="openmeteo",
        variables=["wind_gusts_10m", "wind_speed_10m"],
    )
    url = _build_openmeteo_url(st)
    assert url.startswith("https://api.open-meteo.com/v1/forecast?")
    assert "latitude=50.800000" in url
    assert "longitude=4.350000" in url
    assert (
        "current=wind_gusts_10m%2Cwind_speed_10m" in url
        or "current=wind_gusts_10m,wind_speed_10m" in url
    )


def test_extract_current_handles_missing_or_invalid_payload() -> None:
    ts, cur = _extract_current({})
    assert ts is None
    assert cur == {}

    ts2, cur2 = _extract_current({"current": {"time": 123, "x": "1.5", "bad": "nope"}})
    assert ts2 == 123
    assert cur2["x"] == pytest.approx(1.5)
    assert "bad" not in cur2


def test_ingest_once_publishes_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    st = StationSpec(
        station_id="BE_UCCLE",
        name="Uccle",
        region="belgium",
        lat=50.8,
        lon=4.35,
        source="openmeteo",
        variables=["wind_gusts_10m", "wind_speed_10m"],
    )

    def fake_http_json(url: str, timeout_s: float = 8.0) -> dict[str, Any]:  # noqa: ARG001
        return {"current": {"time": 123, "wind_gusts_10m": 12.0, "wind_speed_10m": 7.5}}

    monkeypatch.setattr("meteovoid.ingest_europe._http_json", fake_http_json)

    r = FakeRedis()
    res = ingest_once(r=r, station=st, out_stream="meteovoid:observations", per_stream=False)
    assert res["ok"] is True
    assert res["published"] == 2
    assert len(r.calls) == 2
    assert all(call[0] == "meteovoid:observations" for call in r.calls)


def test_ingest_once_per_stream_writes_extra_streams(monkeypatch: pytest.MonkeyPatch) -> None:
    st = StationSpec(
        station_id="BE_UCCLE",
        name="Uccle",
        region="belgium",
        lat=50.8,
        lon=4.35,
        source="openmeteo",
        variables=["wind_gusts_10m"],
    )

    def fake_http_json(url: str, timeout_s: float = 8.0) -> dict[str, Any]:  # noqa: ARG001
        return {"current": {"time": 123, "wind_gusts_10m": 12.0}}

    monkeypatch.setattr("meteovoid.ingest_europe._http_json", fake_http_json)

    r = FakeRedis()
    res = ingest_once(r=r, station=st, out_stream="meteovoid:observations", per_stream=True)
    assert res["published"] == 1
    assert len(r.calls) == 2
    assert r.calls[0][0] == "meteovoid:observations"
    assert r.calls[1][0] == "meteovoid:observations:BE_UCCLE:wind_gusts_10m"


def test_ingest_once_unsupported_source() -> None:
    st = StationSpec(
        station_id="X",
        name="X",
        region="default",
        lat=0.0,
        lon=0.0,
        source="other",
        variables=["a"],
    )
    r = FakeRedis()
    res = ingest_once(r=r, station=st, out_stream="meteovoid:observations", per_stream=False)
    assert res["ok"] is False
    assert "unsupported" in str(res["error"])
