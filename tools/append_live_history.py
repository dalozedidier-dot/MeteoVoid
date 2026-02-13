from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _iso_from_any(ts: Any) -> str:
    """Best-effort conversion to an ISO-like string.

    Accepts:
    - numeric unix timestamps (seconds)
    - already-serialized strings (kept as-is)
    """
    try:
        if isinstance(ts, int | float):
            return datetime.fromtimestamp(float(ts), tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        if isinstance(ts, str):
            return ts
    except Exception:
        return ""
    return ""


def _safe_float(x: Any) -> float | None:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _safe_int(x: Any) -> int | None:
    try:
        if x is None:
            return None
        return int(x)
    except Exception:
        return None


def _get(d: dict[str, Any], key: str) -> Any:
    return d.get(key)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Append latest.json into history.csv and history.jsonl."
    )
    p.add_argument("--latest", required=True, help="Path to latest.json")
    p.add_argument(
        "--out-dir",
        required=True,
        help="Output directory (where history.* live)",
    )
    args = p.parse_args(argv)

    latest_path = Path(args.latest)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not latest_path.exists():
        raise SystemExit(f"latest.json not found: {latest_path}")

    obj_any = json.loads(latest_path.read_text(encoding="utf-8"))
    if not isinstance(obj_any, dict):
        raise SystemExit("latest.json must be a JSON object")

    obj: dict[str, Any] = obj_any

    stats = obj.get("stats")
    if not isinstance(stats, dict):
        stats = {}

    meteo = obj.get("meteo")
    if not isinstance(meteo, dict):
        meteo = {}

    flags = meteo.get("flags")
    if not isinstance(flags, list):
        flags = []

    row: dict[str, Any] = {
        "ts": _safe_float(_get(obj, "ts")),
        "ts_iso": _iso_from_any(_get(obj, "ts")),
        "ts_ingest": _safe_float(_get(obj, "ts_ingest")),
        "ts_ingest_iso": _iso_from_any(_get(obj, "ts_ingest")),
        "station_id": _get(obj, "station_id") or "",
        "variable": _get(obj, "variable") or "",
        "stream_id": _get(obj, "stream_id") or "",
        "score": _safe_float(_get(obj, "score")),
        "state": _get(obj, "state") or "",
        "severity": meteo.get("severity") or "",
        "flags": json.dumps(flags, ensure_ascii=False),
        "n_points": _safe_int(stats.get("n_points")),
        "gap_count": _safe_int(stats.get("gap_count")),
        "missing_time_frac": _safe_float(stats.get("missing_time_frac")),
    }

    # Append JSONL (full object + a couple of helper iso fields)
    jsonl_path = out_dir / "history.jsonl"
    enriched = dict(obj)
    enriched["ts_iso"] = row["ts_iso"]
    enriched["ts_ingest_iso"] = row["ts_ingest_iso"]
    with jsonl_path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(enriched, ensure_ascii=False))
        f.write("\n")

    # Append CSV (stable small schema for quick plotting)
    csv_path = out_dir / "history.csv"
    fieldnames = [
        "ts",
        "ts_iso",
        "ts_ingest",
        "ts_ingest_iso",
        "station_id",
        "variable",
        "stream_id",
        "score",
        "state",
        "severity",
        "flags",
        "n_points",
        "gap_count",
        "missing_time_frac",
    ]

    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    with csv_path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            w.writeheader()
        w.writerow(row)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
