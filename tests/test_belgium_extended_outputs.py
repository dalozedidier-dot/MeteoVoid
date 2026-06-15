from __future__ import annotations

import json
from pathlib import Path

from tools.generate_belgium_alert_report import main


def test_belgium_extended_outputs_are_written(tmp_path: Path) -> None:
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
        "risk_timeseries.json",
        "risk_timeline.csv",
        "province_summary.json",
        "province_summary.csv",
        "belgium_alert_heatmap.html",
        "notification_state.json",
        "replay_metrics.json",
    }
    assert expected <= {p.name for p in out_dir.iterdir() if p.is_file()}

    report = json.loads((out_dir / "belgium_alert_report.json").read_text(encoding="utf-8"))
    assert report["timeline_summary"]["status"] == "available"
    assert report["province_summary"]

    notification = json.loads((out_dir / "notification_state.json").read_text(encoding="utf-8"))
    assert notification["should_notify"] is True
    assert notification["public_alert_allowed"] is True

    timeline = json.loads((out_dir / "risk_timeseries.json").read_text(encoding="utf-8"))
    assert timeline["timeline"]
    assert timeline["summary"]["peak_score"] > 0
