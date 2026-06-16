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
    return report_dir


def test_build_index_produces_site_and_api(tmp_path: Path) -> None:
    report_dir = _minimal_report_dir(tmp_path)
    site_dir = tmp_path / "site"
    vm = site.build_index(report_dir, site_dir)

    index_html = (site_dir / "index.html").read_text(encoding="utf-8")
    assert "__BOOTSTRAP__" not in index_html
    assert "__GENERATED_AT__" not in index_html
    assert "Vue simple" in index_html and "Vue opérationnelle" in index_html

    for name in ["latest", "stations", "timeline", "transition", "sources", "validation", "index"]:
        api_file = site_dir / "api" / f"{name}.json"
        assert api_file.exists(), name
        json.loads(api_file.read_text(encoding="utf-8"))  # parses

    # three-level view-model is complete
    assert set(vm) == {"meta", "simple", "operational", "expert"}
    assert len(vm["operational"]["blocks"]) == 7
    assert vm["operational"]["timeline"]["hours"]


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
