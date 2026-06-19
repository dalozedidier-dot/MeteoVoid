from __future__ import annotations

import json
from pathlib import Path

from meteovoid.belgium.bulletin_5days import build_bulletin_5days, write_bulletin_outputs
from meteovoid.belgium.official_geodata import prepare_belgium_geodata
from meteovoid.belgium.validation_history import update_validation_history


def test_offline_5day_bulletin_writes_public_contract(tmp_path: Path) -> None:
    data = build_bulletin_5days(offline_demo=True, days=5)
    write_bulletin_outputs(data, tmp_path)

    payload = json.loads((tmp_path / "weather_5days.json").read_text(encoding="utf-8"))
    assert payload["contract"] == "meteovoid_belgium_weather_5days_v1"
    assert payload["zones_count"] == 8
    assert len(payload["national_days"]) == 5
    assert (tmp_path / "weather_5days.md").exists()


def test_geodata_offline_falls_back_explicitly(tmp_path: Path) -> None:
    fallback = tmp_path / "fallback.geojson"
    fallback.write_text(
        json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8"
    )

    status = prepare_belgium_geodata(
        out_dir=tmp_path,
        fallback_province_geojson=fallback,
        offline=True,
    )

    assert status["contract"] == "meteovoid_belgium_official_geodata_v1"
    assert status["layers"][0]["status"] == "fallback_local"
    assert (tmp_path / "belgium_boundaries_provinces.geojson").exists()
    assert (tmp_path / "official_geodata_status.json").exists()


def test_validation_history_is_append_only(tmp_path: Path) -> None:
    events = tmp_path / "events.csv"
    events.write_text("date,observed\n2026-06-19,true\n", encoding="utf-8")
    report = {
        "generated_at": "2026-06-19T12:00:00Z",
        "run_id": "demo",
        "target_window": {"start": "2026-06-19", "end": "2026-06-19"},
        "operational_state": {"level": "watch_reinforced", "model_score": 0.72},
        "aggregate": {"score": 0.72},
        "province_summary": [{"province": "Brabant wallon", "max_score": 0.72}],
    }

    payload = update_validation_history(
        report=report,
        history_dir=tmp_path / "history",
        verified_events_csv=events,
        out_dir=tmp_path / "out",
    )

    assert payload["stored_run_count"] == 1
    assert payload["evaluated_run_count"] == 1
    assert payload["confusion"]["tp"] == 1
    assert (tmp_path / "out" / "forecast_history.csv").exists()
