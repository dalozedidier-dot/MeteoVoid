from pathlib import Path

from meteovoid.deep_platform import (
    build_convergence_matrix,
    build_country_live_contract,
    build_deep_platform_api,
    build_radar_machine_summary,
)


def test_country_live_contract_has_separated_timelines() -> None:
    contract = build_country_live_contract("germany", hours=12)

    assert contract["contract"] == "meteovoid_country_live_v1"
    assert contract["country"] == "germany"
    assert len(contract["hours"]) == 12
    assert len(contract["stations"]) >= 3
    assert len(contract["grid"]) > 0
    assert contract["timeline"]["default"] == "forecast_model"
    assert "radar_observed" in contract["timeline"]
    assert "nowcast_short_term" in contract["timeline"]
    assert contract["summary"]["national_observations"] == "brightsky_dwd"


def test_deep_platform_api_is_resilient_when_report_dir_missing(tmp_path: Path) -> None:
    payload = build_deep_platform_api(tmp_path / "missing")

    assert payload["countries"]["contract"] == "meteovoid_country_contract_index_v1"
    assert payload["validation_summary"]["contract"] == "meteovoid_validation_summary_v2"
    assert payload["explain"]["contract"] == "meteovoid_signal_explain_v1"
    assert payload["corridors"]["contract"] == "meteovoid_upstream_corridors_v1"
    assert payload["events"]["contract"] == "meteovoid_event_memory_v1"
    assert payload["radar_machine"]["contract"] == "meteovoid_radar_machine_v1"
    assert payload["temporal_layers"]["contract"] == "meteovoid_temporal_layers_v1"
    assert payload["signal_confidence"]["contract"] == "meteovoid_signal_confidence_v1"
    assert payload["station_quality_map"]["contract"] == "meteovoid_station_quality_map_v1"
    assert payload["platform"]["contract"] == "meteovoid_platform_deepening_v2"
    assert payload["convergence_matrix"]["contract"] == "meteovoid_convergence_matrix_v1"
    assert payload["country_comparison"]["contract"] == "meteovoid_country_comparison_v1"
    assert payload["forecast_ledger"]["contract"] == "meteovoid_forecast_ledger_v1"
    assert payload["operational_readiness"]["contract"] == "meteovoid_operational_readiness_v1"
    assert payload["risk_ontology"]["contract"] == "meteovoid_risk_ontology_v1"
    assert payload["action_cards"]["contract"] == "meteovoid_action_cards_v1"
    assert payload["ui_contracts"]["contract"] == "meteovoid_ui_contracts_v1"
    assert payload["source_health"]["contract"] == "meteovoid_source_health_v1"
    assert payload["schema_catalog"]["contract"] == "meteovoid_schema_catalog_v1"


def test_radar_machine_summary_keeps_files_separate_from_confirmation(tmp_path: Path) -> None:
    (tmp_path / "opera_ord_status.json").write_text(
        '{"status":"downloaded","downloaded_files":2,"machine_radar_confirmation":"unavailable"}',
        encoding="utf-8",
    )

    summary = build_radar_machine_summary(tmp_path)

    assert summary["downloaded_file_count"] == 2
    assert summary["machine_layer_ready"] is False
    assert "wradlib" in " ".join(summary["recommended_pipeline"])


def test_convergence_matrix_separates_potential_from_radar_confirmation(tmp_path: Path) -> None:
    payload = {
        "hours": [{"score": 0.8, "max_score": 0.8}],
        "stations": [{"name": "A", "score": 0.7}],
        "grid": [{"score": 0.6}],
    }

    matrix = build_convergence_matrix(tmp_path, payload)

    assert matrix["contract"] == "meteovoid_convergence_matrix_v1"
    layers = {row["id"]: row for row in matrix["layers"]}
    assert layers["model_forecast"]["available"] is True
    assert layers["radar_machine"]["available"] is False
    assert matrix["agreement_score"] < 1.0
