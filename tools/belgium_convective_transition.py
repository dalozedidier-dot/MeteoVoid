from __future__ import annotations

import csv
import html
import json
import math
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

TRANSITION_OUTPUTS = {
    "convective_transition_json": "convective_transition_report.json",
    "convective_transition_csv": "convective_transition_by_station.csv",
    "convective_transition_markdown": "convective_transition_report.md",
    "convective_transition_html": "convective_transition_dashboard.html",
}


def _json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        value_f = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(value_f) or math.isinf(value_f):
        return default
    return value_f


def _clamp01(value: float | None) -> float:
    if value is None:
        return 0.0
    return max(0.0, min(1.0, float(value)))


def _round(value: float | None, digits: int = 6) -> float:
    return round(_clamp01(value), digits)


def _component(station: dict[str, Any], name: str) -> float:
    components = station.get("components")
    if not isinstance(components, dict):
        return 0.0
    return _clamp01(_safe_float(components.get(name), 0.0))


def _stations(report: dict[str, Any]) -> list[dict[str, Any]]:
    raw = report.get("stations")
    if not isinstance(raw, list):
        return []
    stations: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        if item.get("source_ok") is False and (_safe_float(item.get("score"), 0.0) or 0.0) <= 0.0:
            continue
        stations.append(item)
    return stations


def _dewpoint_signal(station: dict[str, Any]) -> float:
    dew = _safe_float(station.get("max_dew_point_c"), 0.0) or 0.0
    if dew >= 23.0:
        return 1.0
    if dew >= 21.0:
        return 0.85
    if dew >= 19.0:
        return 0.68
    if dew >= 17.0:
        return 0.45
    if dew >= 15.0:
        return 0.25
    return 0.0


def _temperature_signal(station: dict[str, Any]) -> float:
    temp = _safe_float(station.get("max_temperature_c"), 0.0) or 0.0
    if temp >= 34.0:
        return 1.0
    if temp >= 32.0:
        return 0.82
    if temp >= 30.0:
        return 0.65
    if temp >= 27.0:
        return 0.40
    return 0.0


def _emergence_from_external(report: dict[str, Any]) -> float:
    external = report.get("external_confirmation")
    if not isinstance(external, dict):
        external = {}
    score = _safe_float(external.get("score"), 0.0) or 0.0
    operational = report.get("operational_state")
    if isinstance(operational, dict):
        score = max(
            score, (_safe_float(operational.get("external_confirmation_score"), 0.0) or 0.0)
        )
    integrations = report.get("integrations")
    if isinstance(integrations, dict):
        if integrations.get("radar_integrated"):
            score = max(score, 0.65)
        if integrations.get("lightning_integrated"):
            score = max(score, 0.72)
        if integrations.get("official_warning_integrated"):
            score = max(score, 0.45)
    return _clamp01(score)


def _alignment(values: list[float]) -> float:
    usable = [_clamp01(v) for v in values]
    if not usable:
        return 0.0
    if len(usable) == 1:
        return usable[0]
    avg = mean(usable)
    spread = min(pstdev(usable), 0.5) / 0.5
    return _clamp01(avg * (1.0 - 0.35 * spread))


def _level(score: float) -> str:
    if score >= 0.82:
        return "void_collapse"
    if score >= 0.68:
        return "transition_probable"
    if score >= 0.52:
        return "latent_unstable"
    if score >= 0.36:
        return "watch"
    return "stable"


