from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Make "src/" importable when running from repo root (CI uses python tools/... without install).
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src") if (_ROOT / "src").exists() else str(_ROOT))

from meteovoid.incoherence import (  # noqa: E402
    compute_incoherence_from_latest,
    load_incoherence_config,
)


def _now_iso() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_str(x: Any) -> str:
    return x if isinstance(x, str) else ""


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


def _append_history(latest: dict[str, Any], out_dir: Path) -> None:
    stats_any = latest.get("stats")
    stats: dict[str, Any] = stats_any if isinstance(stats_any, dict) else {}

    meteo_any = latest.get("meteo")
    meteo: dict[str, Any] = meteo_any if isinstance(meteo_any, dict) else {}

    inco_any = latest.get("incoherence")
    inco: dict[str, Any] = inco_any if isinstance(inco_any, dict) else {}

    comp_any = inco.get("components")
    comp: dict[str, Any] = comp_any if isinstance(comp_any, dict) else {}

    row: dict[str, Any] = {
        "generated_at": _now_iso(),
        "station_id": _safe_str(latest.get("station_id")),
        "variable": _safe_str(latest.get("variable")),
        "stream_id": _safe_str(latest.get("stream_id")),
        "ts": _safe_float(latest.get("ts")),
        "ts_ingest": _safe_float(latest.get("ts_ingest")),
        "score": _safe_float(latest.get("score")),
        "state": _safe_str(latest.get("state")),
        "severity": _safe_str(meteo.get("severity")),
        "incoherence_score": _safe_float(inco.get("score")),
        "incoherence_severity": _safe_str(inco.get("severity")),
        "phi_gap": _safe_float(comp.get("gap")),
        "phi_range": _safe_float(comp.get("range")),
        "phi_stuck": _safe_float(comp.get("stuck")),
        "n_points": _safe_int(stats.get("n_points")),
        "gap_count": _safe_int(stats.get("gap_count")),
        "missing_time_frac": _safe_float(stats.get("missing_time_frac")),
        "min": _safe_float(stats.get("min")),
        "max": _safe_float(stats.get("max")),
        "mean": _safe_float(stats.get("mean")),
        "p95": _safe_float(stats.get("p95")),
    }

    # JSONL append: full enriched object
    jsonl_path = out_dir / "history.jsonl"
    with jsonl_path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(latest, ensure_ascii=False))
        f.write("\n")

    # CSV append: compact schema for quick plotting
    csv_path = out_dir / "history.csv"
    fieldnames = list(row.keys())
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    with csv_path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            w.writeheader()
        w.writerow(row)


def _fmt3(x: Any) -> str:
    v = _safe_float(x)
    return f"{v:.3f}" if v is not None else "n/a"


def _render_bulletin_md(latest: dict[str, Any]) -> str:
    stats_any = latest.get("stats")
    stats: dict[str, Any] = stats_any if isinstance(stats_any, dict) else {}

    meteo_any = latest.get("meteo")
    meteo: dict[str, Any] = meteo_any if isinstance(meteo_any, dict) else {}

    inco_any = latest.get("incoherence")
    inco: dict[str, Any] = inco_any if isinstance(inco_any, dict) else {}

    comp_any = inco.get("components")
    comp: dict[str, Any] = comp_any if isinstance(comp_any, dict) else {}

    lines: list[str] = []
    lines.append("# Bulletin MeteoVoid (Live Smoke)")
    lines.append("")
    lines.append(f"Généré: `{_now_iso()}`")
    lines.append("")
    lines.append("## Résumé")
    lines.append("")
    lines.append(f"- Station: `{_safe_str(latest.get('station_id'))}`")
    lines.append(f"- Variable: `{_safe_str(latest.get('variable'))}`")
    lines.append(f"- État: `{_safe_str(latest.get('state'))}`")
    lines.append(f"- Score variabilité: `{_fmt3(latest.get('score'))}`")
    lines.append(f"- Sévérité: `{_safe_str(meteo.get('severity'))}`")
    lines.append("")
    lines.append("## Incohérence")
    lines.append("")
    lines.append(f"- Score incohérence: `{_fmt3(inco.get('score'))}`")
    lines.append(f"- Sévérité incohérence: `{_safe_str(inco.get('severity'))}`")
    lines.append(
        f"- Composantes: gap={_fmt3(comp.get('gap'))} range={_fmt3(comp.get('range'))} stuck={_fmt3(comp.get('stuck'))}"
    )
    lines.append("")
    lines.append("## Interprétation")
    lines.append("")
    interp = _safe_str(meteo.get("interpretation"))
    lines.append(interp if interp else "Aucune interprétation fournie.")
    flags = meteo.get("flags")
    if isinstance(flags, list) and flags:
        lines.append("")
        lines.append(f"Flags: `{', '.join([str(x) for x in flags])}`")
    lines.append("")
    lines.append("## Stats (fenêtre)")
    lines.append("")
    for k in [
        "n_points",
        "min",
        "max",
        "mean",
        "p95",
        "dt_median_s",
        "gap_count",
        "missing_time_frac",
        "impute_mode",
        "imputed_frac",
    ]:
        if k in stats:
            lines.append(f"- {k}: `{stats[k]}`")

    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate bulletin + history from latest.json.")
    ap.add_argument("--latest", required=True, help="Path to latest.json")
    ap.add_argument("--out-dir", required=True, help="Output dir for bulletin/history files")
    ap.add_argument(
        "--config",
        default="config/incoherence_defaults.json",
        help="JSON config for incoherence computation",
    )
    args = ap.parse_args(argv)

    latest_path = Path(args.latest)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    latest_any = json.loads(latest_path.read_text(encoding="utf-8"))
    if not isinstance(latest_any, dict):
        raise SystemExit("latest.json must be a JSON object")
    latest: dict[str, Any] = latest_any

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        cfg_path = _ROOT / "config" / "incoherence_defaults.json"
    cfg = load_incoherence_config(cfg_path)

    latest["incoherence"] = compute_incoherence_from_latest(latest=latest, cfg=cfg)

    latest_path.write_text(
        json.dumps(latest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    bulletin = {"generated_at": _now_iso(), "latest": latest}
    (out_dir / "bulletin.json").write_text(
        json.dumps(bulletin, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out_dir / "bulletin.md").write_text(_render_bulletin_md(latest), encoding="utf-8")

    _append_history(latest, out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
