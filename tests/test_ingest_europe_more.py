from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from urllib.error import URLError

import pytest

import meteovoid.ingest_europe as ie
from meteovoid.stations_config import StationSpec


class _FakeHTTPResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:  # noqa: ANN401
        return None


def test_http_json_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(req: Any, timeout: float = 8.0) -> _FakeHTTPResponse:  # noqa: ANN401,ARG001
        return _FakeHTTPResponse(b'{"ok": true, "x": 1}')

    monkeypatch.setattr(ie, "urlopen", fake_urlopen)
    obj = ie._http_json("http://example.test")
    assert obj["ok"] is True
    assert obj["x"] == 1


def test_http_json_rejects_non_object(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(req: Any, timeout: float = 8.0) -> _FakeHTTPResponse:  # noqa: ANN401,ARG001
        return _FakeHTTPResponse(b'[1, 2, 3]')

    monkeypatch.setattr(ie, "urlopen", fake_urlopen)
    with pytest.raises(ValueError):
        ie._http_json("http://example.test")


def test_main_once_runs_and_prints_summary(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    station = StationSpec(
        station_id="BE_UCCLE",
        name="Uccle",
        region="belgium",
        lat=50.8,
        lon=4.35,
        source="openmeteo",
        variables=["wind_gusts_10m"],
    )

    monkeypatch.setattr(ie, "load_stations_config", lambda _p: SimpleNamespace(stations=[station]))
    monkeypatch.setattr(ie.redis.Redis, "from_url", lambda *a, **k: object())

    def fake_ingest_once(*, r: Any, station: Any, out_stream: str, per_stream: bool) -> dict[str, Any]:  # noqa: ANN401,ARG001
        return {"station_id": station.station_id, "ok": True, "published": 1, "ts": 123, "vars": ["wind_gusts_10m"]}

    monkeypatch.setattr(ie, "ingest_once", fake_ingest_once)

    rc = ie.main(["--config", "config/stations_europe.yaml", "--once"])
    assert rc == 0

    out = capsys.readouterr().out.strip()
    obj = json.loads(out)
    assert obj["ok_stations"] == 1
    assert obj["stations"] == 1
    assert obj["published"] == 1


def test_main_once_handles_ingest_errors(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    station = StationSpec(
        station_id="BE_UCCLE",
        name="Uccle",
        region="belgium",
        lat=50.8,
        lon=4.35,
        source="openmeteo",
        variables=["wind_gusts_10m"],
    )

    monkeypatch.setattr(ie, "load_stations_config", lambda _p: SimpleNamespace(stations=[station]))
    monkeypatch.setattr(ie.redis.Redis, "from_url", lambda *a, **k: object())

    def boom(*, r: Any, station: Any, out_stream: str, per_stream: bool) -> dict[str, Any]:  # noqa: ANN401,ARG001
        raise URLError("network down")

    monkeypatch.setattr(ie, "ingest_once", boom)

    rc = ie.main(["--config", "config/stations_europe.yaml", "--once"])
    assert rc == 0

    out = capsys.readouterr().out.strip()
    obj = json.loads(out)
    assert obj["ok_stations"] == 0
    assert obj["stations"] == 1
    assert obj["published"] == 0
