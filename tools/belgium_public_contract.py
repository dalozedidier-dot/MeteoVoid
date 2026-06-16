from __future__ import annotations

from typing import Any

BELGIUM_PUBLIC_LATEST_SCHEMA = "meteovoid_belgium_public_latest_v1"


def build_belgium_public_latest(report: dict[str, Any]) -> dict[str, Any]:
    aggregate = report.get("aggregate") if isinstance(report.get("aggregate"), dict) else {}
    return {
        "schema": BELGIUM_PUBLIC_LATEST_SCHEMA,
        "contract": "belgium_public_latest_v1",
        "generated_at": report.get("generated_at"),
        "run_id": report.get("run_id"),
        "target_window": report.get("target_window"),
        "aggregate": aggregate,
        "score_layers": {
            "heat_stress_score": aggregate.get("heat_stress_score"),
            "convective_risk_score": aggregate.get("convective_risk_score"),
            "heat_stress_mean": aggregate.get("heat_stress_mean"),
            "convective_risk_mean": aggregate.get("convective_risk_mean"),
            "contract": aggregate.get("score_layer_contract"),
        },
        "operational_state": report.get("operational_state"),
        "external_confirmation": report.get("external_confirmation"),
        "trend": report.get("trend"),
        "outputs": report.get("outputs"),
        "disclaimer": "Prototype technique non officiel. Toujours consulter les sources officielles.",
        "contract_note": (
            "This Belgium static public contract is distinct from the live Redis /latest payload "
            "validated by tools/validate_latest_report.py."
        ),
    }
