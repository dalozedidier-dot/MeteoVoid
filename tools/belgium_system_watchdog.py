from __future__ import annotations

import html
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

WATCHDOG_OUTPUTS = {
    "self_watchdog_json": "self_watchdog.json",
    "self_watchdog_html": "self_watchdog.html",
    "observation_gap_status_json": "observation_gap_status.json",
}


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _age_minutes(value: Any) -> float | None:
    dt = _parse_dt(value)
    if dt is None:
        return None
    return max(0.0, (datetime.now(UTC) - dt.astimezone(UTC)).total_seconds() / 60.0)


def _source_health(report: dict[str, Any]) -> dict[str, Any]:
    stations = [s for s in report.get("stations", []) if isinstance(s, dict)]
    ok = sum(1 for station in stations if station.get("source_ok"))
    errors = len(stations) - ok
    error_ratio = errors / max(1, len(stations))
    if error_ratio == 0:
        state = "healthy"
    elif error_ratio <= 0.2:
        state = "degraded"
    else:
        state = "fragile"
    return {
        "station_count": len(stations),
        "source_ok_count": ok,
        "source_error_count": errors,
        "source_error_ratio": round(error_ratio, 6),
        "state": state,
    }


def _observation_gap_status(report: dict[str, Any]) -> dict[str, Any]:
    integrations = (
        report.get("integrations") if isinstance(report.get("integrations"), dict) else {}
    )
    external = (
        report.get("external_confirmation")
        if isinstance(report.get("external_confirmation"), dict)
        else {}
    )
    return {
        "generated_at": report.get("generated_at"),
        "satellite": {
            "source": "EUMETSAT/MTG/RDT",
            "status": "connector_prepared_not_configured",
            "configured": False,
        },
        "gnss_water_vapour": {
            "source": "E-GVAP/GNSS",
            "status": "connector_prepared_not_configured",
            "configured": False,
        },
        "pressure_crowd": {
            "source": "Netatmo or compatible pressure network",
            "status": "connector_prepared_not_configured",
            "configured": False,
        },
        "lightning": {
            "source": "community or licensed lightning feed",
            "status": (
                "configured"
                if integrations.get("lightning_integrated")
                or external.get("lightning_confirmation") not in {None, "none"}
                else "connector_prepared_not_configured"
            ),
            "configured": bool(integrations.get("lightning_integrated")),
        },
        "radar": {
            "source": "RainViewer/nowcast or configured radar feed",
            "status": (
                "configured_or_visual_layer"
                if integrations.get("radar_integrated")
                else "visual_layer_only"
            ),
            "configured": bool(integrations.get("radar_integrated")),
        },
        "note": "Ces modalités élargissent la perception au-delà des stations. Elles sont suivies comme état de préparation afin de ne pas casser la CI quand les accès ne sont pas configurés.",
    }


def build_watchdog(report: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    source = _source_health(report)
    generated_age = _age_minutes(report.get("generated_at"))
    required_outputs = [
        "belgium_alert_report.json",
        "risk_by_station.csv",
        "risk_timeseries.json",
        "convective_transition_report.json",
        "upstream_graph_summary.json",
        "manifest.json",
    ]
    missing = [name for name in required_outputs if not (out_dir / name).exists()]
    stale_score = 0.0 if generated_age is None else min(1.0, generated_age / (6 * 60.0))
    missing_score = len(missing) / max(1, len(required_outputs))
    source_score = float(source.get("source_error_ratio") or 0.0)
    coherence_loss_score = min(1.0, 0.45 * source_score + 0.35 * missing_score + 0.20 * stale_score)
    if coherence_loss_score >= 0.5:
        state = "degraded_run"
    elif coherence_loss_score >= 0.2:
        state = "watch_run"
    else:
        state = "healthy_run"
    return {
        "generated_at": report.get("generated_at"),
        "run_id": report.get("run_id"),
        "state": state,
        "coherence_loss_score": round(coherence_loss_score, 6),
        "generated_age_minutes": generated_age,
        "source_health": source,
        "missing_required_outputs": missing,
        "degradation_policy": "never fail silently; report missing sources and lower confidence instead of crashing",
    }


def _render_html(data: dict[str, Any]) -> str:
    source = data.get("source_health", {}) if isinstance(data.get("source_health"), dict) else {}
    missing = (
        data.get("missing_required_outputs", [])
        if isinstance(data.get("missing_required_outputs"), list)
        else []
    )
    missing_html = (
        "".join(f"<li>{html.escape(str(item))}</li>" for item in missing)
        or "<li>Aucune sortie obligatoire manquante.</li>"
    )
    return f"""<!doctype html><html lang='fr'><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width, initial-scale=1'/><title>MeteoVoid · Auto-surveillance</title><style>
body{{margin:0;font-family:Inter,Segoe UI,Arial,sans-serif;background:#eef3f8;color:#0d1b2e}}header{{background:#173b66;color:#fff;padding:22px 26px}}.wrap{{padding:22px;max-width:1100px;margin:auto}}.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}.card{{background:white;border:1px solid #d9e3ef;border-radius:18px;padding:18px;box-shadow:0 14px 32px rgba(20,42,69,.08)}}.big{{font-size:30px;font-weight:900;display:block;margin-top:8px}}small{{color:#66758a;text-transform:uppercase;font-weight:800;letter-spacing:.08em}}@media(max-width:900px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><header><h1>MeteoVoid Belgique · Auto-surveillance</h1><p>Le système observe sa propre cohérence : sources, fraîcheur, sorties et dégradation.</p></header><div class='wrap'><div class='grid'>
<div class='card'><small>État</small><span class='big'>{html.escape(str(data.get("state")))}</span></div>
<div class='card'><small>Perte de cohérence</small><span class='big'>{float(data.get("coherence_loss_score") or 0):.3f}</span></div>
<div class='card'><small>Sources OK/erreurs</small><span class='big'>{source.get("source_ok_count", 0)}/{source.get("source_error_count", 0)}</span></div>
</div><div class='card' style='margin-top:18px'><h2>Sorties manquantes</h2><ul>{missing_html}</ul></div></div></body></html>"""


def write_watchdog_outputs(report: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    data = build_watchdog(report, out_dir)
    observations = _observation_gap_status(report)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "self_watchdog.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    (out_dir / "observation_gap_status.json").write_text(
        json.dumps(observations, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    (out_dir / "self_watchdog.html").write_text(_render_html(data), encoding="utf-8")
    return data
