from pathlib import Path

from tools.generate_belgium_alert_report import (
    _auto_external_confirmation_from_sources,
    _load_calibration,
    _parse_meteoalarm_atom,
    _set_active_calibration,
    _severity_from_score,
)


def test_meteoalarm_atom_parser_detects_warning_and_thunder() -> None:
    atom = """<?xml version='1.0' encoding='UTF-8'?>
    <feed xmlns='http://www.w3.org/2005/Atom'>
      <entry><title>Orange warning for Belgium: severe thunderstorms with hail</title></entry>
    </feed>"""
    parsed = _parse_meteoalarm_atom(atom)
    assert parsed["level"] == "orange"
    assert parsed["forecast_signal"] == "severe_thunderstorms"


def test_auto_external_connector_is_fail_safe(tmp_path: Path) -> None:
    config = tmp_path / "sources.yaml"
    config.write_text(
        "rmi_warning_page_url: ''\n"
        "rmi_forecast_page_url: ''\n"
        "metealarm_atom_url: ''\n"
        "estofex_text_url: ''\n",
        encoding="utf-8",
    )
    confirmation = _auto_external_confirmation_from_sources(
        timeout_s=0.01,
        config_path=config,
        base_irm_warning_level="none",
        base_official_forecast_signal="thunderstorms",
        base_heat_warning_active=False,
        base_metealarm_level="none",
        base_estofex_level="none",
        base_radar_confirmation="none",
        base_lightning_confirmation="none",
        base_external_note="",
    )
    assert confirmation["score"] >= 0.40
    assert confirmation["auto_sources"]["enabled"] is True


def test_calibration_changes_severity_threshold(tmp_path: Path) -> None:
    cfg = tmp_path / "calibration.yaml"
    cfg.write_text("severity_thresholds:\n  high: 0.60\n", encoding="utf-8")
    calibration = _load_calibration(cfg)
    _set_active_calibration(calibration)
    try:
        assert _severity_from_score(0.61) == "high"
    finally:
        _set_active_calibration({})
