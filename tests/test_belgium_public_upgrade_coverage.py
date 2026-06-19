from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from meteovoid.belgium import bulletin_5days as b5
from meteovoid.belgium import official_geodata as geo
from meteovoid.belgium import validation_history as vh


def test_bulletin_helpers_cover_edge_cases(tmp_path: Path) -> None:
    assert b5._as_float(None) is None
    assert b5._as_float("") is None
    assert b5._as_float("nan") is None
    assert b5._as_float("bad") is None
    assert b5._round("12.345", 1) == 12.3
    assert b5._dict_or_empty([]) == {}
    assert b5._list_or_empty({}) == []

    assert b5._load_zone_config(tmp_path / "missing.yaml")[0].key == "coast"

    zones_yaml = tmp_path / "zones.yaml"
    zones_yaml.write_text(
        """
zones:
  - key: custom
    label: Zone custom
    lat: 50.1
    lon: 4.2
    province_group: Test
  - key: broken
    lat: bad
    lon: 4.0
  - not-a-dict
""".strip(),
        encoding="utf-8",
    )
    zones = b5._load_zone_config(zones_yaml)
    assert zones == [b5.ForecastZone("custom", "Zone custom", 50.1, 4.2, "Test")]

    labels = {
        0: "temps généralement ensoleillé",
        2: "alternance de soleil et de nuages",
        45: "brume ou brouillard par moments",
        53: "bruine ou faibles précipitations",
        63: "averses ou pluie par moments",
        75: "précipitations hivernales possibles",
        96: "risque d’orages",
        999: "temps variable",
    }
    for code, expected in labels.items():
        assert b5._weather_code_label(code) == expected

    assert "orageuses" in b5._risk_note(
        {"weather_code": 95, "temperature_2m_max": 31, "wind_gusts_10m_max": 60}
    )
    assert b5._risk_note({"weather_code": 2}) == "pas de signal météo marqué dans le bulletin brut"


