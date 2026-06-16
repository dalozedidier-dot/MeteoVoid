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


def _openmeteo_payload() -> dict[str, object]:
    hours = ["2026-06-17T18:00", "2026-06-17T19:00", "2026-06-17T20:00"]
    return {
        "hourly": {
            "time": hours,
            "temperature_2m": [29.0, 31.0, 30.0],
            "dew_point_2m": [19.0, 21.5, 20.5],
            "relative_humidity_2m": [70.0, 78.0, 74.0],
            "precipitation_probability": [45.0, 82.0, 68.0],
            "precipitation": [0.0, 5.2, 2.0],
            "showers": [0.0, 7.0, 1.0],
            "weather_code": [3.0, 95.0, 96.0],
            "pressure_msl": [1007.0, 1005.0, 1004.0],
            "wind_speed_10m": [6.0, 8.0, 7.0],
            "wind_direction_10m": [220.0, 225.0, 230.0],
            "wind_gusts_10m": [14.0, 24.0, 20.0],
            "cape": [600.0, 1800.0, 2300.0],
            "temperature_925hPa": [24.0, 25.0, 24.5],
            "dew_point_925hPa": [17.0, 18.0, 17.5],
            "relative_humidity_925hPa": [78.0, 90.0, 86.0],
            "wind_speed_925hPa": [10.0, 11.0, 10.5],
            "wind_direction_925hPa": [210.0, 215.0, 220.0],
            "geopotential_height_925hPa": [760.0, 755.0, 750.0],
            "temperature_850hPa": [18.0, 19.0, 18.5],
            "dew_point_850hPa": [13.0, 15.5, 14.0],
            "relative_humidity_850hPa": [70.0, 86.0, 82.0],
            "wind_speed_850hPa": [14.0, 16.0, 15.0],
            "wind_direction_850hPa": [220.0, 225.0, 225.0],
            "geopotential_height_850hPa": [1500.0, 1490.0, 1485.0],
            "temperature_700hPa": [8.0, 7.0, 7.5],
            "dew_point_700hPa": [1.0, 2.0, 1.5],
            "relative_humidity_700hPa": [48.0, 52.0, 50.0],
            "wind_speed_700hPa": [18.0, 20.0, 19.0],
            "wind_direction_700hPa": [230.0, 235.0, 235.0],
            "geopotential_height_700hPa": [3100.0, 3090.0, 3085.0],
            "temperature_500hPa": [-13.0, -14.0, -13.5],
            "dew_point_500hPa": [-25.0, -24.0, -24.5],
            "relative_humidity_500hPa": [34.0, 38.0, 36.0],
            "wind_speed_500hPa": [28.0, 31.0, 30.0],
            "wind_direction_500hPa": [245.0, 250.0, 250.0],
            "geopotential_height_500hPa": [5660.0, 5650.0, 5645.0],
            "temperature_300hPa": [-42.0, -43.0, -42.5],
            "dew_point_300hPa": [-55.0, -56.0, -55.5],
            "relative_humidity_300hPa": [20.0, 22.0, 21.0],
            "wind_speed_300hPa": [44.0, 48.0, 46.0],
            "wind_direction_300hPa": [250.0, 255.0, 255.0],
            "geopotential_height_300hPa": [9250.0, 9240.0, 9235.0],
        }
    }


def test_build_upstream_watch_with_openmeteo_fallback(monkeypatch) -> None:
    from meteovoid.belgium import upstream_watch as module

    calls: list[str] = []

    def fake_http_json(url: str, *, timeout_s: float) -> dict[str, object]:
        calls.append(url)
        assert timeout_s == 1.0
        return _openmeteo_payload()

    monkeypatch.setattr(module, "_http_json", fake_http_json)
    watch = module.build_upstream_watch(
        _minimal_report(),
        upstream_config_path="config/upstream_regions.yaml",
        radar_sources_config_path="config/european_radar_sources.yaml",
        openmeteo_enabled=True,
        forecast_hours=3,
        timeout_s=1.0,
    )

    assert calls
    assert watch["data_mode"] == "openmeteo_fallback_enabled"
    assert watch["summary"]["max_corridor_score"] > 0.0
    assert "openmeteo_fallback" in watch["summary"]["data_modes"]
    first_region = watch["regions"][0]
    assert first_region["indices"]["cape_j_kg"] == 2300.0
    assert first_region["indices"]["k_index_proxy_c"] is not None
    assert first_region["indices"]["shear_850_500_ms_proxy"] is not None
    assert first_region["evidence"]["openmeteo_url"].startswith("https://api.open-meteo.com")


