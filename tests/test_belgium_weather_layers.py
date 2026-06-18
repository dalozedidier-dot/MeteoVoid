from __future__ import annotations

import json
from pathlib import Path

from tools.generate_belgium_alert_report import main


def test_weather_layers_outputs_are_written(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    rc = main(
        [
            "--stations",
            "config/stations_belgium.yaml",
            "--target-date",
            "2026-06-19",
            "--out-dir",
            str(out_dir),
            "--offline-demo",
            "--official-forecast-signal",
            "severe_thunderstorms",
            "--heat-warning-active",
            "--no-history",
        ]
    )
    assert rc == 0

    expected = {
        "belgium_weather_layers.html",
        "belgium_radar_map.html",
        "belgium_humidity_map.html",
        "belgium_dewpoint_map.html",
        "belgium_storm_formation_map.html",
        "belgium_windy_compare.html",
        "weather_layers_grid.csv",
        "convective_parameters.json",
        "belgium_native_convective_map.html",
        "native_convective_grid.csv",
        "native_convective_parameters.json",
    }
    assert expected <= {p.name for p in out_dir.iterdir() if p.is_file()}

    convective = json.loads((out_dir / "convective_parameters.json").read_text(encoding="utf-8"))
    assert convective["mode"] == "proxy_plus_native_convective_fields"
    assert convective["native_convective_contract"] == "native_convective_fields_optional_v1"
    assert convective["inputs"]["grid_point_count"] > 0
    assert convective["inputs"]["native_convective_grid_point_count"] > 0
    assert convective["inputs"]["cape_integrated"] is True
    assert convective["inputs"]["shear_integrated"] is False
    assert convective["inputs"]["srh_integrated"] is False
    assert convective["summary"]["max_storm_formation_score_grid"] is not None
    assert convective["summary"]["max_native_convective_score_grid"] is not None

    native = json.loads((out_dir / "native_convective_parameters.json").read_text(encoding="utf-8"))
    assert native["mode"] == "proxy_plus_native_convective_fields"

    layers_html = (out_dir / "belgium_weather_layers.html").read_text(encoding="utf-8")
    assert "Radar pluie" in layers_html
    assert "Formation orageuse" in layers_html
    assert "RainViewer" in layers_html
