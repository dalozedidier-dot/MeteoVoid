"""Tests for the three-level public site builder and its static JSON API."""

from __future__ import annotations

import json
from pathlib import Path

import tools.build_belgium_public_site as site


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _minimal_report_dir(root: Path) -> Path:
    report_dir = root / "report"
    report_dir.mkdir()
    _write(
        report_dir / "belgium_alert_report.json",
        {
            "generated_at": "2026-06-16T16:00:00+00:00",
            "run_id": "test_run",
            "timezone": "Europe/Brussels",
            "data_mode": "offline_demo",
            "target_window": {"start": "2026-06-16", "end": "2026-06-16", "label": "2026-06-16"},
            "aggregate": {
                "score": 0.81,
                "severity": "alert",
                "source_ok_count": 3,
                "source_error_count": 0,
            },
            "operational_state": {
                "level": "watch_reinforced",
                "model_score": 0.81,
                "external_confirmation_score": 0.0,
                "source_health_score": 1.0,
                "public_wording": "veille renforcée, non officielle",
                "reason": "signal modèle élevé",
            },
            "integrations": {"radar_integrated": False},
            "timeline_summary": {
                "status": "available",
                "first_high_time": "2026-06-16T15:00",
                "last_high_time": "2026-06-16T20:00",
                "peak_time": "2026-06-16T16:00",
                "peak_score": 0.86,
                "high_hour_count": 6,
                "summary": "Pic vers 16h.",
            },
            "province_summary": [
                {
                    "province": "Brabant wallon",
                    "max_score": 0.84,
                    "severity": "alert",
                    "top_station": "Jodoigne",
                    "station_count": 2,
                }
            ],
            "stations": [
                {
                    "station_id": "BE_UCCLE",
                    "name": "Uccle",
                    "region": "belgium_center",
                    "score": 0.81,
                    "severity": "alert",
                    "worst_time": "2026-06-16T16:00",
                    "lat": 50.8,
                    "lon": 4.36,
                    "max_temperature_c": 32.0,
                    "max_dew_point_c": 20.0,
                    "max_precip_probability_pct": 73.0,
                    "max_pressure_drop_6h_hpa": 8.0,
                    "max_wind_gust_ms": 18.0,
                    "signals": ["chaleur marquée", "humidité lourde"],
                }
            ],
        },
    )
    _write(report_dir / "alert_state.json", {"level": "watch_reinforced"})
    _write(
        report_dir / "convective_transition_report.json",
        {
            "interpretation": "Transition convective probable.",
            "external_emergence_proxy": 0.1,
            "national": {
                "national_void_collapse_signal": 0.74,
                "national_transition_level": "transition_probable",
                "indices": {
                    "convective_load_index": {"mean": 0.8, "max": 0.9},
                    "trigger_readiness_index": {"mean": 0.7, "max": 0.9},
                    "storm_organization_potential": {"mean": 0.6, "max": 0.7},
                    "lid_fragility_index": {"mean": 0.75, "max": 0.9},
                    "observed_emergence_index": {"mean": 0.5, "max": 0.7},
                },
            },
        },
    )
    _write(
        report_dir / "risk_timeseries.json",
        {
            "timeline": [
                {
                    "time": "2026-06-16T15:00",
                    "max_score": 0.7,
                    "mean_score": 0.4,
                    "severity": "high",
                },
                {
                    "time": "2026-06-16T16:00",
                    "max_score": 0.86,
                    "mean_score": 0.5,
                    "severity": "alert",
                },
            ]
        },
    )
    _write(
        report_dir / "early_warning_signals.json",
        {"summary": {"network_early_warning_score": 0.5, "interpretation": "destabilizing"}},
    )
    _write(
        report_dir / "information_graph_summary.json",
        {
            "summary": {
                "information_corridor_score": 0.8,
                "top_upstream_station": "DE_AACHEN",
                "top_downstream_station": "BE_UCCLE",
            }
        },
    )
    _write(
        report_dir / "validation_metrics.json",
        {
            "status": "needs_verified_events",
            "matched_event_count": 0,
            "scores": {"brier_score": None, "model_probability": 0.81},
            "confusion": {"tp": 0, "fp": 0, "tn": 0, "fn": 0},
        },
    )
    _write(report_dir / "self_watchdog.json", {"state": "healthy_run", "coherence_loss_score": 0.1})
    _write(
        report_dir / "source_status.json",
        {"data_mode": "offline_demo", "source_ok_count": 3, "source_error_count": 0},
    )
    _write(
        report_dir / "observation_gap_status.json",
        {"radar": {"configured": False, "status": "visual_layer_only", "source": "RainViewer"}},
    )
    _write(
        report_dir / "nowcast_status.json",
        {"radar_confirmation": "none", "lightning_confirmation": "none", "nowcast_ready": False},
    )
    _write(
        report_dir / "radar_stack.json",
        {
            "summary": {
                "rainviewer_evidence_level": "display_only",
                "opera_ord_status": "disabled",
                "national_radar_status": "interfaces_ready_no_machine_data",
                "national_radar_country_count": 4,
                "national_machine_country_count": 0,
            }
        },
    )
    _write(
        report_dir / "european_national_radar_status.json",
        {
            "summary": {
                "status": "interfaces_ready_no_machine_data",
                "country_count": 4,
                "machine_country_count": 0,
                "live_probe_enabled": False,
            }
        },
    )
    _write(
        report_dir / "european_national_radar_metrics.json",
        {
            "status": "no_country_machine_metrics",
            "countries": [
                {
                    "country": "spain",
                    "status": "no_readable_country_files",
                    "file_count": 0,
                    "readable_file_count": 0,
                    "machine_radar_available": False,
                    "radar_activity_score": None,
                },
                {
                    "country": "france",
                    "status": "no_readable_country_files",
                    "file_count": 0,
                    "readable_file_count": 0,
                    "machine_radar_available": False,
                    "radar_activity_score": None,
                },
                {
                    "country": "switzerland",
                    "status": "no_readable_country_files",
                    "file_count": 0,
                    "readable_file_count": 0,
                    "machine_radar_available": False,
                    "radar_activity_score": None,
                },
                {
                    "country": "netherlands",
                    "status": "no_readable_country_files",
                    "file_count": 0,
                    "readable_file_count": 0,
                    "machine_radar_available": False,
                    "radar_activity_score": None,
                },
            ],
        },
    )
    return report_dir