def test_openmeteo_error_falls_back_to_belgium_report(monkeypatch) -> None:
    from meteovoid.belgium import upstream_watch as module

    monkeypatch.setattr(module, "_http_json", lambda url, *, timeout_s: {"error": True})
    watch = module.build_upstream_watch(
        _minimal_report(),
        upstream_config_path="config/upstream_regions.yaml",
        radar_sources_config_path="config/european_radar_sources.yaml",
        openmeteo_enabled=True,
    )
    assert "surface_or_config_fallback" in watch["summary"]["data_modes"]
    assert all(
        region["source_status"] == "fallback_from_belgium_report" for region in watch["regions"]
    )


def test_radar_interfaces_configured_success_and_error(tmp_path: Path, monkeypatch) -> None:
    from meteovoid.belgium import upstream_watch as module

    radar_config = tmp_path / "radar.yaml"
    radar_config.write_text(
        """
contract: european_radar_interface_optional_v1
sources:
  - name: Licensed radar JSON
    kind: radar
    endpoint_env: METEOVOID_TEST_RADAR_URL
    public_info_url: https://example.invalid/radar
    license_note: test only
  - name: Lightning JSON
    kind: lightning
    endpoint_url: https://example.invalid/lightning.json
    public_info_url: https://example.invalid/lightning
    license_note: test only
  - name: Broken radar JSON
    kind: radar
    endpoint_url: https://example.invalid/broken.json
    public_info_url: https://example.invalid/broken
    license_note: test only
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("METEOVOID_TEST_RADAR_URL", "https://example.invalid/radar.json")

    def fake_http_json(url: str, *, timeout_s: float) -> dict[str, object]:
        assert timeout_s == 2.0
        if url.endswith("broken.json"):
            raise ValueError("bad upstream payload")
        if url.endswith("lightning.json"):
            return {"lightning_confirmation": "strong", "product": "test-li"}
        return {"radar_confirmation": "confirmed", "last_update": "2026-06-17T00:00:00Z"}

    monkeypatch.setattr(module, "_http_json", fake_http_json)
    status = module.inspect_radar_interfaces(radar_config, timeout_s=2.0)

    assert status["radar_confirmation_score"] == 0.75
    assert status["lightning_confirmation_score"] == 0.9
    assert [source["status"] for source in status["sources"]] == ["ok", "ok", "error"]


def test_invalid_and_sparse_config_branches(tmp_path: Path) -> None:
    from meteovoid.belgium import upstream_watch as module

    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("- not\n- a\n- mapping\n", encoding="utf-8")
    try:
        module.load_upstream_config(invalid)
    except ValueError as exc:
        assert "mapping" in str(exc)
    else:  # pragma: no cover - defensive assertion path
        raise AssertionError("invalid config should fail")

    sparse = tmp_path / "sparse.yaml"
    sparse.write_text(
        """
contract: european_upstream_regions_v1
regions:
  - id: TEST_SOURCE
    name: Test source
    role: upstream
    probe: {lat: 50.0, lon: 3.0}
  - id: TEST_TARGET
    name: Test target
    role: target
    probe: {lat: 50.5, lon: 4.5}
corridors:
  - id: TEST_CORRIDOR
    name: Test corridor
    source_region: TEST_SOURCE
    target_region: TEST_TARGET
    expected_bearing_deg: 45
""".lstrip(),
        encoding="utf-8",
    )
    watch = module.build_upstream_watch(
        {"stations": []},
        upstream_config_path=sparse,
        radar_sources_config_path=None,
        openmeteo_enabled=False,
    )
    assert watch["summary"]["corridor_count"] == 1
    assert watch["corridors"][0]["confidence"] == "very_low"