def test_bulletin_live_transform_and_error_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    zone = b5.ForecastZone("test", "Test", 50.0, 4.0, "X")
    payload: dict[str, Any] = {
        "daily": {
            "time": ["2026-06-19", "2026-06-20"],
            "weather_code": [2, 95],
            "temperature_2m_max": [25.2, 31.4],
            "temperature_2m_min": [13.1, 17.2],
            "precipitation_probability_max": [20, 80],
            "wind_gusts_10m_max": [30, 62],
        },
        "hourly": {
            "dew_point_2m": [12, None, "bad", 19.4],
            "cape": [0, 1234.4],
            "convective_inhibition": [-25, -80],
            "lifted_index": [2.0, -4.2],
            "total_column_integrated_water_vapour": [22.1, 36.6],
            "pressure_msl": [1012.4, 1007.8],
            "relative_humidity_2m": [55, 91],
        },
    }

    seen: dict[str, Any] = {}

    def fake_fetch(url: str, *, timeout_s: float) -> dict[str, Any]:
        seen["url"] = url
        seen["timeout"] = timeout_s
        return payload

    monkeypatch.setattr(b5, "_fetch_json", fake_fetch)
    live = b5._zone_live_forecast(
        zone, model="icon_seamless", timezone="Europe/Brussels", days=3, timeout_s=1.5
    )
    assert live["source"] == "Open-Meteo Forecast API"
    assert "models=icon_seamless" in seen["url"]
    assert seen["timeout"] == 1.5
    assert len(live["days"]) == 2
    assert live["convective_extremes"]["cape_max_j_kg"] == 1234.0

    assert "models=" not in b5._openmeteo_url(
        zone, model="best_match", timezone="UTC", days=1
    )
    assert b5._hourly_extremes({})["dew_point_max_c"] is None
    assert b5._day_from_daily({"time": ["2026-01-01"], "ignored": "x"}, 0)[
        "weather_label"
    ]
    assert b5._national_days([], days=2) == []
    assert b5._summary_text([]) == "Bulletin 5 jours indisponible pour le moment."

    calls = {"n": 0}

    def fake_zone_live_forecast(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls["n"] += 1
        if calls["n"] == 1:
            raise b5.BulletinError("boom")
        return b5._offline_zone_forecast(args[0], days=2)

    monkeypatch.setattr(b5, "_zone_live_forecast", fake_zone_live_forecast)
    built = b5.build_bulletin_5days(days=10, offline_demo=False)
    assert built["days_requested"] == 7
    assert built["errors"][0]["error"] == "boom"
    assert built["zones_count"] == len(b5.DEFAULT_ZONES) - 1

    md = b5.render_bulletin_markdown(
        {"national_days": ["skip"], "zones": ["skip"], "disclaimer": "ok"}
    )
    assert "ok" in md


class _FakeResponse:
    def __init__(self, payload: str) -> None:
        self.payload = payload

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload.encode("utf-8")


def test_fetch_json_rejects_non_object(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(b5, "urlopen", lambda *args, **kwargs: _FakeResponse("[]"))
    with pytest.raises(b5.BulletinError):
        b5._fetch_json("https://example.test", timeout_s=1)

    monkeypatch.setattr(b5, "urlopen", lambda *args, **kwargs: _FakeResponse('{"ok": true}'))
    assert b5._fetch_json("https://example.test", timeout_s=1) == {"ok": True}


def test_geodata_download_and_fallback_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fallback = tmp_path / "fallback.geojson"
    fc = {"type": "FeatureCollection", "features": []}
    fallback.write_text(json.dumps(fc), encoding="utf-8")

    def fake_fetch(url: str, *, timeout_s: float) -> dict[str, Any]:
        if "municipality" in url:
            raise RuntimeError("too heavy")
        return fc

    monkeypatch.setattr(geo, "_fetch_json", fake_fetch)
    status = geo.prepare_belgium_geodata(
        out_dir=tmp_path / "out",
        fallback_province_geojson=fallback,
        province_url="https://example.test/province",
        municipality_url="https://example.test/municipality",
        offline=False,
    )
    assert status["layers"][0]["status"] == "downloaded"
    assert status["layers"][1]["status"] == "unavailable"

    monkeypatch.setattr(geo, "_fetch_json", lambda *args, **kwargs: {"type": "Nope"})
    status2 = geo.prepare_belgium_geodata(
        out_dir=tmp_path / "out2",
        fallback_province_geojson=fallback,
        province_url="https://example.test/province",
        municipality_url="https://example.test/municipality",
        offline=False,
    )
    assert status2["layers"][0]["status"] == "fallback_local_after_error"
    assert geo._is_feature_collection(fc) is True
    assert geo._is_feature_collection({"type": "FeatureCollection", "features": {}}) is False

    monkeypatch.undo()
    monkeypatch.setattr(geo, "urlopen", lambda *args, **kwargs: _FakeResponse("[]"))
    with pytest.raises(ValueError):
        geo._fetch_json("https://example.test", timeout_s=1)


def test_validation_history_branches(tmp_path: Path) -> None:
    assert vh._num("bad", 3.0) == 3.0
    assert vh._dict_or_empty([]) == {}
    assert vh._list_or_empty({}) == []
    assert vh._target_date({"window_start": "2026-06-20T00:00:00Z"}) == "2026-06-20"
    assert vh._event_observed_for_date([], "2026-06-20") is None

    events = tmp_path / "events.csv"
    events.write_text(
        "date_start,date_end,observed\n2026-06-20,2026-06-21,false\n2026-06-22,2026-06-22,yes\n",
        encoding="utf-8",
    )
    report = {
        "generated_at": "2026-06-19T12:00:00Z",
        "target_window": {"start": "2026-06-20"},
        "operational_state": {"level": "normal", "model_score": 0.2},
        "aggregate": {"score": 0.2},
        "province_summary": [
            {"province": "France amont", "max_score": 1.0},
            {"province": "Namur", "max_score": 0.2},
        ],
    }
    payload = vh.update_validation_history(
        report=report,
        history_dir=tmp_path / "history",
        verified_events_csv=events,
        out_dir=tmp_path / "out",
    )
    assert payload["confusion"]["tn"] == 1
    assert payload["last_prediction"]["main_zone"] == "Namur"

    no_events_payload = vh.update_validation_history(
        report={
            "target_window": {"start": "2026-06-30"},
            "operational_state": {"level": "alert"},
        },
        history_dir=tmp_path / "history2",
        verified_events_csv=tmp_path / "missing.csv",
        out_dir=tmp_path / "out2",
    )
    assert no_events_payload["status"] == "needs_verified_events"
