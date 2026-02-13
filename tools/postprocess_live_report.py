"""Post-process Live Smoke artifacts to produce a human usable bulletin + history.

Inputs:
- latest.json: a single report from /latest (already validated by tools/validate_latest_report.py)

Outputs (in out-dir):
- latest_enriched.json
- bulletin.json
- bulletin.md
- history.csv (append-only)
- history.jsonl (append-only)

Design goals:
- Keep it lightweight (stdlib only)
- Never crash the workflow because optional fields are missing
- Provide a consistent "bulletin" structure even when schema evolves
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(p: Path) -> dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def _safe_float(x: Any) -> Optional[float]:
    if isinstance(x, (int, float)):
        return float(x)
    try:
        return float(str(x))
    except Exception:
        return None


def _safe_int(x: Any) -> Optional[int]:
    if isinstance(x, int):
        return x
    try:
        return int(str(x))
    except Exception:
        return None


@dataclass(frozen=True)
class IncoherenceConfig:
    weights: dict[str, float]
    smoke_threshold: float
    stuck_eps: float


def _load_incoherence_config(path: Optional[str]) -> IncoherenceConfig:
    # Defaults are conservative and generic.
    default = IncoherenceConfig(
        weights={
            "gap_hours": 0.3,
            "stuck": 0.2,
            "out_of_range": 0.2,
            "score": 0.3,
        },
        smoke_threshold=50.0,
        stuck_eps=1e-9,
    )
    if not path:
        return default

    p = Path(path)
    if not p.exists():
        return default

    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default

    w = d.get("weights")
    weights: dict[str, float] = dict(default.weights)
    if isinstance(w, dict):
        for k, v in w.items():
            if isinstance(k, str) and isinstance(v, (int, float)):
                weights[k] = float(v)

    smoke_threshold = _safe_float(d.get("smoke_threshold")) or default.smoke_threshold
    stuck_eps = _safe_float(d.get("stuck_eps")) or default.stuck_eps
    return IncoherenceConfig(weights=weights, smoke_threshold=smoke_threshold, stuck_eps=stuck_eps)


def _compute_incoherence(latest: dict[str, Any], cfg: IncoherenceConfig) -> dict[str, Any]:
    # phi_gap: based on missing_time_frac or gap_total_s if present
    stats = latest.get("stats") if isinstance(latest.get("stats"), dict) else {}
    missing_frac = _safe_float(stats.get("missing_time_frac")) or 0.0

    # Convert missing fraction to "gap hours" on a 1h window, if window length is unknown we keep it proportional.
    # This stays dimensionless but interpretable: 0.25 means 25% missing.
    phi_gap_hours = missing_frac * 1.0

    # phi_stuck: 1 if sensor seems stuck.
    # We infer stuck from stats min==max and n_points>5
    n_points = _safe_int(stats.get("n_points")) or 0
    vmin = _safe_float(stats.get("min"))
    vmax = _safe_float(stats.get("max"))
    phi_stuck = 0.0
    if n_points >= 5 and vmin is not None and vmax is not None and abs(vmax - vmin) <= cfg.stuck_eps:
        phi_stuck = 1.0

    # phi_out_of_range: if hints exist in meteo flags
    meteo = latest.get("meteo") if isinstance(latest.get("meteo"), dict) else {}
    flags = meteo.get("flags") if isinstance(meteo.get("flags"), list) else []
    phi_out_of_range = 1.0 if any(isinstance(x, str) and x.lower() == "out_of_range" for x in flags) else 0.0

    # phi_score: reuse score as a signal (already normalized 0..1-ish)
    phi_score = _safe_float(latest.get("score")) or 0.0

    phis = {
        "gap_hours": max(0.0, phi_gap_hours),
        "stuck": max(0.0, phi_stuck),
        "out_of_range": max(0.0, phi_out_of_range),
        "score": max(0.0, phi_score),
    }

    weights = cfg.weights
    total = 0.0
    breakdown: dict[str, float] = {}
    for k, phi in phis.items():
        w = float(weights.get(k, 0.0))
        c = w * float(phi)
        breakdown[k] = round(c, 6)
        total += c

    return {
        "total": round(total, 6),
        "phis": {k: round(float(v), 6) for k, v in phis.items()},
        "weights": {k: round(float(v), 6) for k, v in weights.items()},
        "breakdown": breakdown,
    }


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _append_history(out_dir: Path, enriched: dict[str, Any]) -> Path:
    history_csv = out_dir / "history.csv"
    history_jsonl = out_dir / "history.jsonl"

    ts_ingest = enriched.get("ts_ingest")
    if not isinstance(ts_ingest, str) or not ts_ingest:
        ts_ingest = _iso(_now_utc())

    station_id = enriched.get("station_id") if isinstance(enriched.get("station_id"), str) else ""
    variable = enriched.get("variable") if isinstance(enriched.get("variable"), str) else ""
    state = enriched.get("state") if isinstance(enriched.get("state"), str) else ""
    severity = ""
    meteo = enriched.get("meteo") if isinstance(enriched.get("meteo"), dict) else {}
    if isinstance(meteo, dict):
        sev = meteo.get("severity")
        if isinstance(sev, str):
            severity = sev

    inco = enriched.get("incoherence") if isinstance(enriched.get("incoherence"), dict) else {}
    inco_total = _safe_float(inco.get("total")) if isinstance(inco, dict) else None

    stats = enriched.get("stats") if isinstance(enriched.get("stats"), dict) else {}
    gap_count = _safe_int(stats.get("gap_count")) if isinstance(stats, dict) else None
    missing_time_frac = _safe_float(stats.get("missing_time_frac")) if isinstance(stats, dict) else None

    row = {
        "ts_ingest": ts_ingest,
        "station_id": station_id,
        "variable": variable,
        "score": _safe_float(enriched.get("score")),
        "state": state,
        "severity": severity,
        "gap_count": gap_count,
        "missing_time_frac": missing_time_frac,
        "incoherence_total": inco_total,
    }

    # CSV append
    fieldnames = list(row.keys())
    exists = history_csv.exists()
    with history_csv.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            w.writeheader()
        w.writerow({k: "" if v is None else v for k, v in row.items()})

    # JSONL append
    with history_jsonl.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")

    return history_csv


def _make_bulletin(enriched: dict[str, Any]) -> dict[str, Any]:
    stats = enriched.get("stats") if isinstance(enriched.get("stats"), dict) else {}
    meteo = enriched.get("meteo") if isinstance(enriched.get("meteo"), dict) else {}
    inco = enriched.get("incoherence") if isinstance(enriched.get("incoherence"), dict) else {}

    return {
        "generated_at": _iso(_now_utc()),
        "station_id": enriched.get("station_id", ""),
        "variable": enriched.get("variable", ""),
        "state": enriched.get("state", ""),
        "score": enriched.get("score", None),
        "severity": meteo.get("severity", ""),
        "flags": meteo.get("flags", []),
        "interpretation": meteo.get("interpretation", ""),
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
    lines.append(f"Flags: {', '.join(bulletin.get('flags', []) or [])}")
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--latest", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--config", required=False, default="")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    latest = _load_json(Path(args.latest))
    cfg = _load_incoherence_config(args.config if args.config else None)

    enriched = dict(latest)
    enriched["ts_ingest"] = str(enriched.get("ts_ingest") or _iso(_now_utc()))
    enriched["incoherence"] = _compute_incoherence(enriched, cfg)

    _write_json(out_dir / "latest_enriched.json", enriched)

    history_csv = _append_history(out_dir, enriched)

    bulletin = _make_bulletin(enriched)
    _write_json(out_dir / "bulletin.json", bulletin)
    _write_bulletin_md(out_dir / "bulletin.md", bulletin)

    # convenience: keep a stable pointer
    (out_dir / "_history_path.txt").write_text(str(history_csv) + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
