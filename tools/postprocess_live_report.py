"""Post-process Live Smoke artifacts to produce a usable bulletin, history, and incoherence summary.

Inputs:
- latest.json: a single report from /latest (validated by tools/validate_latest_report.py)

Outputs (in out-dir):
- latest_enriched.json
- bulletin.json
- bulletin.md
- history.csv (append-only)
- history.jsonl (append-only)

Notes:
- Keeps latest.json numeric timestamps (ts, ts_ingest) intact.
- Adds ts_iso and ts_ingest_iso for human readability.
- Adds incoherence_score and incoherence_contributions for convenience.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _epoch(dt: datetime) -> float:
    return float(dt.timestamp())


def _iso_from_epoch(ts: float) -> str:
    dt = datetime.fromtimestamp(float(ts), tz=UTC)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_float(x: Any) -> float | None:
    if isinstance(x, bool):
        return None
    if isinstance(x, int | float):
        return float(x)
    try:
        return float(str(x).strip())
    except Exception:
        return None


def _safe_int(x: Any) -> int | None:
    if isinstance(x, bool):
        return None
    if isinstance(x, int):
        return x
    try:
        return int(str(x).strip())
    except Exception:
        return None


def _safe_str(x: Any) -> str | None:
    if not isinstance(x, str):
        return None
    s = x.strip()
    return s if s else None


def _load_json(p: Path) -> dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class IncoherenceConfig:
    weights: dict[str, float]
    smoke_threshold: float
    stuck_eps: float
    drift_window: int


def _default_incoherence_config() -> IncoherenceConfig:
    return IncoherenceConfig(
        weights={
            "gap_hours": 0.30,
            "smoke": 0.00,
            "stuck": 0.20,
            "drift": 0.00,
            "out_of_range": 0.15,
            "score": 0.35,
        },
        smoke_threshold=50.0,
        stuck_eps=1e-9,
        drift_window=30,
    )


def _load_incoherence_config(path: str | None) -> IncoherenceConfig:
    default = _default_incoherence_config()
    if not path:
        return default

    p = Path(path)
    if not p.exists():
        return default

    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default

    weights = dict(default.weights)
    w = d.get("weights") if isinstance(d, dict) else None
    if isinstance(w, dict):
        for k, v in w.items():
            if (
                isinstance(k, str)
                and isinstance(v, int | float)
                and not isinstance(v, bool)
            ):
                weights[k] = float(v)

    smoke_threshold = (
        _safe_float(d.get("smoke_threshold")) if isinstance(d, dict) else None
    )
    stuck_eps = _safe_float(d.get("stuck_eps")) if isinstance(d, dict) else None
    drift_window = _safe_int(d.get("drift_window")) if isinstance(d, dict) else None

    return IncoherenceConfig(
        weights=weights,
        smoke_threshold=float(
            smoke_threshold if smoke_threshold is not None else default.smoke_threshold
        ),
        stuck_eps=float(stuck_eps if stuck_eps is not None else default.stuck_eps),
        drift_window=int(
            drift_window if drift_window is not None else default.drift_window
        ),
    )


def _history_recent_means(
    history_csv: Path,
    station_id: str,
    variable: str,
    window: int,
) -> list[float]:
    """Return recent stats.mean values from history for drift detection."""
    if window <= 0 or not history_csv.exists():
        return []

    rows: list[dict[str, str]] = []
    with history_csv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for d in reader:
            if (d.get("station_id", "") or "").strip() != station_id:
                continue
            if (d.get("variable", "") or "").strip() != variable:
                continue
            rows.append(d)

    tail = rows[-window:]
    out: list[float] = []
    for d in tail:
        v = _safe_float(d.get("stats_mean"))
        if v is not None:
            out.append(float(v))
    return out


def _compute_incoherence(
    latest: dict[str, Any],
    cfg: IncoherenceConfig,
    history_csv: Path | None,
) -> dict[str, Any]:
    stats = latest.get("stats") if isinstance(latest.get("stats"), dict) else {}
    meteo = latest.get("meteo") if isinstance(latest.get("meteo"), dict) else {}

    # phi_gap: duration of gaps in hours (prefer missing_time_s, fallback to gap_total_s)
    missing_time_s = (
        _safe_float(stats.get("missing_time_s")) if isinstance(stats, dict) else None
    )
    gap_total_s = (
        _safe_float(stats.get("gap_total_s")) if isinstance(stats, dict) else None
    )
    phi_gap_hours = (
        float((missing_time_s if missing_time_s is not None else gap_total_s) or 0.0)
        / 3600.0
    )

    # phi_smoke: if the variable looks like air quality, compare mean to threshold
    variable = _safe_str(latest.get("variable")) or ""
    mean = _safe_float(stats.get("mean")) if isinstance(stats, dict) else None
    phi_smoke = 0.0
    if mean is not None:
        var_l = variable.lower()
        if any(k in var_l for k in ("pm25", "pm10", "aqi", "smoke", "air")):
            over = float(mean) - float(cfg.smoke_threshold)
            if over > 0.0:
                phi_smoke = min(1.0, over / max(1e-9, float(cfg.smoke_threshold)))

    # phi_stuck: max-min <= eps, enough points
    n_points = _safe_int(stats.get("n_points")) if isinstance(stats, dict) else None
    vmin = _safe_float(stats.get("min")) if isinstance(stats, dict) else None
    vmax = _safe_float(stats.get("max")) if isinstance(stats, dict) else None
    phi_stuck = 0.0
    if (n_points or 0) >= 5 and vmin is not None and vmax is not None:
        if abs(float(vmax) - float(vmin)) <= float(cfg.stuck_eps):
            phi_stuck = 1.0

    # phi_out_of_range: flags include "out_of_range"
    flags = meteo.get("flags") if isinstance(meteo, dict) else []
    phi_out_of_range = 0.0
    if isinstance(flags, list):
        if any(isinstance(x, str) and x.lower() == "out_of_range" for x in flags):
            phi_out_of_range = 1.0

    # phi_score: reuse score (already 0..1-ish by contract)
    phi_score = _safe_float(latest.get("score")) or 0.0

    # phi_drift: z-shift of stats.mean vs recent history means (optional)
    phi_drift = 0.0
    if history_csv is not None and mean is not None:
        station_id = _safe_str(latest.get("station_id")) or ""
        recent = _history_recent_means(
            history_csv,
            station_id=station_id,
            variable=variable,
            window=cfg.drift_window,
        )
        if len(recent) >= 5:
            mu = float(sum(recent) / len(recent))
            var = float(sum((x - mu) ** 2 for x in recent) / len(recent))
            sigma = float(var**0.5)
            if sigma > 1e-12:
                z = abs((float(mean) - mu) / sigma)
                phi_drift = min(1.0, z / 5.0)  # z>=5 saturates

    phis: dict[str, float] = {
        "gap_hours": max(0.0, float(phi_gap_hours)),
        "smoke": max(0.0, float(phi_smoke)),
        "stuck": max(0.0, float(phi_stuck)),
        "drift": max(0.0, float(phi_drift)),
        "out_of_range": max(0.0, float(phi_out_of_range)),
        "score": max(0.0, float(phi_score)),
    }

    total = 0.0
    breakdown: dict[str, float] = {}
    for k, phi in phis.items():
        w = float(cfg.weights.get(k, 0.0))
        c = w * float(phi)
        breakdown[k] = round(c, 6)
        total += c

    return {
        "total": round(total, 6),
        "phis": {k: round(float(v), 6) for k, v in phis.items()},
        "weights": {k: round(float(v), 6) for k, v in cfg.weights.items()},
        "breakdown": breakdown,
    }


def _append_history(out_dir: Path, enriched: dict[str, Any]) -> None:
    history_csv = out_dir / "history.csv"
    history_jsonl = out_dir / "history.jsonl"

    station_id = _safe_str(enriched.get("station_id")) or ""
    variable = _safe_str(enriched.get("variable")) or ""
    state = _safe_str(enriched.get("state")) or ""
    score = _safe_float(enriched.get("score"))

    ts = _safe_float(enriched.get("ts"))
    ts_ingest = _safe_float(enriched.get("ts_ingest"))

    ts_iso = _safe_str(enriched.get("ts_iso")) or (
        _iso_from_epoch(ts) if ts is not None else ""
    )
    ts_ingest_iso = _safe_str(enriched.get("ts_ingest_iso")) or (
        _iso_from_epoch(ts_ingest) if ts_ingest is not None else ""
    )

    meteo = enriched.get("meteo") if isinstance(enriched.get("meteo"), dict) else {}
    severity = _safe_str(meteo.get("severity")) if isinstance(meteo, dict) else None
    severity_s = severity or ""

    stats = enriched.get("stats") if isinstance(enriched.get("stats"), dict) else {}
    gap_count = _safe_int(stats.get("gap_count")) if isinstance(stats, dict) else None
    missing_time_frac = (
        _safe_float(stats.get("missing_time_frac")) if isinstance(stats, dict) else None
    )
    stats_mean = _safe_float(stats.get("mean")) if isinstance(stats, dict) else None

    inco_total = _safe_float(enriched.get("incoherence_score"))
    row: dict[str, Any] = {
        "ts_ingest_iso": ts_ingest_iso,
        "ts_iso": ts_iso,
        "ts_ingest": ts_ingest,
        "ts": ts,
        "station_id": station_id,
        "variable": variable,
        "score": score,
        "state": state,
        "severity": severity_s,
        "gap_count": gap_count,
        "missing_time_frac": missing_time_frac,
        "incoherence_score": inco_total,
        "stats_mean": stats_mean,
    }

    fieldnames = list(row.keys())
    exists = history_csv.exists()
    with history_csv.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            w.writeheader()
        w.writerow({k: "" if v is None else v for k, v in row.items()})

    with history_jsonl.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")


def _make_bulletin(enriched: dict[str, Any]) -> dict[str, Any]:
    stats = enriched.get("stats") if isinstance(enriched.get("stats"), dict) else {}
    meteo = enriched.get("meteo") if isinstance(enriched.get("meteo"), dict) else {}
    inco = (
        enriched.get("incoherence")
        if isinstance(enriched.get("incoherence"), dict)
        else {}
    )

    return {
        "generated_at": _iso_from_epoch(_epoch(_now_utc())),
        "station_id": _safe_str(enriched.get("station_id")) or "",
        "variable": _safe_str(enriched.get("variable")) or "",
        "state": _safe_str(enriched.get("state")) or "",
        "score": _safe_float(enriched.get("score")),
        "severity": _safe_str(meteo.get("severity")) if isinstance(meteo, dict) else "",
        "flags": meteo.get("flags", []) if isinstance(meteo, dict) else [],
        "interpretation": (
            _safe_str(meteo.get("interpretation")) if isinstance(meteo, dict) else ""
        ),
        "stats": stats,
        "incoherence": inco,
    }


def _write_bulletin_md(path: Path, bulletin: dict[str, Any]) -> None:
    def s(k: str, default: str = "") -> str:
        v = bulletin.get(k, default)
        return str(v) if v is not None else default

    lines: list[str] = []
    lines.append("# MeteoVoid bulletin")
    lines.append("")
    lines.append(f"Generated at: {s('generated_at')}")
    lines.append("")
    lines.append("## Latest status")
    lines.append(f"Station: {s('station_id')}")
    lines.append(f"Variable: {s('variable')}")
    lines.append(f"State: {s('state')}")
    lines.append(f"Score: {s('score')}")
    lines.append(f"Severity: {s('severity')}")
    flags = bulletin.get("flags", [])
    lines.append(f"Flags: {', '.join(flags or [])}")
    lines.append("")
    lines.append("## Interpretation")
    lines.append(s("interpretation"))
    lines.append("")
    lines.append("## Incoherence")
    inco = bulletin.get("incoherence", {})
    if isinstance(inco, dict):
        lines.append(f"Total: {inco.get('total', '')}")
        breakdown = inco.get("breakdown", {})
        if isinstance(breakdown, dict) and breakdown:
            lines.append("Breakdown:")
            for k in sorted(breakdown.keys()):
                lines.append(f"- {k}: {breakdown.get(k)}")
    lines.append("")
    lines.append("## Stats")
    st = bulletin.get("stats", {})
    if isinstance(st, dict) and st:
        for k in sorted(st.keys()):
            lines.append(f"- {k}: {st.get(k)}")
    lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _enrich_latest(latest: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(latest)

    ts = _safe_float(enriched.get("ts"))
    if ts is None:
        ts = _epoch(_now_utc())
        enriched["ts"] = float(ts)
    enriched["ts_iso"] = _iso_from_epoch(float(ts))

    ts_ingest = _safe_float(enriched.get("ts_ingest"))
    if ts_ingest is None:
        ts_ingest = _epoch(_now_utc())
        enriched["ts_ingest"] = float(ts_ingest)
    enriched["ts_ingest_iso"] = _iso_from_epoch(float(ts_ingest))

    return enriched


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--latest", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--config", required=False, default="")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    latest = _load_json(Path(args.latest))
    enriched = _enrich_latest(latest)

    cfg = _load_incoherence_config(args.config if args.config else None)
    history_csv = (
        (out_dir / "history.csv") if (out_dir / "history.csv").exists() else None
    )
    inco = _compute_incoherence(enriched, cfg, history_csv=history_csv)

    enriched["incoherence"] = inco
    enriched["incoherence_score"] = inco.get("total")
    enriched["incoherence_contributions"] = inco.get("breakdown")

    _write_json(out_dir / "latest_enriched.json", enriched)
    _append_history(out_dir, enriched)

    bulletin = _make_bulletin(enriched)
    _write_json(out_dir / "bulletin.json", bulletin)
    _write_bulletin_md(out_dir / "bulletin.md", bulletin)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