def test_build_index_produces_site_and_api(tmp_path: Path) -> None:
    report_dir = _minimal_report_dir(tmp_path)
    site_dir = tmp_path / "site"
    vm = site.build_index(report_dir, site_dir)

    index_html = (site_dir / "index.html").read_text(encoding="utf-8")
    assert "__BOOTSTRAP__" not in index_html
    assert "__GENERATED_AT__" not in index_html
    assert "Vue simple" in index_html and "Vue opérationnelle" in index_html

    for name in [
        "latest",
        "stations",
        "timeline",
        "transition",
        "sources",
        "validation",
        "radar",
        "europe",
        "europe_sources",
        "map_live",
        "index",
    ]:
        api_file = site_dir / "api" / f"{name}.json"
        assert api_file.exists(), name
        json.loads(api_file.read_text(encoding="utf-8"))  # parses

    # three-level view-model is complete
    assert set(vm) == {"meta", "simple", "operational", "heat", "expert", "bulletin"}
    assert len(vm["operational"]["blocks"]) == 7
    assert vm["operational"]["timeline"]["hours"]


def test_map_live_api_exposes_alert_watch_map_payload(tmp_path: Path) -> None:
    report_dir = _minimal_report_dir(tmp_path)
    site_dir = tmp_path / "site"

    site.build_index(report_dir, site_dir)

    payload = json.loads((site_dir / "api" / "map_live.json").read_text(encoding="utf-8"))
    assert payload["contract"] == "meteovoid_belgium_map_live_v2"
    assert payload["compat_contract"] == "meteovoid_belgium_map_live_v1"
    assert payload["source"] == "belgium_alert_watch"
    assert payload["hours"]
    assert payload["stations"]
    assert payload["stations"][0]["scores"]
    assert payload["timeline"]["forecast_model"]["label"] == "prévision modèle"
    assert payload["timeline"]["radar_observed"]["label"] == "radar observé"
    assert payload["summary"]["station_count"] >= 1


