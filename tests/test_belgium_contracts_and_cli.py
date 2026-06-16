from __future__ import annotations

import json
from pathlib import Path

from meteovoid.belgium.contracts import validate_output_directory
from tools.generate_belgium_alert_report import main as generate_main


def test_belgium_outputs_respect_minimal_contracts(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    history_dir = tmp_path / "history"
    rc = generate_main(
        [
            "--stations",
            "config/stations_belgium.yaml",
            "--out-dir",
            str(out_dir),
            "--history-dir",
            str(history_dir),
            "--target-date",
            "2026-06-19",
            "--offline-demo",
            "--official-forecast-signal",
            "severe_thunderstorms",
            "--heat-warning-active",
        ]
    )
    assert rc == 0
    validate_output_directory(out_dir)

    alert_state = json.loads((out_dir / "alert_state.json").read_text(encoding="utf-8"))
    assert "notification_allowed" in alert_state
    assert "public_wording" in alert_state
    assert alert_state["official_alert"] is False


def test_schema_files_are_valid_json() -> None:
    for path in Path("schemas").glob("*.schema.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["$schema"].startswith("https://json-schema.org/")
        assert payload["type"] == "object"