def _station_transition_indices(
    station: dict[str, Any], external_emergence: float
) -> dict[str, Any]:
    model_score = _clamp01(_safe_float(station.get("score"), 0.0))
    heat = max(_component(station, "heat"), _temperature_signal(station))
    moisture = max(_component(station, "moisture"), _dewpoint_signal(station))
    precipitation = _component(station, "precipitation")
    pressure_drop = _component(station, "pressure_drop")
    weather_code = _component(station, "weather_code")
    wind_gust = _component(station, "wind_gust")

    convective_load = _clamp01(
        0.30 * heat + 0.42 * moisture + 0.16 * model_score + 0.12 * precipitation
    )
    trigger_readiness = _clamp01(
        0.34 * precipitation + 0.28 * pressure_drop + 0.26 * weather_code + 0.12 * wind_gust
    )
    organization_potential = _clamp01(
        0.42 * wind_gust + 0.24 * weather_code + 0.20 * precipitation + 0.14 * model_score
    )
    lid_fragility = _clamp01(
        0.36 * convective_load + 0.28 * pressure_drop + 0.22 * weather_code + 0.14 * precipitation
    )
    observed_emergence = _clamp01(
        0.48 * weather_code + 0.25 * precipitation + 0.17 * external_emergence + 0.10 * wind_gust
    )
    latent_risk_gap = _clamp01(
        (convective_load + organization_potential) / 2.0 - observed_emergence
    )
    coherence_index = _alignment(
        [convective_load, trigger_readiness, organization_potential, lid_fragility]
    )
    transition_pressure = _clamp01(
        0.33 * convective_load
        + 0.24 * trigger_readiness
        + 0.22 * organization_potential
        + 0.21 * lid_fragility
    )
    void_collapse_signal = _clamp01(
        0.30 * coherence_index
        + 0.24 * transition_pressure
        + 0.18 * observed_emergence
        + 0.18 * model_score
        + 0.10 * max(0.0, 1.0 - latent_risk_gap)
    )

    return {
        "station_id": station.get("station_id"),
        "name": station.get("name"),
        "region": station.get("region"),
        "lat": station.get("lat"),
        "lon": station.get("lon"),
        "worst_time": station.get("worst_time"),
        "model_score": round(model_score, 6),
        "model_severity": station.get("severity", "normal"),
        "convective_load_index": _round(convective_load),
        "trigger_readiness_index": _round(trigger_readiness),
        "storm_organization_potential": _round(organization_potential),
        "lid_fragility_index": _round(lid_fragility),
        "observed_emergence_index": _round(observed_emergence),
        "latent_risk_gap": _round(latent_risk_gap),
        "convective_coherence_index": _round(coherence_index),
        "transition_pressure_index": _round(transition_pressure),
        "void_collapse_signal": _round(void_collapse_signal),
        "transition_level": _level(void_collapse_signal),
        "signals": station.get("signals", []),
    }


def _aggregate_station_indices(station_indices: list[dict[str, Any]]) -> dict[str, Any]:
    fields = [
        "convective_load_index",
        "trigger_readiness_index",
        "storm_organization_potential",
        "lid_fragility_index",
        "observed_emergence_index",
        "latent_risk_gap",
        "convective_coherence_index",
        "transition_pressure_index",
        "void_collapse_signal",
    ]
    summary: dict[str, Any] = {}
    for field in fields:
        values = [_safe_float(item.get(field), 0.0) or 0.0 for item in station_indices]
        summary[field] = {
            "mean": round(mean(values), 6) if values else 0.0,
            "max": round(max(values), 6) if values else 0.0,
        }
    top = sorted(
        station_indices,
        key=lambda item: _safe_float(item.get("void_collapse_signal"), 0.0) or 0.0,
        reverse=True,
    )[:8]
    national_signal = _clamp01(
        0.50 * summary["void_collapse_signal"]["mean"]
        + 0.30 * summary["void_collapse_signal"]["max"]
        + 0.20 * summary["convective_coherence_index"]["mean"]
    )
    return {
        "national_void_collapse_signal": round(national_signal, 6),
        "national_transition_level": _level(national_signal),
        "indices": summary,
        "top_transition_stations": top,
    }


def _interpretation(level: str) -> str:
    if level == "void_collapse":
        return (
            "Signal de bascule très élevé : les composantes énergie, déclenchement, organisation "
            "et émergence convergent vers un régime convectif potentiellement dangereux."
        )
    if level == "transition_probable":
        return (
            "Transition convective probable : plusieurs couches deviennent cohérentes, mais la "
            "confirmation radar/foudre ou officielle reste déterminante."
        )
    if level == "latent_unstable":
        return (
            "Risque latent instable : l'environnement se charge, mais l'actualisation dépend encore "
            "du déclenchement et de l'érosion du couvercle."
        )
    if level == "watch":
        return "Veille simple : certains signaux existent, sans alignement convectif robuste."
    return "Régime stable ou faiblement organisé dans les paramètres disponibles."