def test_latest_api_has_expected_shape(tmp_path: Path) -> None:
    report_dir = _minimal_report_dir(tmp_path)
    site_dir = tmp_path / "site"
    site.build_index(report_dir, site_dir)
    latest = json.loads((site_dir / "api" / "latest.json").read_text(encoding="utf-8"))

    assert latest["operational_level"]["label"] == "Veille renforcée"
    # operational level "watch_reinforced" must not be painted red (reserved for danger)
    assert latest["operational_level"]["class"] == "elevated"
    assert latest["critical_window"]["label"] == "15h → 20h"
    assert latest["main_zone"]["name"] == "Brabant wallon"
    assert 0.0 <= latest["confidence"]["score"] <= 1.0
    assert latest["alert_explanation"]["bullets"]


def test_level_meta_reserves_red_for_real_danger() -> None:
    assert site._meta("alert")["class"] == "danger"
    assert site._meta("void_collapse")["class"] == "danger"
    assert site._meta("watch_reinforced")["class"] == "elevated"
    assert site._meta("normal")["class"] == "calm"
    # unknown keys degrade gracefully
    assert site._meta(None)["class"] == "calm"


def test_level_meta_accepts_already_normalized_dicts() -> None:
    meta = site._meta({"key": "alert", "label": "Critique", "class": "danger", "rank": 5})

    assert meta == {"key": "alert", "label": "Critique", "class": "danger", "rank": 5}


def test_bulletin_zones_are_clean_and_split_from_upstream(tmp_path: Path) -> None:
    report_dir = _minimal_report_dir(tmp_path)
    report = json.loads((report_dir / "belgium_alert_report.json").read_text(encoding="utf-8"))
    report["province_summary"].insert(
        0,
        {
            "province": "Approche France",
            "max_score": 0.871,
            "severity": {"key": "alert", "label": "Critique", "class": "danger", "rank": 5},
            "top_station": "FR_LILLE",
            "station_count": 1,
        },
    )
    (report_dir / "belgium_alert_report.json").write_text(
        json.dumps(report, ensure_ascii=False),
        encoding="utf-8",
    )
    site_dir = tmp_path / "site"
    vm = site.build_index(report_dir, site_dir)

    assert vm["simple"]["main_zone"]["name"] == "Brabant wallon"

    sections = {s.get("title"): s for s in vm["bulletin"]["sections"]}
    belgium = "\n".join(sections["Zones belges à surveiller"]["items"])
    upstream = "\n".join(sections["Couloirs amont à surveiller"]["items"])
    joined = belgium + "\n" + upstream

    assert "Brabant wallon · Critique (0.840)" in belgium
    assert "Approche France · Critique (0.871)" in upstream
    assert "Approche France" not in belgium
    assert "{'" not in joined
    assert "key" not in joined.lower()


def test_map_scaffolding_and_enriched_stations(tmp_path: Path) -> None:
    report_dir = _minimal_report_dir(tmp_path)
    site_dir = tmp_path / "site"
    site.build_index(report_dir, site_dir)

    index_html = (site_dir / "index.html").read_text(encoding="utf-8")
    for token in ['data-view="map"', "renderMap", "initMap", "locsel", "leaflet"]:
        assert token in index_html, token

    stations = json.loads((site_dir / "api" / "stations.json").read_text(encoding="utf-8"))[
        "stations"
    ]
    assert stations, "stations must be exposed for the map"
    first = stations[0]
    assert first["lat"] is not None and first["lon"] is not None
    assert "drivers" in first and "temperature_c" in first["drivers"]
    assert isinstance(first["hourly"], list)


def test_build_is_robust_to_empty_report_dir(tmp_path: Path) -> None:
    """The builder must never fail silently: an empty run still yields a page."""
    report_dir = tmp_path / "empty"
    report_dir.mkdir()
    site_dir = tmp_path / "site"

    vm = site.build_index(report_dir, site_dir)  # must not raise

    assert (site_dir / "index.html").exists()
    latest = json.loads((site_dir / "api" / "latest.json").read_text(encoding="utf-8"))
    assert latest["operational_level"]["class"] == "calm"
    assert len(vm["operational"]["blocks"]) == 7


