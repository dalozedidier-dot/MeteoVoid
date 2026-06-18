"""Tests for the per-country European follow-up (detection + radar network)."""

from __future__ import annotations

from meteovoid.europe_country import build_all_countries, build_country_detection


def test_build_all_countries_covers_every_tracked_country() -> None:
    models = build_all_countries(run_day="2026-06-18")
    assert {
        "spain",
        "france",
        "switzerland",
        "netherlands",
        "germany",
        "denmark",
    } <= set(models)
    for model in models.values():
        assert model["contract"] == "meteovoid_country_followup_v1"
        assert model["non_official"] is True
        assert model["data_mode"] == "offline_demo"
        # the sanitised master radar source registry is attached per country
        assert model["data_sources"], "each country links its master radar sources"
        for src in model["data_sources"]:
            assert "id" in src and "status" in src
            # never leak a secret value, only the variable name + a boolean
            assert "configured" in src
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


def test_convective_layer_is_labelled_proxy_when_offline() -> None:
    models = build_all_countries(run_day="2026-06-18")
    fr = models["france"]
    # offline build must never claim native convective model fields
    assert fr["summary"]["convective_basis"] == "proxy"
    assert fr["summary"]["native_convective_fields"] is False
    assert fr["convective"]["native_fields_available"] is False
    assert set(fr["convective"]["fields"]) == {"CAPE", "CIN", "lifted_index", "bulk_shear"}
    station = fr["stations"][0]
    conv = station["convective"]
    assert conv["native_fields_available"] is False
    assert conv["basis"].startswith("proxy")
    # the proxy still carries CAPE/LI/shear shaped values for the UI
    assert "cape_jkg" in conv and "lifted_index" in conv


def test_validation_is_honest_about_missing_verified_events() -> None:
    models = build_all_countries(run_day="2026-06-18")
    val = models["france"]["validation"]
    assert val["status"] == "needs_verified_events"
    assert val["verified_event_count"] == 0
    # Brier / POD / FAR / CSI must stay null until real events are supplied
    assert val["metrics"] == {"brier_score": None, "pod": None, "far": None, "csi": None}


def test_machine_radar_is_zero_until_a_real_file_is_provided() -> None:
    models = build_all_countries(run_day="2026-06-18")
    mr = models["france"]["machine_radar"]
    assert mr["available"] is False
    assert mr["metrics"] is None
    assert mr["blockers"], "must explain why no machine metric exists"
    assert mr["how_to_enable"], "must explain how to reach machine evidence"
