from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from meteovoid.belgium import european_national_radar as module
from meteovoid.belgium.european_national_radar import (
    build_european_national_radar,
    parse_country_files,
    write_european_national_radar_outputs,
)


def test_parse_country_files() -> None:
    parsed = parse_country_files(["france:/tmp/a.npy", "netherlands:/tmp/b.csv", "bad"])
    assert parsed["france"] == [Path("/tmp/a.npy")]
    assert parsed["netherlands"] == [Path("/tmp/b.csv")]
    assert "bad" not in parsed


def test_registry_default_is_honest_without_machine_data() -> None:
    payload = build_european_national_radar(live=False)
    assert payload["contract"] == "meteovoid_european_national_radar_v1"
    assert payload["status"] == "interfaces_ready_no_machine_data"
    countries = {item["country"]: item for item in payload["countries"]}
    assert {"spain", "france", "switzerland", "netherlands"}.issubset(countries)
    assert countries["france"]["priority_for_belgium"] == "high"
    assert payload["summary"]["machine_country_count"] == 0


def test_local_country_file_becomes_machine_metric(tmp_path: Path) -> None:
    frame = tmp_path / "france.npy"
    np.save(frame, np.array([[0.0, 12.0], [35.0, 48.0]]))
    payload = build_european_national_radar(
        live=False,
        country_files={"france": [frame]},
    )
    france = next(item for item in payload["countries"] if item["country"] == "france")
    assert france["machine_radar_available"] is True
    assert france["radar_activity_score"] is not None
    assert payload["status"] == "machine_metrics_available"


def test_write_outputs_and_csv(tmp_path: Path) -> None:
    payload = write_european_national_radar_outputs(tmp_path)
    assert payload["status"] == "interfaces_ready_no_machine_data"
    for name in [
        "european_national_radar_status.json",
        "european_national_radar_metrics.json",
        "european_national_radar_sources.csv",
        "european_national_radar_map.html",
        "european_national_radar_report.md",
    ]:
        assert (tmp_path / name).exists(), name
    status = json.loads((tmp_path / "european_national_radar_status.json").read_text())
    assert status["summary"]["country_count"] >= 4


def test_generated_at_can_be_fixed_for_deterministic_outputs(tmp_path: Path) -> None:
    generated_at = "2026-01-02T03:04:05+00:00"
    payload = write_european_national_radar_outputs(tmp_path, generated_at=generated_at)
    metrics = json.loads((tmp_path / "european_national_radar_metrics.json").read_text())
    assert payload["generated_at"] == generated_at
    assert payload["metrics"]["generated_at"] == generated_at
    assert metrics["generated_at"] == generated_at


def test_source_date_epoch_controls_generated_at(monkeypatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    payload = build_european_national_radar(live=False)
    assert payload["generated_at"] == "1970-01-01T00:00:00+00:00"
    assert payload["metrics"]["generated_at"] == "1970-01-01T00:00:00+00:00"


def test_live_probe_success_without_api_key(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "cfg.yaml"
    config.write_text(
        """
contract: test
countries:
  testland:
    label: Testland
    iso2: TL
    bbox: {west: 0, south: 0, east: 1, north: 1}
    sources:
      - id: test_source
        provider: Test Provider
        evidence_level: stac_open_data
        endpoint_template: https://example.test/stac
        expected_format: STAC
""".lstrip(),
        encoding="utf-8",
    )

    def fake_probe(url: str, **kwargs: object) -> dict[str, object]:
        assert url == "https://example.test/stac"
        return {"ok": True, "status": "reachable", "http_status": 200}

    monkeypatch.setattr(module, "_http_probe", fake_probe)
    payload = build_european_national_radar(config, live=True)
    source = payload["countries"][0]["sources"][0]
    assert source["status"] == "reachable"
    assert source["ok"] is True