def test_european_radars_are_visible_in_public_html_and_api(tmp_path: Path) -> None:
    report_dir = _minimal_report_dir(tmp_path)
    site_dir = tmp_path / "site"
    site.build_index(report_dir, site_dir)

    index_html = (site_dir / "index.html").read_text(encoding="utf-8")
    for token in [
        "Radars Europe",
        "Radars nationaux Europe",
        "Espagne, France, Suisse, Pays-Bas",
        "european_national_radar_map.html",
        "european_national_radar_report.md",
    ]:
        assert token in index_html, token

    radar = json.loads((site_dir / "api" / "radar.json").read_text(encoding="utf-8"))
    assert radar["european_national_radar"]["country_count"] == 4
    assert radar["european_national_radar_metrics"]["countries"][0]["country"] == "spain"


def test_europe_page_is_dedicated_and_precise(tmp_path: Path) -> None:
    report_dir = _minimal_report_dir(tmp_path)
    site_dir = tmp_path / "site"
    site.build_index(report_dir, site_dir)

    europe_html = (site_dir / "europe.html").read_text(encoding="utf-8")
    for token in [
        "MeteoVoid Europe",
        "Espagne · France · Suisse · Pays-Bas",
        "Page Europe complète",
        "Vue simple",
        "Opérationnel",
        "Carte Europe",
        "Pays",
        "Corridors",
        "Sources",
        "Expert",
        "Source → radar → métrique → corridor",
        "european_national_radar_map.html",
        "api/europe.json",
    ]:
        assert token in europe_html, token

    europe = json.loads((site_dir / "api" / "europe.json").read_text(encoding="utf-8"))
    assert europe["summary"]["country_count"] == 4
    assert europe["page_contract"] == "meteovoid_europe_page_full_v3_same_design"
    assert "simple" in europe and "operational" in europe
    assert "radar_layers" in europe and len(europe["radar_layers"]) >= 4
    assert "exports" in europe and len(europe["exports"]) >= 8
    assert europe["summary"]["source_count"] >= 16
    assert europe["summary"]["configured_source_count"] >= 10
    assert len(europe["radar_layers"]) >= 4
    assert {src["bucket"] for src in europe["sources"]} >= {"display", "national", "opera"}
    assert {c["country"] for c in europe["countries"]} == {
        "spain",
        "france",
        "switzerland",
        "netherlands",
    }
    assert europe["links"]["belgium"] == "index.html"

    index_html = (site_dir / "index.html").read_text(encoding="utf-8")
    assert 'href="europe.html"' in index_html


def test_country_pages_are_generated_and_linked(tmp_path: Path) -> None:
    report_dir = _minimal_report_dir(tmp_path)
    site_dir = tmp_path / "site"
    site.build_index(report_dir, site_dir)

    europe_html = (site_dir / "europe.html").read_text(encoding="utf-8")
    for key in ("spain", "france", "switzerland", "netherlands", "germany", "denmark"):
        page = site_dir / f"{key}.html"
        assert page.exists(), f"missing dedicated page for {key}"
        html = page.read_text(encoding="utf-8")
        for token in ["Détection", "Carte radar", "Réseau radar", "initCountryMap", "leaflet"]:
            assert token in html, (key, token)
        # the Europe page links to each dedicated country page
        assert f"{key}.html" in europe_html

        model = json.loads((site_dir / "api" / f"country_{key}.json").read_text(encoding="utf-8"))
        assert model["contract"] == "meteovoid_country_followup_v1"
        assert model["stations"], "country detection must score stations"
        assert model["radar_network"]["site_count"] >= 1
        assert model["summary"]["radar_site_count"] == model["radar_network"]["site_count"]
        assert model["data_sources"], "country links its master radar sources"

    # France ships the densest real radar network of the four original countries
    france = json.loads((site_dir / "api" / "country_france.json").read_text(encoding="utf-8"))
    assert france["summary"]["radar_site_count"] >= 15


