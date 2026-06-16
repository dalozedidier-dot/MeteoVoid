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


def test_partial_external_confirmation_stays_pre_alert() -> None:
    from tools.generate_belgium_alert_report import _operational_state

    report = {
        "aggregate": {
            "score": 0.86,
            "severity": "alert",
            "source_ok_count": 1,
            "source_error_count": 0,
        },
        "external_confirmation": {
            "score": 0.45,
            "inputs": {
                "irm_warning_level": "none",
                "metealarm_level": "none",
                "estofex_level": "none",
                "radar_confirmation": "none",
                "lightning_confirmation": "none",
            },
        },
        "trend": {"status": "stable"},
        "source_status": {"source_health_score": 1.0},
    }

    state = _operational_state(report)

    assert state["level"] == "pre_alert_confirmed"
    assert state["official_alert"] is False
    assert state["strong_external_confirmation"] is False
    assert state["public_wording"] != "alerte technique confirmée, non officielle"


def test_strong_external_confirmation_allows_confirmed_signal() -> None:
    from tools.generate_belgium_alert_report import _operational_state

    report = {
        "aggregate": {
            "score": 0.86,
            "severity": "alert",
            "source_ok_count": 1,
            "source_error_count": 0,
        },
        "external_confirmation": {
            "score": 0.82,
            "inputs": {
                "irm_warning_level": "orange",
                "metealarm_level": "none",
                "estofex_level": "none",
                "radar_confirmation": "none",
                "lightning_confirmation": "none",
            },
        },
        "trend": {"status": "stable"},
        "source_status": {"source_health_score": 1.0},
    }

    state = _operational_state(report)

    assert state["level"] == "alert_confirmed"
    assert state["official_alert"] is True
    assert state["strong_external_confirmation"] is True
    assert state["public_alert_allowed"] is True
