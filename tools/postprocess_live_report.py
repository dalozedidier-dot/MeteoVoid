#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class IncoherenceWeights:
    gap_hours: float = 0.30
    stuck: float = 0.20
    drift: float = 0.20
    score: float = 0.30


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except (TypeError, ValueError):
        return default


def _compute_gap_hours(stats: dict[str, Any]) -> float:
    gap_total_s = _safe_float(stats.get("gap_total_s"), 0.0)
    missing_time_s = _safe_float(stats.get("missing_time_s"), 0.0)
    return max(gap_total_s, missing_time_s) / 3600.0


def _compute_stuck(stats: dict[str, Any], meteo: dict[str, Any]) -> float:
    # Prefer explicit fields if present; otherwise infer from flags.
    stuck_points = _safe_float(stats.get("stuck_points"), 0.0)
    stuck_frac = _safe_float(stats.get("stuck_frac"), 0.0)
    flags = meteo.get("flags")
    stuck_flag = 1.0 if isinstance(flags, list) and any(str(f).lower() == "stuck" for f in flags) else 0.0
    return max(stuck_points, stuck_frac * 10.0, stuck_flag * 2.0)


def _compute_drift_from_history(history_csv: Path, *, current_mean: float) -> float:
    if not history_csv.exists():
        return 0.0

    try:
        with history_csv.open("r", encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
    except Exception:
        return 0.0

    if not rows:
        return 0.0

    # Compare to last non-empty mean_value
    for row in reversed(rows[-50:]):
        prev = row.get("mean_value", "")
        if prev:
            prev_mean = _safe_float(prev, 0.0)
            return abs(current_mean - prev_mean)
    return 0.0


def add_incoherence(latest: dict[str, Any], *, history_csv: Path, weights: IncoherenceWeights) -> dict[str, Any]:
    stats = latest.get("stats")
    if not isinstance(stats, dict):
        stats = {}

    meteo = latest.get("meteo")
    if not isinstance(meteo, dict):
        meteo = {}

    score = _safe_float(latest.get("score"), 0.0)
    mean_value = _safe_float(stats.get("mean"), 0.0)

    gap_hours = _compute_gap_hours(stats)
    stuck = _compute_stuck(stats, meteo)
    drift = _compute_drift_from_history(history_csv, current_mean=mean_value)

    phis = {
        "gap_hours": gap_hours,
        "stuck": stuck,
        "drift": drift,
        "score": score,
    }
    w = {
        "gap_hours": weights.gap_hours,
        "stuck": weights.stuck,
        "drift": weights.drift,
        "score": weights.score,
    }

    total = sum(w[k] * phis[k] for k in phis)
    breakdown = {k: round(w[k] * phis[k], 6) for k in phis}

    enriched = dict(latest)
    enriched["incoherence"] = {
        "total": round(total, 6),
        "weights": {k: w[k] for k in phis},
        "phis": {k: round(phis[k], 6) for k in phis},
        "breakdown": breakdown,
    }
    return enriched


def _bulletin_md(latest: dict[str, Any]) -> str:
    stats = latest.get("stats")
    if not isinstance(stats, dict):
        stats = {}

    meteo = latest.get("meteo")
    if not isinstance(meteo, dict):
        meteo = {}

    inco = latest.get("incoherence")
    if not isinstance(inco, dict):
        inco = {}

    lines: list[str] = []
    lines.append("# MeteoVoid bulletin (Live Smoke)")
    lines.append("")
    lines.append(f"- generated_utc: {_utc_now_iso()}")
    lines.append(f"- station_id: {latest.get('station_id')}")
    lines.append(f"- variable: {latest.get('variable')}")
    lines.append(f"- stream_id: {latest.get('stream_id')}")
    lines.append(f"- score: {latest.get('score')}")
    lines.append(f"- state: {latest.get('state')}")
    lines.append(f"- severity: {meteo.get('severity')}")
    lines.append(f"- flags: {meteo.get('flags')}")
    lines.append("")
    lines.append("## Stats")
    for k in sorted(stats.keys()):
        lines.append(f"- {k}: {stats.get(k)}")
    lines.append("")
    lines.append("## Interpretation")
    lines.append(str(meteo.get("interpretation", "")))
    lines.append("")
    lines.append("## Incoherence")
    lines.append(f"- total: {inco.get('total')}")
    b = inco.get("breakdown")
    if isinstance(b, dict):
        for k in sorted(b.keys()):
            lines.append(f"- {k}: {b.get(k)}")
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _append_history(latest: dict[str, Any], *, history_csv: Path, history_jsonl: Path) -> None:
    stats = latest.get("stats")
    if not isinstance(stats, dict):
        stats = {}

    meteo = latest.get("meteo")
    if not isinstance(meteo, dict):
        meteo = {}

    inco = latest.get("incoherence")
    if not isinstance(inco, dict):
        inco = {}

    row = {
        "ts_iso": _utc_now_iso(),
        "station_id": str(latest.get("station_id", "")),
        "variable": str(latest.get("variable", "")),
        "stream_id": str(latest.get("stream_id", "")),
        "score": _safe_float(latest.get("score")),
        "state": str(latest.get("state", "")),
        "severity": str(meteo.get("severity", "")),
        "mean_value": _safe_float(stats.get("mean")),
        "gap_count": int(_safe_float(stats.get("gap_count"))),
        "missing_time_frac": _safe_float(stats.get("missing_time_frac")),
        "incoherence_total": _safe_float(inco.get("total")),
        "incoherence_breakdown": (
            json.dumps(inco.get("breakdown"), ensure_ascii=False) if isinstance(inco.get("breakdown"), dict) else ""
        ),
    }

    history_csv.parent.mkdir(parents=True, exist_ok=True)
    history_jsonl.parent.mkdir(parents=True, exist_ok=True)

    write_header = not history_csv.exists()
    with history_csv.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if write_header:
            w.writeheader()
        w.writerow(row)

    with history_jsonl.open("a", encoding="utf-8") as f:
        f.write(json.dumps(latest, ensure_ascii=False) + "\n")


def main() -> int:
    p = argparse.ArgumentParser(description="Postprocess live_smoke latest.json into a bulletin + history.")
    p.add_argument("--latest", type=Path, required=True, help="Path to latest.json (from /latest).")
    p.add_argument("--out-dir", type=Path, required=True, help="Output directory (e.g. _ci_out/live_smoke).")
    args = p.parse_args()

    latest_path: Path = args.latest
    out_dir: Path = args.out_dir

    out_dir.mkdir(parents=True, exist_ok=True)

    latest = json.loads(latest_path.read_text(encoding="utf-8"))

    history_csv = out_dir / "history.csv"
    history_jsonl = out_dir / "history.jsonl"

    enriched = add_incoherence(latest, history_csv=history_csv, weights=IncoherenceWeights())

    (out_dir / "latest_enriched.json").write_text(json.dumps(enriched, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "bulletin.json").write_text(json.dumps(enriched, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "bulletin.md").write_text(_bulletin_md(enriched), encoding="utf-8")

    _append_history(enriched, history_csv=history_csv, history_jsonl=history_jsonl)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