def test_master_radar_source_registry_is_published_and_sanitised(tmp_path: Path) -> None:
    report_dir = _minimal_report_dir(tmp_path)
    site_dir = tmp_path / "site"
    site.build_index(report_dir, site_dir)

    reg = json.loads((site_dir / "api" / "radar_sources.json").read_text(encoding="utf-8"))
    assert reg["summary"]["source_count"] == 8
    assert reg["sources"][0]["id"] == "meteogate_opera_ord"  # European pivot, rank 1

    europe_html = (site_dir / "europe.html").read_text(encoding="utf-8")
    assert "Registre maître" in europe_html
    assert "priorité opérationnelle" in europe_html


def test_belgium_page_has_a_weather_bulletin(tmp_path: Path) -> None:
    report_dir = _minimal_report_dir(tmp_path)
    site_dir = tmp_path / "site"
    vm = site.build_index(report_dir, site_dir)

    # bulletin is part of the view-model and rendered on the Belgium page
    assert "bulletin" in vm
    bulletin = vm["bulletin"]
    assert bulletin["contract"] == "meteovoid_belgium_bulletin_v1"
    assert bulletin["sections"], "bulletin must have content sections"
    assert bulletin["non_official"] is True

    index_html = (site_dir / "index.html").read_text(encoding="utf-8")
    for token in [
        'data-view="bulletin"',
        "renderBulletin",
        "view-bulletin",
        "Bulletin météo classique Belgique",
        "Températures par région belge",
    ]:
        assert token in index_html, token

    section_titles = {section.get("title") for section in bulletin["sections"]}
    assert "Bulletin météo classique Belgique" in section_titles


def test_model_map_selectors_are_actually_wired(tmp_path: Path) -> None:
    report_dir = _minimal_report_dir(tmp_path)
    site_dir = tmp_path / "site"
    site.build_index(report_dir, site_dir)

    index_html = (site_dir / "index.html").read_text(encoding="utf-8")
    for token in [
        "BELGIUM_VIEW_BOUNDS",
        "BELGIUM_MODEL_GRID",
        "modelSelectionChanged",
        "fitBelgiumMap",
        "Open-Meteo · champ modèle réel",
    ]:
        assert token in index_html, token

    assert "modelSource.onchange=()=>modelSelectionChanged()" in index_html
    assert "modelLayer.onchange=()=>modelSelectionChanged()" in index_html

    france_html = (site_dir / "france.html").read_text(encoding="utf-8")
    assert "cNwpChanged" in france_html
    assert "Open-Meteo · champ modèle réel" in france_html


def test_map_live_api_uses_csv_timeline_when_json_is_absent(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    site_dir = tmp_path / "site"
    report_dir.mkdir()
    (report_dir / "risk_timeline.csv").write_text(
        "time,mean_score,max_score,severity,station_count\n"
        "2026-06-19T00:00,0.21,0.45,watch,2\n"
        "2026-06-19T01:00,0.12,0.30,normal,2\n",
        encoding="utf-8",
    )
    (report_dir / "risk_by_station.csv").write_text(
        "station_id,name,region,score,severity,heat_stress_score,convective_risk_score,"
        "max_temperature_c,max_dew_point_c,max_precip_probability_pct,max_wind_gust_ms,signals\n"
        "BE_UCCLE,Uccle / Bruxelles,belgium_center,0.61,medium,1.0,0.53,34,21,85,14,signal\n",
        encoding="utf-8",
    )
    (report_dir / "native_convective_grid.csv").write_text(
        "lat,lon,storm_formation_score,native_convective_score,"
        "cape_j_kg,cin_j_kg,lifted_index_c,nearest_station\n"
        "50.8,4.36,0.72,0.41,1200,10,-3,Uccle\n",
        encoding="utf-8",
    )

    site.build_index(report_dir, site_dir)

    payload = json.loads((site_dir / "api" / "map_live.json").read_text(encoding="utf-8"))
    assert [hour["score"] for hour in payload["hours"]] == [0.45, 0.3]
    assert payload["stations"][0]["name"] == "Uccle / Bruxelles"
    assert payload["stations"][0]["lat"] == 50.7989
    assert payload["stations"][0]["scores"][0] != payload["stations"][0]["scores"][1]
    assert payload["grid"][0]["scores"][0] != payload["grid"][0]["scores"][1]
