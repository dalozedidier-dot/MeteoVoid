from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _iso_from_any(ts: Any) -> str:
    try:
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        pass
    return ""


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Append latest.json into history.csv and history.jsonl.")
    p.add_argument("--latest", required=True, help="Path to latest.json")
    p.add_argument("--out-dir", required=True, help="Output directory (where history.* live)")
    args = p.parse_args(argv)

    latest_path = Path(args.latest)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    obj = json.loads(latest_path.read_text(encoding="utf-8"))

    station_id = str(obj.get("station_id") or "")
    variable = str(obj.get("variable") or "")
    score = obj.get("score")
    state = str(obj.get("state") or "")
    meteo = obj.get("meteo") if isinstance(obj.get("meteo"), dict) else {}
    severity = str(meteo.get("severity") or "")
    flags = meteo.get("flags") if isinstance(meteo.get("flags"), list) else []
    flags_s = ",".join(str(x) for x in flags if str(x).strip())

    stats = obj.get("stats") if isinstance(obj.get("stats"), dict) else {}
    n_points = stats.get("n_points")
    gap_count = stats.get("gap_count")
    missing_frac = stats.get("missing_time_frac")
    imputed_frac = stats.get("imputed_frac")

    ts_ingest = obj.get("ts_ingest")
    ts_ingest_iso = _iso_from_any(ts_ingest)
    if not ts_ingest_iso:
        ts_ingest_iso = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    row = {
        "ts_ingest": ts_ingest,
        "ts_ingest_iso": ts_ingest_iso,
        "station_id": station_id,
        "variable": variable,
        "score": score,
        "state": state,
        "severity": severity,
        "flags": flags_s,
        "n_points": n_points,
        "gap_count": gap_count,
        "missing_time_frac": missing_frac,
        "imputed_frac": imputed_frac,
    }

    # JSONL (append)
    jsonl_path = out_dir / "history.jsonl"
    with jsonl_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # CSV (append with header if missing/empty)
    csv_path = out_dir / "history.csv"
    need_header = (not csv_path.exists()) or (csv_path.stat().st_size == 0)
    fieldnames = list(row.keys())
    with csv_path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if need_header:
            w.writeheader()
        w.writerow(row)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
