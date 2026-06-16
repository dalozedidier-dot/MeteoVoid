from __future__ import annotations

import json
from pathlib import Path

from meteovoid.belgium.upstream_watch import (
    build_openmeteo_upstream_url,
    build_upstream_watch,
    write_upstream_watch_outputs,
)


def _minimal_report() -> dict[str, object]:
    return {
        "generated_at": "2026-06-17T00:00:00+02:00",
        "target_window": {"start": "2026-06-17T18:00:00+02:00", "end": "2026-06-18T00:00:00+02:00"},
        "aggregate": {"score": 0.42, "severity": "medium"},
        "stations": [
            {
                "station_id": "BE_MONS",
                "name": "Mons",
                "region": "belgium_west",
                "score": 0.56,
                "heat_stress_score": 0.68,
                "convective_risk_score": 0.51,
                "components": {"moisture": 0.72},
                "signals": ["humid"],
                "source_ok": True,
            },
            {
                "station_id": "BE_JODOIGNE",
                "name": "Jodoigne",
                "region": "belgium_center",
                "score": 0.36,
                "heat_stress_score": 0.61,
                "convective_risk_score": 0.34,
                "components": {"moisture": 0.62},
                "signals": ["watch"],
                "source_ok": True,
            },
        ],
    }


def test_openmeteo_upstream_url_contains_pressure_level_variables() -> None:
    url = build_openmeteo_upstream_url(50.63, 3.06, forecast_hours=6)
    assert "cape" in url
    assert "wind_speed_850hPa" in url
    assert "wind_direction_700hPa" in url
    assert "geopotential_height_500hPa" in url
    assert "wind_speed_unit=ms" in url


def test_build_upstream_watch_offline_contract() -> None:
    watch = build_upstream_watch(
        _minimal_report(),
        upstream_config_path="config/upstream_regions.yaml",
        radar_sources_config_path="config/european_radar_sources.yaml",
        openmeteo_enabled=False,
    )
    assert watch["contract"] == "european_upstream_watch_v1"
    assert watch["data_mode"] == "report_surface_fallback_only"
    assert watch["summary"]["corridor_count"] >= 6
    assert watch["corridors"]
    assert watch["radar_interface"]["contract"] == "european_radar_interface_optional_v1"
    assert all(source["configured"] is False for source in watch["radar_interface"]["sources"])


def test_write_upstream_watch_outputs(tmp_path: Path) -> None:
    watch = write_upstream_watch_outputs(
        _minimal_report(),
        tmp_path,
        upstream_config_path="config/upstream_regions.yaml",
        radar_sources_config_path="config/european_radar_sources.yaml",
        openmeteo_enabled=False,
    )
    assert watch["summary"]["max_corridor_score"] >= 0.0
    assert (tmp_path / "upstream_watch.json").exists()
    assert (tmp_path / "upstream_watch_report.md").exists()
    assert (tmp_path / "european_upstream_map.html").exists()
    assert (tmp_path / "upstream_corridors.csv").exists()
    payload = json.loads((tmp_path / "upstream_watch.json").read_text(encoding="utf-8"))
    assert payload["contract"] == "european_upstream_watch_v1"
