from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


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


def _iso_from_any(ts: Any) -> str:
    try:
        if isinstance(ts, int | float):
            return datetime.fromtimestamp(float(ts), tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        if isinstance(ts, str):
            return ts
    except Exception:
        return ""
    return ""


def _read_json(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise SystemExit(f"Expected JSON object in {path}")
    return obj


def _read_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return _read_json(path)


def _read_history_rows(history_csv: Path) -> list[dict[str, str]]:
    if not history_csv.exists() or history_csv.stat().st_size == 0:
        return []
    with history_csv.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        return [row for row in r if isinstance(row, dict)]


def _history_stats_for(
    rows: list[dict[str, str]], station_id: str, variable: str, *, limit: int = 48
) -> tuple[float | None, float | None]:
    vals: list[float] = []
    for row in rows[::-1]:
        if row.get("station_id") != station_id or row.get("variable") != variable:
            continue
        for key in ("mean_value", "stats_mean", "mean"):
            v = _safe_float(row.get(key))
            if v is not None:
                vals.append(v)
                break
        if len(vals) >= limit:
            break

    if len(vals) < 5:
        return None, None

    mu = sum(vals) / len(vals)
    var = sum((x - mu) ** 2 for x in vals) / max(1, (len(vals) - 1))
    return mu, var**0.5


def _derive_smoke_index(latest: dict[str, Any]) -> float | None:
    for key in ("current_smoke_index", "smoke_index", "aqi", "air_quality_index"):
        v = _safe_float(latest.get(key))
        if v is not None:
            return v

    meteo = latest.get("meteo")
    if isinstance(meteo, dict):
        for key in ("current_smoke_index", "smoke_index", "aqi", "air_quality_index"):
            v = _safe_float(meteo.get(key))
            if v is not None:
                return v

    var = str(latest.get("variable") or "")
    if any(s in var.lower() for s in ("pm25", "pm2.5", "pm2_5", "aqi", "smoke")):
        stats = latest.get("stats")
        if isinstance(stats, dict):
            return _safe_float(stats.get("mean"))
    return None


def compute_incoherence(
    latest: dict[str, Any],
    *,
    history_rows: list[dict[str, str]],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    stats = latest.get("stats")
    if not isinstance(stats, dict):
        stats = {}

    station_id = str(latest.get("station_id") or "")
    variable = str(latest.get("variable") or "")

    gap_total_s = _safe_float(stats.get("gap_total_s")) or 0.0
    missing_time_s = _safe_float(stats.get("missing_time_s")) or 0.0
    gap_hours = max(gap_total_s, missing_time_s) / 3600.0

    vmin = _safe_float(stats.get("min"))
    vmax = _safe_float(stats.get("max"))
    n_points = _safe_int(stats.get("n_points")) or 0

    eps_range = float(cfg.get("stuck_eps_range", 0.02))
    min_points_for_stuck = int(cfg.get("stuck_min_points", 30))
    stuck_count = 0.0
    if vmin is not None and vmax is not None and n_points >= min_points_for_stuck:
        if abs(vmax - vmin) <= eps_range:
            stuck_count = 1.0

    smoke_index = _derive_smoke_index(latest)
    smoke_baseline = float(cfg.get("smoke_baseline", 50.0))
    smoke_scale = float(cfg.get("smoke_scale", 100.0))
    smoke_dev = 0.0
    if smoke_index is not None:
        smoke_dev = max(0.0, smoke_index - smoke_baseline) / max(1e-9, smoke_scale)

    hist_mu, hist_sigma = _history_stats_for(history_rows, station_id, variable)
    cur_mean = _safe_float(stats.get("mean"))
    drift_z = 0.0
    if cur_mean is not None and hist_mu is not None and hist_sigma is not None and hist_sigma > 0:
        drift_z = abs(cur_mean - hist_mu) / hist_sigma

    weights: dict[str, float] = {
        "smoke": float(cfg.get("w_smoke", 0.5)),
        "gap": float(cfg.get("w_gap", 0.3)),
        "stuck": float(cfg.get("w_stuck", 0.2)),
        "drift": float(cfg.get("w_drift", 0.2)),
    }

    per_var = cfg.get("per_variable")
    if isinstance(per_var, dict) and variable in per_var and isinstance(per_var[variable], dict):
        ov = per_var[variable]
        for k_cfg, k_w in (
            ("w_smoke", "smoke"),
            ("w_gap", "gap"),
            ("w_stuck", "stuck"),
            ("w_drift", "drift"),
        ):
            if k_cfg in ov:
                weights[k_w] = float(ov[k_cfg])

    phis: dict[str, float] = {
        "smoke_dev": smoke_dev,
        "gap_hours": gap_hours,
        "stuck_count": stuck_count,
        "drift_z": drift_z,
    }

    total = 0.0
    total += weights["smoke"] * phis["smoke_dev"]
    total += weights["gap"] * phis["gap_hours"]
    total += weights["stuck"] * phis["stuck_count"]
    total += weights["drift"] * phis["drift_z"]

    breakdown = {
        "smoke": round(weights["smoke"] * phis["smoke_dev"], 4),
        "gap": round(weights["gap"] * phis["gap_hours"], 4),
        "stuck": round(weights["stuck"] * phis["stuck_count"], 4),
        "drift": round(weights["drift"] * phis["drift_z"], 4),
    }

    return {
        "total": round(total, 4),
        "breakdown": breakdown,
        "phis": {k: round(v, 4) for k, v in phis.items()},
        "weights": {k: round(v, 4) for k, v in weights.items()},
        "meta": {
            "smoke_index": round(smoke_index, 4) if smoke_index is not None else None,
            "hist_mean": round(hist_mu, 4) if hist_mu is not None else None,
            "hist_std": round(hist_sigma, 4) if hist_sigma is not None else None,
        },
    }


def _render_bulletin_md(latest: dict[str, Any]) -> str:
    inco_total = latest.get("incoherence_score")
    breakdown = latest.get("incoherence_contributions")
    if not isinstance(breakdown, dict):
        breakdown = None

    meteo = latest.get("meteo")
    severity = None
    flags: list[str] = []
    if isinstance(meteo, dict):
        severity = meteo.get("severity")
        fl = meteo.get("flags")
        if isinstance(fl, list):
            flags = [str(x) for x in fl if x is not None]

    lines: list[str] = []
    lines.append("# MeteoVoid Live Bulletin")
    lines.append("")
    lines.append(f"- station_id: {latest.get('station_id')}")
    lines.append(f"- variable: {latest.get('variable')}")
    lines.append(f"- state: {latest.get('state')}")
    lines.append(f"- severity: {severity}")
    lines.append(f"- score: {latest.get('score')}")
    lines.append(f"- incoherence_score: {inco_total}")
    if flags:
        lines.append(f"- flags: {', '.join(flags)}")
    lines.append("")

    if isinstance(breakdown, dict):
        lines.append("## Incohérence globale (Σ wᵢ φᵢ)")
        lines.append("")
        for k, v in sorted(breakdown.items(), key=lambda kv: float(kv[1]), reverse=True):
            lines.append(f"- {k}: {v}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _append_history(latest: dict[str, Any], *, history_csv: Path, history_jsonl: Path) -> None:
    stats = latest.get("stats")
    if not isinstance(stats, dict):
        stats = {}

    meteo = latest.get("meteo")
    severity = ""
    if isinstance(meteo, dict) and meteo.get("severity") is not None:
        severity = str(meteo.get("severity"))

    gap_total_s = _safe_float(stats.get("gap_total_s")) or 0.0
    missing_time_s = _safe_float(stats.get("missing_time_s")) or 0.0
    gap_hours = max(gap_total_s, missing_time_s) / 3600.0

    row: dict[str, Any] = {
        "ts": _safe_float(latest.get("ts")),
        "ts_iso": _iso_from_any(latest.get("ts")),
        "station_id": str(latest.get("station_id") or ""),
        "variable": str(latest.get("variable") or ""),
        "score": _safe_float(latest.get("score")),
        "state": str(latest.get("state") or ""),
        "severity": severity,
        "mean_value": _safe_float(stats.get("mean")),
        "gap_hours": round(gap_hours, 6),
        "incoherence_total": _safe_float(latest.get("incoherence_score")),
        "incoherence_breakdown": json.dumps(
            latest.get("incoherence_contributions"), ensure_ascii=False
        )
        if isinstance(latest.get("incoherence_contributions"), dict)
        else "",
    }

    enriched = dict(latest)
    enriched["ts_iso"] = row["ts_iso"]
    with history_jsonl.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(enriched, ensure_ascii=False))
        f.write("\n")

    fieldnames = [
        "ts",
        "ts_iso",
        "station_id",
        "variable",
        "score",
        "state",
        "severity",
        "mean_value",
        "gap_hours",
        "incoherence_total",
        "incoherence_breakdown",
    ]
    write_header = not history_csv.exists() or history_csv.stat().st_size == 0
    with history_csv.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            w.writeheader()
        w.writerow(row)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Post-process latest.json: add incoherence score + bulletin + history."
    )
    ap.add_argument("--latest", required=True, help="Path to latest.json")
    ap.add_argument("--out-dir", required=True, help="Output directory for bulletin/history")
    ap.add_argument("--config", default="config/incoherence.json", help="Config JSON path.")
    args = ap.parse_args(argv)

    latest_path = Path(args.latest)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = _read_config(Path(args.config))
    latest = _read_json(latest_path)

    history_csv = out_dir / "history.csv"
    history_jsonl = out_dir / "history.jsonl"
    rows = _read_history_rows(history_csv)

    inco = compute_incoherence(latest, history_rows=rows, cfg=cfg)
    latest["incoherence"] = inco
    latest["incoherence_score"] = inco.get("total")
    latest["incoherence_contributions"] = inco.get("breakdown")

    latest_path.write_text(
        json.dumps(latest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    (out_dir / "bulletin.json").write_text(
        json.dumps(
            {
                "station_id": latest.get("station_id"),
                "variable": latest.get("variable"),
                "state": latest.get("state"),
                "severity": (
                    (latest.get("meteo") or {}).get("severity")
                    if isinstance(latest.get("meteo"), dict)
                    else None
                ),
                "score": latest.get("score"),
                "incoherence_score": latest.get("incoherence_score"),
                "contributions": latest.get("incoherence_contributions"),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (out_dir / "bulletin.md").write_text(_render_bulletin_md(latest), encoding="utf-8")

    _append_history(latest, history_csv=history_csv, history_jsonl=history_jsonl)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
