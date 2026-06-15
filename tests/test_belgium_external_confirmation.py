from tools.generate_belgium_alert_report import _external_confirmation_from_inputs


def test_official_forecast_signal_lifts_external_confirmation_score():
    confirmation = _external_confirmation_from_inputs(
        irm_warning_level="none",
        official_forecast_signal="severe_thunderstorms",
        heat_warning_active=True,
        metealarm_level="none",
        estofex_level="none",
        radar_confirmation="none",
        lightning_confirmation="none",
        external_note="",
    )

    assert confirmation["score"] >= 0.40
    assert confirmation["status"] == "partially_confirmed"
    assert confirmation["inputs"]["effective_official_forecast_signal"] == "severe_thunderstorms"


def test_external_note_can_infer_official_forecast_signal_when_irm_is_named():
    confirmation = _external_confirmation_from_inputs(
        irm_warning_level="none",
        official_forecast_signal="none",
        heat_warning_active=False,
        metealarm_level="none",
        estofex_level="none",
        radar_confirmation="none",
        lightning_confirmation="none",
        external_note="IRM annonce un risque d'orages violents avec grêle et fortes rafales.",
    )

    assert confirmation["inputs"]["inferred_official_forecast_signal"] == "severe_thunderstorms"
    assert confirmation["score"] >= 0.40
