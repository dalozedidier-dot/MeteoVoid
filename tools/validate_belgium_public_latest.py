from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REQUIRED_TOP_LEVEL = {
    "schema",
    "contract",
    "generated_at",
    "run_id",
    "target_window",
    "aggregate",
    "score_layers",
    "operational_state",
    "disclaimer",
}


def validate_payload(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED_TOP_LEVEL - set(payload))
    if missing:
        errors.append("missing top-level keys: " + ", ".join(missing))
    if payload.get("schema") != "meteovoid_belgium_public_latest_v1":
        errors.append("schema must be meteovoid_belgium_public_latest_v1")
    if payload.get("contract") != "belgium_public_latest_v1":
        errors.append("contract must be belgium_public_latest_v1")
    score_layers = payload.get("score_layers")
    if not isinstance(score_layers, dict):
        errors.append("score_layers must be an object")
    else:
        for key in ["heat_stress_score", "convective_risk_score", "contract"]:
            if key not in score_layers:
                errors.append(f"score_layers.{key} is required")
    aggregate = payload.get("aggregate")
    if not isinstance(aggregate, dict):
        errors.append("aggregate must be an object")
    elif "score" not in aggregate or "severity" not in aggregate:
        errors.append("aggregate.score and aggregate.severity are required")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Belgium static public latest contract.")
    parser.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    payload = json.loads(args.path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("payload must be a JSON object")
    errors = validate_payload(payload)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("OK: belgium public latest contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
