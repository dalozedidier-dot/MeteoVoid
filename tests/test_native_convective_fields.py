from __future__ import annotations

import json
from pathlib import Path

from tools.belgium_score_layers import native_convective_indices_from_hourly
from tools.belgium_weather_layers import build_weather_layer_grid, convective_parameters_summary


def test_native_convective_indices_consume_model_fields() -> None:
    indices = native_convective_indices_from_hourly(
        {
            "cape": [0.0, 1800.0, 2400.0],
            "lifted_index": [2.0, -4.0, -6.5],
            "convective_inhibition": [-180.0, -80.0, -30.0],
            "freezing_level_height": [3100.0, 3700.0, 4100.0],
            "boundary_layer_height": [900.0, 1600.0, 2200.0],
            "lightning_potential": [0.0, 3.0, 6.0],
        }
    )

    assert indices["available"] is True
    assert "cape_j_kg" in indices["available_fields"]
    assert "lifted_index_c" in indices["available_fields"]
    assert "cin_j_kg" in indices["available_fields"]
    assert "freezing_level_height_m" in indices["available_fields"]
    assert "boundary_layer_height_m" in indices["available_fields"]
    assert "lightning_potential_index" in indices["available_fields"]
    assert indices["raw"]["cape_j_kg"] == 2400.0
    assert indices["raw"]["lifted_index_c"] == -6.5
    assert indices["native_convective_score"] is not None


def test_weather_layers_build_native_convective_grid() -> None:
    report = {
        "generated_at": "2026-06-18T12:00:00+02:00",
        "source": "test",
        "stations": [
            {
                "station_id": "BE_TEST",
                "name": "Test",
                "region": "belgium_center",
                "lat": 50.85,
                "lon": 4.35,
                "score": 0.6,
                "max_relative_humidity_pct": 82.0,
                "max_dew_point_c": 21.0,
                "source_ok": True,
                "components": {"moisture": 0.8},
                "convective_indices": {
                    "available": True,
                    "available_fields": ["cape_j_kg", "cin_j_kg", "lifted_index_c"],
                    "native_convective_score": 0.72,
                    "raw": {
                        "cape_j_kg": 1800.0,
                        "cin_j_kg": -60.0,
                        "lifted_index_c": -5.0,
                    },
                },
            }
        ],
    }

    points = build_weather_layer_grid(report, step=0.3)
    summary = convective_parameters_summary(report, points)

    assert points
    assert any(point.native_convective_score is not None for point in points)
    assert any(point.cape_j_kg is not None for point in points)
    assert summary["mode"] == "proxy_plus_native_convective_fields"
    assert summary["inputs"]["native_convective_grid_point_count"] > 0


def test_native_convective_report_outputs_exist(tmp_path: Path) -> None:
    from tools.belgium_weather_layers import write_weather_layer_outputs

    report = {
        "generated_at": "2026-06-18T12:00:00+02:00",
        "source": "test",
        "stations": [
            {
                "station_id": "BE_TEST",
                "name": "Test",
                "region": "belgium_center",
                "lat": 50.85,
                "lon": 4.35,
                "score": 0.6,
                "max_relative_humidity_pct": 82.0,
                "max_dew_point_c": 21.0,
                "source_ok": True,
                "components": {"moisture": 0.8},
                "convective_indices": {
                    "available": True,
                    "available_fields": ["cape_j_kg", "cin_j_kg", "lifted_index_c"],
                    "native_convective_score": 0.72,
                    "raw": {
                        "cape_j_kg": 1800.0,
                        "cin_j_kg": -60.0,
                        "lifted_index_c": -5.0,
                    },
                },
            }
        ],
    }
    write_weather_layer_outputs(report, tmp_path)

    assert (tmp_path / "belgium_native_convective_map.html").exists()
    assert (tmp_path / "native_convective_grid.csv").exists()
    native = json.loads((tmp_path / "native_convective_parameters.json").read_text())
    assert native["mode"] == "proxy_plus_native_convective_fields"