def build_convective_transition_report(report: dict[str, Any]) -> dict[str, Any]:
    external_emergence = _emergence_from_external(report)
    station_indices = [
        _station_transition_indices(station, external_emergence) for station in _stations(report)
    ]
    aggregate = _aggregate_station_indices(station_indices)
    level = str(aggregate.get("national_transition_level", "stable"))
    return {
        "generated_at": report.get("generated_at"),
        "run_id": report.get("run_id"),
        "target_window": report.get("target_window"),
        "mode": "convective_transition_engine",
        "source": report.get("source"),
        "source_type": report.get("source_type"),
        "external_emergence_proxy": round(external_emergence, 6),
        "national": aggregate,
        "interpretation": _interpretation(level),
        "station_indices": station_indices,
        "limits": [
            "Ce moteur mesure une cohérence convective dérivée des variables actuellement disponibles.",
            "CAPE, CIN, cisaillement vertical, SRH et données satellite/foudre natives restent à intégrer quand une source fiable est disponible.",
            "Le signal ne constitue pas une alerte officielle et doit rester comparé à l'IRM/KMI, MeteoAlarm, ESTOFEX, radar et foudre.",
        ],
        "next_native_inputs": [
            "CAPE",
            "CIN",
            "cisaillement 0-6 km",
            "SRH 0-1 km / 0-3 km",
            "LCL / LFC",
            "theta-e",
            "PWAT",
            "refroidissement IR satellite",
            "lightning rate",
            "radar growth / rotation / grêle",
        ],
    }


def _write_transition_csv(transition: dict[str, Any], path: Path) -> None:
    rows = transition.get("station_indices")
    if not isinstance(rows, list):
        rows = []
    fieldnames = [
        "station_id",
        "name",
        "region",
        "worst_time",
        "model_score",
        "model_severity",
        "convective_load_index",
        "trigger_readiness_index",
        "storm_organization_potential",
        "lid_fragility_index",
        "observed_emergence_index",
        "latent_risk_gap",
        "convective_coherence_index",
        "transition_pressure_index",
        "void_collapse_signal",
        "transition_level",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name) for name in fieldnames})


