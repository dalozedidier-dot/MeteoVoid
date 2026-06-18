"""Tests for the per-country European follow-up (detection + radar network)."""

from __future__ import annotations

from meteovoid.europe_country import build_all_countries, build_country_detection


def test_build_all_countries_covers_the_four_tracked_countries() -> None:
    models = build_all_countries(run_day="2026-06-18")
    assert set(models) == {"spain", "france", "switzerland", "netherlands"}
    for model in models.values():
        assert model["contract"] == "meteovoid_country_followup_v1"
        assert model["non_official"] is True
        assert model["data_mode"] == "offline_demo"
        # the same detection engine produces per-station scores
        assert model["stations"], "each country must score at least one station"
        for station in model["stations"]:
            assert 0.0 <= station["score"] <= 1.0
            assert station["severity"]["key"] in {"calm", "watch", "elevated", "danger"}
            assert "wind_gust_ms" in station["drivers"]
            assert station["hourly"], "stations expose an hourly sparkline series"
        # a real national radar network is attached
        network = model["radar_network"]
        assert network["site_count"] >= 1
        assert len(network["sites"]) == network["site_count"]
        for site in network["sites"]:
            assert -180 <= site["lon"] <= 180 and -90 <= site["lat"] <= 90


def test_country_models_are_deterministic_offline() -> None:
    a = build_all_countries(run_day="2026-06-18")
    b = build_all_countries(run_day="2026-06-18")
    assert [s["score"] for s in a["france"]["stations"]] == [
        s["score"] for s in b["france"]["stations"]
    ]


def test_radar_network_stays_honest_without_a_national_key(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("AEMET_API_KEY", raising=False)
    models = build_all_countries(run_day="2026-06-18")
    spain = models["spain"]["radar_network"]
    assert spain["api_key_env"] == "AEMET_API_KEY"
    assert spain["api_key_configured"] is False
    assert spain["machine_evidence"] is False
    assert spain["status"] == "interface_ready_awaiting_national_key"
    # MeteoSwiss exposes open data, so it has no key requirement
    assert models["switzerland"]["radar_network"]["status"] == "open_data_interface_ready"


def test_france_has_a_dense_radar_network_and_station_grid() -> None:
    models = build_all_countries(run_day="2026-06-18")
    france = models["france"]
    assert france["summary"]["radar_site_count"] >= 15
    assert france["summary"]["station_count"] >= 8
    assert france["operational_level"]["key"] in {"calm", "watch", "elevated", "danger"}


def test_missing_country_config_is_tolerated() -> None:
    models = build_all_countries(config_path="does/not/exist.yaml", run_day="2026-06-18")
    assert models == {}


def test_single_country_detection_shape() -> None:
    cfg = {
        "label": "Testland",
        "iso2": "TL",
        "center": {"lat": 50.0, "lon": 4.0},
        "zoom": 7,
        "radar_operator": "TestMet",
        "radars": [{"name": "R1", "lat": 50.1, "lon": 4.1, "band": "C"}],
        "stations": [{"id": "TL_A", "name": "Alpha", "lat": 50.2, "lon": 4.2}],
    }
    model = build_country_detection("testland", cfg, run_day="2026-06-18")
    assert model["label"] == "Testland"
    assert model["summary"]["station_count"] == 1
    assert model["summary"]["radar_site_count"] == 1
    assert model["radar_network"]["status"] == "open_data_interface_ready"
