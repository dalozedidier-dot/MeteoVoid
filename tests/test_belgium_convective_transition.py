from __future__ import annotations

import json

from tools.belgium_convective_transition import (
    build_convective_transition_report,
    write_convective_transition_outputs,
)


def _sample_report() -> dict:
    return {
        "generated_at": "2026-06-19T12:00:00+02:00",
        "run_id": "test-run",
        "source": "offline_demo",
        "source_type": "model_forecast",
        "target_window": {"start": "2026-06-19", "end": "2026-06-19"},
        "integrations": {
            "official_warning_integrated": True,
            "radar_integrated": False,
            "lightning_integrated": False,
        },
        "external_confirmation": {"score": 0.45},
        "operational_state": {"external_confirmation_score": 0.45},
        "stations": [
            {
                "station_id": "BE_NAMUR",
                "name": "Namur",
                "region": "Wallonie",
                "lat": 50.46,
                "lon": 4.86,
                "score": 0.76,
                "severity": "high",
                "worst_time": "2026-06-19T17:00",
                "max_temperature_c": 33.0,
                "max_dew_point_c": 22.5,
                "components": {
                    "heat": 0.8,
                    "moisture": 0.9,
                    "precipitation": 0.75,
                    "pressure_drop": 0.55,
                    "weather_code": 1.0,
                    "wind_gust": 0.45,
                },
                "signals": ["code météo orageux"],
                "source_ok": True,
            }
        ],
    }


def test_build_convective_transition_report_has_core_indices() -> None:
    transition = build_convective_transition_report(_sample_report())
    assert transition["mode"] == "convective_transition_engine"
    assert transition["national"]["national_void_collapse_signal"] > 0
    assert transition["station_indices"][0]["convective_load_index"] > 0
    assert transition["station_indices"][0]["void_collapse_signal"] > 0


def test_write_convective_transition_outputs(tmp_path) -> None:
    write_convective_transition_outputs(_sample_report(), tmp_path)
    json_path = tmp_path / "convective_transition_report.json"
    assert json_path.exists()
    assert (tmp_path / "convective_transition_by_station.csv").exists()
    assert (tmp_path / "convective_transition_report.md").exists()
    assert (tmp_path / "convective_transition_dashboard.html").exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["station_indices"][0]["name"] == "Namur"
