# tools/validate_latest_report.py
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Fail:
    msg: str


def _is_number(x: Any) -> bool:
    # ruff UP038: prefer PEP 604 union in isinstance
    return isinstance(x, int | float) and not isinstance(x, bool)


def _req(obj: dict[str, Any], key: str) -> Any | Fail:
    if key not in obj:
        return Fail(f"missing key: {key}")
    return obj[key]


def _req_str(obj: dict[str, Any], key: str) -> str | Fail:
    v = _req(obj, key)
    if isinstance(v, Fail):
        return v
    if not isinstance(v, str):
        return Fail(f"key '{key}' must be str, got {type(v).__name__}")
    if not v:
        return Fail(f"key '{key}' must be non-empty")
    return v


def _req_num(obj: dict[str, Any], key: str) -> float | Fail:
    v = _req(obj, key)
    if isinstance(v, Fail):
        return v
    if not _is_number(v):
        return Fail(f"key '{key}' must be number, got {type(v).__name__}")
    return float(v)


def _req_int(obj: dict[str, Any], key: str) -> int | Fail:
    v = _req(obj, key)
    if isinstance(v, Fail):
        return v
    if not isinstance(v, int) or isinstance(v, bool):
        return Fail(f"key '{key}' must be int, got {type(v).__name__}")
    return v


def _req_list_str(obj: dict[str, Any], key: str) -> list[str] | Fail:
    v = _req(obj, key)
    if isinstance(v, Fail):
        return v
    if not isinstance(v, list) or any(not isinstance(x, str) for x in v):
        return Fail(f"key '{key}' must be list[str]")
    return v


def _req_dict(obj: dict[str, Any], key: str) -> dict[str, Any] | Fail:
    v = _req(obj, key)
    if isinstance(v, Fail):
        return v
    if not isinstance(v, dict):
        return Fail(f"key '{key}' must be object, got {type(v).__name__}")
    return v


def validate(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    score = _req_num(report, "score")
    if isinstance(score, Fail):
        errors.append(score.msg)
    else:
        if not (0.0 <= score <= 1.0):
            errors.append("score must be in [0, 1]")

    state = _req_str(report, "state")
    if isinstance(state, Fail):
        errors.append(state.msg)
    else:
        if state not in {"stable", "transition", "unstable"}:
            errors.append("state must be one of: stable, transition, unstable")

    for k in ("station_id", "variable", "stream_id"):
        v = _req_str(report, k)
        if isinstance(v, Fail):
            errors.append(v.msg)

    for k in ("ts", "ts_ingest"):
        v = _req_num(report, k)
        if isinstance(v, Fail):
            errors.append(v.msg)

    stats = _req_dict(report, "stats")
    if isinstance(stats, Fail):
        errors.append(stats.msg)
    else:
        for k in ("n_points", "gap_count"):
            v = _req_int(stats, k)
            if isinstance(v, Fail):
                errors.append(f"stats.{v.msg}")

        for k in (
            "min",
            "max",
            "mean",
            "p95",
            "dt_median_s",
            "gap_max_s",
            "gap_total_s",
            "missing_time_s",
            "missing_time_frac",
        ):
            v = _req_num(stats, k)
            if isinstance(v, Fail):
                errors.append(f"stats.{v.msg}")

        mtf = stats.get("missing_time_frac")
        if _is_number(mtf) and not (0.0 <= float(mtf) <= 1.0):
            errors.append("stats.missing_time_frac must be in [0, 1]")

    meteo = _req_dict(report, "meteo")
    if isinstance(meteo, Fail):
        errors.append(meteo.msg)
    else:
        v = _req_str(meteo, "interpretation")
        if isinstance(v, Fail):
            errors.append(f"meteo.{v.msg}")

        v = _req_list_str(meteo, "flags")
        if isinstance(v, Fail):
            errors.append(f"meteo.{v.msg}")

        sev = _req_str(meteo, "severity")
        if isinstance(sev, Fail):
            errors.append(f"meteo.{sev.msg}")
        else:
            if sev not in {"low", "medium", "high"}:
                errors.append("meteo.severity must be one of: low, medium, high")

    return errors


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python tools/validate_latest_report.py path/to/latest.json", file=sys.stderr)
        return 2

    p = Path(argv[1])
    if not p.exists():
        print(f"file not found: {p}", file=sys.stderr)
        return 2

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"invalid json: {e}", file=sys.stderr)
        return 2

    if not isinstance(data, dict):
        print("latest.json must be a JSON object", file=sys.stderr)
        return 2

    errors = validate(data)
    if errors:
        print("latest.json validation failed:", file=sys.stderr)
        for e in errors:
            print(f"- {e}", file=sys.stderr)
        return 1

    print("latest.json OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
