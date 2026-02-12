from __future__ import annotations

from pathlib import Path

import pytest

from meteovoid.stations_config import filter_stations, load_stations_config


def test_load_stations_config_parses_stations_and_thresholds(tmp_path: Path) -> None:
    cfg_text = """stations:
  - id: BE_UCCLE
    name: Uccle
    region: belgium
    lat: 50.8
    lon: 4.35
    source: openmeteo
    variables: [wind_gusts_10m, wind_speed_10m]
  - id: FR_PARIS
    name: Paris
    region: france
    lat: 48.8167
    lon: 2.3333
    source: openmeteo
    variables: [temperature_2m]

thresholds:
  wind_gusts_10m:
    watch: 0.4
    alert: 0.7
  temperature_2m:
    watch: 0.5
"""
    p = tmp_path / "stations.yaml"
    p.write_text(cfg_text, encoding="utf-8")

    cfg = load_stations_config(p)
    assert len(cfg.stations) == 2
    assert cfg.stations[0].station_id == "BE_UCCLE"
    assert cfg.stations[0].variables == ["wind_gusts_10m", "wind_speed_10m"]
    assert cfg.thresholds["wind_gusts_10m"]["watch"] == pytest.approx(0.4)
    assert cfg.thresholds["wind_gusts_10m"]["alert"] == pytest.approx(0.7)
    assert cfg.thresholds["temperature_2m"]["watch"] == pytest.approx(0.5)


def test_filter_stations_by_region_and_ids(tmp_path: Path) -> None:
    cfg_text = """stations:
  - id: BE_UCCLE
    name: Uccle
    region: belgium
    lat: 50.8
    lon: 4.35
    source: openmeteo
    variables: [wind_gusts_10m]
  - id: BE_LIEGE
    name: Liege
    region: belgium
    lat: 50.6
    lon: 5.6
    source: openmeteo
    variables: [wind_gusts_10m]
  - id: FR_PARIS
    name: Paris
    region: france
    lat: 48.81
    lon: 2.33
    source: openmeteo
    variables: [temperature_2m]
"""
    p = tmp_path / "stations.yaml"
    p.write_text(cfg_text, encoding="utf-8")

    cfg = load_stations_config(p)

    be = filter_stations(cfg, region="belgium")
    assert {s.station_id for s in be} == {"BE_UCCLE", "BE_LIEGE"}

    one = filter_stations(cfg, station_ids=["FR_PARIS"])
    assert [s.station_id for s in one] == ["FR_PARIS"]

    both = filter_stations(cfg, region="belgium", station_ids=["BE_LIEGE", "FR_PARIS"])
    assert [s.station_id for s in both] == ["BE_LIEGE"]


def test_load_stations_config_rejects_invalid_shapes(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("[]\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_stations_config(p)

    p2 = tmp_path / "bad2.yaml"
    p2.write_text("stations: notalist\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_stations_config(p2)


def test_load_stations_config_skips_invalid_station_entries(tmp_path: Path) -> None:
    cfg_text = """stations:
  - foo: bar
  - id: ""
    variables: [x]
  - id: OK
    region: default
    lat: "50.0"
    lon: "4.0"
    source: openmeteo
    variables: ["a", " ", "b"]
"""
    p = tmp_path / "stations.yaml"
    p.write_text(cfg_text, encoding="utf-8")

    cfg = load_stations_config(p)
    assert [s.station_id for s in cfg.stations] == ["OK"]
    assert cfg.stations[0].variables == ["a", "b"]
