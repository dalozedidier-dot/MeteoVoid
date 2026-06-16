from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ContractError(Exception):
    """Raised when a Belgium alert output does not match the minimal contract."""

    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractError(str(path), "missing file") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(str(path), f"invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ContractError(str(path), "top-level JSON value must be an object")
    return payload


def _require_keys(path: Path, payload: dict[str, Any], keys: list[str]) -> None:
    missing = [key for key in keys if key not in payload]
    if missing:
        raise ContractError(str(path), f"missing required keys: {', '.join(missing)}")


def validate_report(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    _require_keys(
        path,
        payload,
        [
            "generated_at",
            "target_window",
            "aggregate",
            "stations",
            "data_mode",
            "source_type",
            "external_confirmation",
            "operational_state",
        ],
    )
    aggregate = payload.get("aggregate")
    if not isinstance(aggregate, dict):
        raise ContractError(str(path), "aggregate must be an object")
    _require_keys(path, aggregate, ["score", "severity", "source_ok_count", "source_error_count"])
    stations = payload.get("stations")
    if not isinstance(stations, list):
        raise ContractError(str(path), "stations must be a list")
    for idx, station in enumerate(stations):
        if not isinstance(station, dict):
            raise ContractError(str(path), f"stations[{idx}] must be an object")
        _require_keys(
            path,
            station,
            ["station_id", "name", "score", "severity", "source_ok", "signals"],
        )
    return payload


def validate_alert_state(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    _require_keys(
        path,
        payload,
        [
            "level",
            "reason",
            "model_score",
            "external_confirmation_score",
            "notification_allowed",
            "public_wording",
            "official_alert",
        ],
    )
    return payload


def validate_source_status(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    _require_keys(path, payload, ["source_health_score", "source_ok_count", "source_error_count"])
    return payload


def validate_notification_state(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    _require_keys(
        path,
        payload,
        [
            "generated_at",
            "should_notify",
            "cooldown_hours",
            "dedupe_key",
            "notification_allowed",
            "public_wording",
            "official_alert",
        ],
    )
    return payload


def validate_output_directory(out_dir: Path | str) -> dict[str, dict[str, Any]]:
    root = Path(out_dir)
    return {
        "report": validate_report(root / "belgium_alert_report.json"),
        "alert_state": validate_alert_state(root / "alert_state.json"),
        "source_status": validate_source_status(root / "source_status.json"),
        "notification_state": validate_notification_state(root / "notification_state.json"),
    }