def _render_markdown(transition: dict[str, Any]) -> str:
    national = transition.get("national") if isinstance(transition.get("national"), dict) else {}
    top = national.get("top_transition_stations") if isinstance(national, dict) else []
    if not isinstance(top, list):
        top = []
    lines = [
        "# MeteoVoid · Convective Transition Engine",
        "",
        f"- Run : `{transition.get('run_id')}`",
        f"- Signal national : `{national.get('national_void_collapse_signal', 0)}`",
        f"- Niveau : `{national.get('national_transition_level', 'stable')}`",
        f"- Émergence externe proxy : `{transition.get('external_emergence_proxy', 0)}`",
        "",
        "## Lecture",
        "",
        str(transition.get("interpretation") or ""),
        "",
        "## Stations les plus sensibles",
        "",
        "| Station | Région | Signal void | Charge | Déclencheur | Organisation | Niveau |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in top[:8]:
        if not isinstance(row, dict):
            continue
        lines.append(
            "| {name} | {region} | {void} | {load} | {trigger} | {org} | {level} |".format(
                name=row.get("name") or row.get("station_id"),
                region=row.get("region") or "",
                void=row.get("void_collapse_signal"),
                load=row.get("convective_load_index"),
                trigger=row.get("trigger_readiness_index"),
                org=row.get("storm_organization_potential"),
                level=row.get("transition_level"),
            )
        )
    lines.extend(
        [
            "",
            "## Limites",
            "",
        ]
    )
    for item in transition.get("limits", []):
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def _badge_color(level: str) -> str:
    return {
        "stable": "#5da867",
        "watch": "#c8b847",
        "latent_unstable": "#e89432",
        "transition_probable": "#d9534f",
        "void_collapse": "#6f42c1",
    }.get(level, "#697386")


def _card(title: str, value: Any, subtitle: str, level: str = "stable") -> str:
    color = _badge_color(level)
    return f"""
    <section class="card">
      <div class="label">{html.escape(title)}</div>
      <div class="value" style="color:{color}">{html.escape(str(value))}</div>
      <div class="small">{html.escape(subtitle)}</div>
    </section>
    """


def _render_html(transition: dict[str, Any]) -> str:
    national = transition.get("national") if isinstance(transition.get("national"), dict) else {}
    indices = national.get("indices") if isinstance(national.get("indices"), dict) else {}
    level = str(national.get("national_transition_level") or "stable")
    top = (
        national.get("top_transition_stations")
        if isinstance(national.get("top_transition_stations"), list)
        else []
    )

    def mean_value(name: str) -> Any:
        item = indices.get(name) if isinstance(indices, dict) else {}
        if isinstance(item, dict):
            return item.get("mean", 0)
        return 0

    rows = []
    for item in top[:10]:
        if not isinstance(item, dict):
            continue
        item_level = str(item.get("transition_level") or "stable")
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(item.get('name') or item.get('station_id') or ''))}</td>"
            f"<td>{html.escape(str(item.get('region') or ''))}</td>"
            f"<td>{item.get('void_collapse_signal')}</td>"
            f"<td>{item.get('convective_load_index')}</td>"
            f"<td>{item.get('trigger_readiness_index')}</td>"
            f"<td>{item.get('storm_organization_potential')}</td>"
            f"<td><span class='badge' style='background:{_badge_color(item_level)}'>{html.escape(item_level)}</span></td>"
            "</tr>"
        )
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>MeteoVoid · Convective Transition Engine</title>
<style>
:root {{ --bg:#f4f7fb; --ink:#142033; --muted:#697386; --card:#fff; --line:#dbe3ef; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:Inter,Segoe UI,Arial,sans-serif; background:var(--bg); color:var(--ink); }}
header {{ padding:26px 32px; background:linear-gradient(135deg,#0b1728,#234f7d); color:white; }}
h1 {{ margin:0; font-size:26px; }}
header p {{ margin:8px 0 0; color:#d8e6f7; max-width:1080px; }}
main {{ padding:22px; max-width:1280px; margin:auto; }}
.grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:18px; padding:16px; box-shadow:0 10px 28px rgba(15,31,53,.07); }}
.label {{ font-size:12px; color:var(--muted); text-transform:uppercase; letter-spacing:.08em; }}
.value {{ font-size:30px; font-weight:760; margin:8px 0; }}
.small {{ color:var(--muted); font-size:13px; line-height:1.45; }}
.panel {{ background:var(--card); border:1px solid var(--line); border-radius:18px; padding:18px; margin-top:16px; box-shadow:0 10px 28px rgba(15,31,53,.07); }}
table {{ width:100%; border-collapse:collapse; }}
th,td {{ padding:10px 8px; border-bottom:1px solid #edf1f7; text-align:left; font-size:14px; }}
th {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.06em; }}
.badge {{ color:white; border-radius:999px; padding:4px 8px; font-size:12px; }}
.note {{ color:var(--muted); line-height:1.55; }}
@media (max-width:900px) {{ .grid {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<header>
<h1>MeteoVoid · Convective Transition Engine</h1>
<p>Lecture systémique de la transition convective : charge, déclenchement, organisation, couvercle, émergence observée et signal de fermeture du “void”.</p>
</header>
<main>
<div class="grid">
{_card("Signal void national", national.get("national_void_collapse_signal", 0), "Mesure synthétique de la bascule potentielle.", level)}
{_card("Niveau transition", national.get("national_transition_level", "stable"), "Classe MeteoVoid non officielle.", level)}
{_card("Émergence externe", transition.get("external_emergence_proxy", 0), "Proxy issu des confirmations externes disponibles.", level)}
{_card("Charge convective", mean_value("convective_load_index"), "Énergie, chaleur et humidité.", level)}
{_card("Déclenchement", mean_value("trigger_readiness_index"), "Forçage proxy : précipitations, pression, codes météo.", level)}
{_card("Organisation", mean_value("storm_organization_potential"), "Potentiel d’organisation via vent, précipitations et signal modèle.", level)}
</div>
<section class="panel"><h2>Lecture opérationnelle</h2><p class="note">{html.escape(str(transition.get("interpretation") or ""))}</p></section>
<section class="panel"><h2>Stations les plus sensibles</h2><table><thead><tr><th>Station</th><th>Région</th><th>Void</th><th>Charge</th><th>Déclencheur</th><th>Organisation</th><th>Niveau</th></tr></thead><tbody>{"".join(rows)}</tbody></table></section>
<section class="panel"><h2>Limites</h2><p class="note">Ce module ne remplace pas les alertes officielles. Il pose une couche expérimentale d’analyse de cohérence convective au-dessus des prévisions et observations disponibles.</p></section>
</main>
</body>
</html>
"""


def write_convective_transition_outputs(report: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    transition = build_convective_transition_report(report)
    (out_dir / TRANSITION_OUTPUTS["convective_transition_json"]).write_text(
        _json_dumps(transition), encoding="utf-8"
    )
    (out_dir / TRANSITION_OUTPUTS["convective_transition_markdown"]).write_text(
        _render_markdown(transition), encoding="utf-8"
    )
    (out_dir / TRANSITION_OUTPUTS["convective_transition_html"]).write_text(
        _render_html(transition), encoding="utf-8"
    )
    _write_transition_csv(transition, out_dir / TRANSITION_OUTPUTS["convective_transition_csv"])
    return transition
