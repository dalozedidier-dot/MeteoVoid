"""Historical validation scaffold for MeteoVoid Belgium runs."""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

POSITIVE_LEVELS = {"watch_reinforced", "pre_alert_confirmed", "alert_confirmed", "alert"}


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _target_date(report: dict[str, Any]) -> str:
    window = report.get("target_window") if isinstance(report.get("target_window"), dict) else {}
    return str(window.get("start") or report.get("window_start") or "")[:10]


def _prediction_row(report: dict[str, Any]) -> dict[str, Any]:
    op = report.get("operational_state") if isinstance(report.get("operational_state"), dict) else {}
    aggregate = report.get("aggregate") if isinstance(report.get("aggregate"), dict) else {}
    level = str(op.get("level") or aggregate.get("severity") or "normal")
    probability = max(_num(op.get("model_score")), _num(aggregate.get("score")))
    return {
        "generated_at": report.get("generated_at") or _now_iso(),
        "run_id": report.get("run_id") or "",
        "target_date": _target_date(report),
        "operational_level": level,
        "model_probability": round(probability, 6),
        "predicted_positive": str(level in POSITIVE_LEVELS or probability >= 0.55).lower(),
        "main_zone": _main_zone(report),
    }


def _main_zone(report: dict[str, Any]) -> str:
    provinces = report.get("province_summary") if isinstance(report.get("province_summary"), list) else []
    best_name = ""
    best_score = -1.0
    for item in provinces:
        if not isinstance(item, dict):
            continue
        name = str(item.get("province") or "")
        if name.lower().startswith(("approche", "france", "pays-bas", "allemagne")):
            continue
        score = _num(item.get("max_score"), -1.0)
        if score > best_score:
            best_name, best_score = name, score
    return best_name


def _event_observed_for_date(events: list[dict[str, str]], target: str) -> bool | None:
    if not target:
        return None
    matched = []
    for row in events:
        start = str(row.get("date_start") or row.get("start") or row.get("date") or "")[:10]
        end = str(row.get("date_end") or row.get("end") or row.get("date") or start)[:10]
        if start and start <= target <= (end or start):
            matched.append(row)
    if not matched:
        return None
    return any(
        str(row.get("observed") or row.get("event") or row.get("expected_detected") or "")
        .strip()
        .lower()
        in {"1", "true", "yes", "oui", "severe", "detected", "event"}
        for row in matched
    )


def _scores(rows: list[dict[str, str]], events: list[dict[str, str]]) -> dict[str, Any]:
    tp = fp = fn = tn = 0
    briers: list[float] = []
    evaluated = 0
    for row in rows:
        target = str(row.get("target_date") or "")[:10]
        observed = _event_observed_for_date(events, target)
        if observed is None:
            continue
        predicted = str(row.get("predicted_positive") or "").lower() == "true"
        prob = _num(row.get("model_probability"))
        if predicted and observed:
            tp += 1
        elif predicted and not observed:
            fp += 1
        elif not predicted and observed:
            fn += 1
        else:
            tn += 1
        briers.append((prob - (1.0 if observed else 0.0)) ** 2)
        evaluated += 1
    pod = tp / (tp + fn) if (tp + fn) else None
    far = fp / (tp + fp) if (tp + fp) else None
    csi = tp / (tp + fp + fn) if (tp + fp + fn) else None
    return {
        "evaluated_run_count": evaluated,
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "scores": {
            "pod": pod,
            "far": far,
            "csi": csi,
            "brier_score": sum(briers) / len(briers) if briers else None,
        },
    }


def update_validation_history(
    *,
    report: dict[str, Any],
    history_dir: Path,
    verified_events_csv: Path,
    out_dir: Path,
) -> dict[str, Any]:
    history_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = history_dir / "forecast_history.csv"
    row = _prediction_row(report)
    fieldnames = list(row)
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    with csv_path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerow(row)

    rows = _read_csv(csv_path)
    events = _read_csv(verified_events_csv)
    metrics = _scores(rows, events)
    status = "needs_verified_events"
    if metrics["evaluated_run_count"] > 0:
        status = "under_calibration"
        csi = metrics["scores"].get("csi")
        if csi is not None and csi >= 0.4:
            status = "usable_but_keep_calibrating"
    payload = {
        "contract": "meteovoid_belgium_validation_history_v1",
        "generated_at": _now_iso(),
        "status": status,
        "history_file": str(csv_path),
        "verified_events_file": str(verified_events_csv),
        "stored_run_count": len(rows),
        "last_prediction": row,
        **metrics,
        "note": (
            "Append-only forecast history. Metrics become meaningful only when verified events are "
            "added after the fact; this avoids validating forecasts against their own assumptions."
        ),
    }
    (out_dir / "validation_history.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out_dir / "forecast_history.csv").write_text(csv_path.read_text(encoding="utf-8"), encoding="utf-8")
    return payload
