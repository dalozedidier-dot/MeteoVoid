"""Build the public MeteoVoid Belgium GitHub Pages site.

Design goals (interface redesign):

* Three reading levels instead of "12 cards at once":
  1. Vue simple      -> what to remember (level, zone, window, confidence, one sentence)
  2. Vue operationnelle -> why the risk moves (Convective Transition gauge + hourly timeline
                          + automatic alert explanation)
  3. Vue expert      -> raw data, scores, maps, graphs, exports

* A clean static JSON API under ``api/`` so the HTML page *reads JSON* instead of
  being a huge frozen page:
  ``api/latest.json``, ``api/stations.json``, ``api/timeline.json``,
  ``api/transition.json``, ``api/sources.json``, ``api/validation.json`` and an
  ``api/index.json`` manifest.

The Python side only *transforms* the artifacts already produced by
``generate_belgium_alert_report.py`` into a compact view-model. All rendering is
done client side in vanilla JS, so the layout stays easy to evolve.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

# Artifacts copied verbatim into reports/latest/ so the expert view (iframes) and
# the export links keep working. Kept intentionally broad.
PUBLIC_FILES = [
    "belgium_alert_dashboard.html",
    "convective_transition_dashboard.html",
    "upstream_graph.html",
    "early_warning_dashboard.html",
    "information_graph.html",
    "validation_dashboard.html",
    "self_watchdog.html",
    "belgium_alert_cap.xml",
    "meteovoid_api_latest.json",
    "early_warning_signals.json",
    "early_warning_by_station.csv",
    "early_warning_network.csv",
    "information_graph_summary.json",
    "information_graph_edges.csv",
    "validation_metrics.json",
    "validation_report.md",
    "self_watchdog.json",
    "observation_gap_status.json",
    "nowcast_status.json",
    "belgium_alert_map.html",
    "belgium_weather_layers.html",
    "belgium_radar_map.html",
    "belgium_humidity_map.html",
    "belgium_dewpoint_map.html",
    "belgium_storm_formation_map.html",
    "belgium_province_map.html",
    "belgium_alert_heatmap.html",
    "belgium_windy_compare.html",
    "belgium_alert_report.md",
    "convective_transition_report.md",
    "convective_transition_report.json",
    "convective_transition_by_station.csv",
    "convective_parameters.json",
    "upstream_graph_summary.json",
    "upstream_graph_edges.csv",
    "risk_by_station.csv",
    "risk_by_station.geojson",
    "risk_timeline.csv",
    "risk_timeseries.json",
    "weather_layers_grid.csv",
    "province_summary.csv",
    "province_summary.json",
    "belgium_alert_report.json",
    "alert_state.json",
    "source_status.json",
    "official_sources_status.json",
    "manifest.json",
]

# Expert deep-dive frames, grouped "by usage" (point 3 of the redesign).
EXPERT_FRAMES = [
    ("Cartes", "Risque par station", "belgium_alert_map.html"),
    ("Cartes", "Provinces", "belgium_province_map.html"),
    ("Cartes", "Atmosphère lourde", "belgium_humidity_map.html"),
    ("Cartes", "Point de rosée", "belgium_dewpoint_map.html"),
    ("Cartes", "Formation orageuse", "belgium_storm_formation_map.html"),
    ("Cartes", "Radar / observation", "belgium_radar_map.html"),
    ("Cartes", "Couches avancées", "belgium_weather_layers.html"),
    ("Analyse", "Synthèse détaillée", "belgium_alert_dashboard.html"),
    ("Analyse", "Transition convective", "convective_transition_dashboard.html"),
    ("Analyse", "Graphe amont", "upstream_graph.html"),
    ("Analyse", "Graphe informationnel", "information_graph.html"),
    ("Preuve", "Signaux précoces", "early_warning_dashboard.html"),
    ("Preuve", "Validation", "validation_dashboard.html"),
    ("Preuve", "Auto-surveillance", "self_watchdog.html"),
]

EXPORTS = [
    ("Rapport Markdown", "belgium_alert_report.md"),
    ("Rapport transition", "convective_transition_report.md"),
    ("Stations CSV", "risk_by_station.csv"),
    ("Timeline CSV", "risk_timeline.csv"),
    ("Grille météo CSV", "weather_layers_grid.csv"),
    ("Transition par station CSV", "convective_transition_by_station.csv"),
    ("API latest JSON", "../api/latest.json"),
    ("API stations JSON", "../api/stations.json"),
    ("API timeline JSON", "../api/timeline.json"),
    ("API transition JSON", "../api/transition.json"),
    ("API sources JSON", "../api/sources.json"),
    ("API validation JSON", "../api/validation.json"),
    ("CAP XML (test)", "belgium_alert_cap.xml"),
    ("Manifest", "manifest.json"),
]

DISCLAIMER = (
    "Prototype technique non officiel. MeteoVoid ne remplace pas l’IRM/KMI. "
    "Toujours comparer avec les sources officielles, le radar et la foudre."
)

# --- level / severity vocabulary -------------------------------------------------

# class buckets, ordered by intensity. Sober palette: red is reserved for real danger.
_CLASS_RANK = {"calm": 0, "info": 1, "watch": 2, "elevated": 3, "high": 4, "danger": 5}

_KEY_TO_CLASS = {
    # operational levels
    "normal": "calm",
    "low_watch": "info",
    "watch": "watch",
    "watch_reinforced": "elevated",
    "pre_alert_confirmed": "high",
    "alert_confirmed": "danger",
    # station / aggregate severities
    "medium": "watch",
    "high": "elevated",
    "alert": "danger",
    # convective transition levels
    "stable": "calm",
    "latent_unstable": "watch",
    "transition_probable": "elevated",
    "void_collapse": "danger",
}

_KEY_TO_LABEL = {
    "normal": "Normal",
    "low_watch": "Veille faible",
    "watch": "Veille",
    "watch_reinforced": "Veille renforcée",
    "pre_alert_confirmed": "Pré-alerte confirmée",
    "alert_confirmed": "Alerte confirmée",
    "medium": "Modéré",
    "high": "Élevé",
    "alert": "Critique",
    "stable": "Stable",
    "latent_unstable": "Instable latent",
    "transition_probable": "Transition probable",
    "void_collapse": "Bascule (void collapse)",
}


def _meta(key: Any) -> dict[str, Any]:
    key = str(key or "normal").lower()
    cls = _KEY_TO_CLASS.get(key, "calm")
    return {
        "key": key,
        "label": _KEY_TO_LABEL.get(key, key.replace("_", " ").title()),
        "class": cls,
        "rank": _CLASS_RANK.get(cls, 0),
    }


# --- small helpers ---------------------------------------------------------------


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _num(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        out = float(value)
    except (TypeError, ValueError):
        return default
    if out != out or out in (float("inf"), float("-inf")):  # NaN / inf
        return default
    return out


def _clamp01(value: Any) -> float:
    out = _num(value, 0.0) or 0.0
    return max(0.0, min(1.0, out))


def _round(value: Any, digits: int = 3) -> float | None:
    out = _num(value)
    return None if out is None else round(out, digits)


def _hour_label(iso: Any) -> str:
    text = str(iso or "")
    if "T" in text:
        clock = text.split("T", 1)[1][:5]
        if clock:
            return clock.replace(":00", "h").replace(":", "h")
    return text or "—"


# --- view-model building ---------------------------------------------------------


def _confidence(
    operational: dict[str, Any],
    watchdog: dict[str, Any],
    early_warning: dict[str, Any],
    info_graph: dict[str, Any],
) -> dict[str, Any]:
    """Transparent composite confidence for the run/signal in [0, 1]."""
    source_health = _clamp01(operational.get("source_health_score"))
    coherence = 1.0 - _clamp01(watchdog.get("coherence_loss_score"))
    external = _clamp01(operational.get("external_confirmation_score"))
    ews = early_warning.get("summary") if isinstance(early_warning.get("summary"), dict) else {}
    info = info_graph.get("summary") if isinstance(info_graph.get("summary"), dict) else {}
    spatial = max(
        _clamp01(info.get("information_corridor_score")),
        _clamp01(ews.get("network_early_warning_score")),
    )
    score = 0.35 * source_health + 0.25 * coherence + 0.25 * external + 0.15 * spatial
    score = round(_clamp01(score), 3)
    if score >= 0.7:
        label, cls = "élevée", "calm"
    elif score >= 0.45:
        label, cls = "modérée", "watch"
    else:
        label, cls = "faible", "elevated"
    return {
        "score": score,
        "label": label,
        "class": cls,
        "factors": [
            {"name": "Qualité des sources", "value": round(source_health, 2)},
            {"name": "Cohérence interne", "value": round(coherence, 2)},
            {"name": "Confirmation externe", "value": round(external, 2)},
            {"name": "Cohérence spatiale", "value": round(spatial, 2)},
        ],
    }


def _critical_window(report: dict[str, Any]) -> dict[str, Any]:
    summary = report.get("timeline_summary")
    summary = summary if isinstance(summary, dict) else {}
    status = str(summary.get("status") or "unavailable")
    if status != "available":
        return {"status": status, "label": "fenêtre non déterminée"}
    start = summary.get("first_high_time")
    end = summary.get("last_high_time")
    peak = summary.get("peak_time")
    start_h, end_h, peak_h = _hour_label(start), _hour_label(end), _hour_label(peak)
    label = f"{start_h} → {end_h}" if start_h != end_h else f"vers {peak_h}"
    return {
        "status": status,
        "start": start,
        "end": end,
        "peak": peak,
        "start_hour": start_h,
        "end_hour": end_h,
        "peak_hour": peak_h,
        "label": label,
        "high_hour_count": summary.get("high_hour_count"),
    }


def _main_zone(report: dict[str, Any]) -> dict[str, Any]:
    provinces = report.get("province_summary")
    provinces = provinces if isinstance(provinces, list) else []
    usable = [p for p in provinces if isinstance(p, dict)]
    if usable:
        top = max(usable, key=lambda p: _num(p.get("max_score"), 0.0) or 0.0)
        return {
            "name": str(top.get("province") or "—"),
            "score": _round(top.get("max_score")),
            "severity": _meta(top.get("severity")),
            "top_station": str(top.get("top_station") or ""),
        }
    stations = _stations(report)
    if stations:
        top = stations[0]
        return {
            "name": str(top.get("region") or top.get("name") or "—"),
            "score": _round(top.get("score")),
            "severity": _meta(top.get("severity")),
            "top_station": str(top.get("name") or ""),
        }
    return {"name": "—", "score": None, "severity": _meta("normal"), "top_station": ""}


def _stations(report: dict[str, Any], limit: int | None = None) -> list[dict[str, Any]]:
    raw = report.get("stations")
    raw = raw if isinstance(raw, list) else []
    usable = [s for s in raw if isinstance(s, dict)]
    usable.sort(key=lambda s: _num(s.get("score"), 0.0) or 0.0, reverse=True)
    return usable[:limit] if limit else usable


def _network_drivers(report: dict[str, Any]) -> dict[str, float]:
    """Network-wide maxima of the human-readable weather drivers."""
    keys = [
        "max_temperature_c",
        "max_dew_point_c",
        "max_precip_probability_pct",
        "max_precipitation_mm_h",
        "max_pressure_drop_6h_hpa",
        "max_wind_gust_ms",
        "max_relative_humidity_pct",
    ]
    out: dict[str, float] = {}
    for station in _stations(report):
        for key in keys:
            value = _num(station.get(key))
            if value is not None:
                out[key] = max(out.get(key, value), value)
    return out


def _synthesis(
    op_level: dict[str, Any],
    zone: dict[str, Any],
    window: dict[str, Any],
    model_score: float | None,
    external_score: float,
) -> str:
    wording = op_level.get("label", "Veille")
    parts = [f"{wording} non officielle"]
    zone_name = zone.get("name")
    if zone_name and zone_name != "—":
        parts.append(f"zone la plus exposée : {zone_name}")
    if window.get("status") == "available":
        parts.append(f"fenêtre sensible {window.get('label')}")
    if model_score is not None:
        parts.append(f"score modèle {model_score:.2f}")
    if external_score >= 0.4:
        parts.append("confirmation externe partielle")
    elif external_score > 0:
        parts.append("confirmation externe faible")
    else:
        parts.append("pas encore de confirmation radar/foudre")
    return " · ".join(parts) + "."


def _alert_explanation(
    report: dict[str, Any],
    op_level: dict[str, Any],
    window: dict[str, Any],
    drivers: dict[str, float],
    info_graph: dict[str, Any],
    nowcast: dict[str, Any],
    external_score: float,
) -> dict[str, Any]:
    bullets: list[str] = []
    dew = drivers.get("max_dew_point_c")
    if dew is not None and dew >= 17:
        bullets.append(f"le point de rosée atteint {dew:.0f} °C (atmosphère lourde)")
    temp = drivers.get("max_temperature_c")
    if temp is not None and temp >= 27:
        bullets.append(f"la température maximale atteint {temp:.0f} °C")
    precip = drivers.get("max_precip_probability_pct")
    if precip is not None and precip >= 40 and window.get("status") == "available":
        bullets.append(
            f"la probabilité de précipitation monte à {precip:.0f} % "
            f"entre {window.get('start_hour')} et {window.get('end_hour')}"
        )
    drop = drivers.get("max_pressure_drop_6h_hpa")
    if drop is not None and drop >= 3:
        bullets.append(f"la pression chute de {drop:.1f} hPa sur 6 h")
    gust = drivers.get("max_wind_gust_ms")
    if gust is not None and gust >= 14:
        bullets.append(f"des rafales jusqu’à {gust:.0f} m/s sont prévues")

    top_names = [str(s.get("name") or s.get("station_id")) for s in _stations(report, 4)]
    top_names = [name for name in top_names if name]
    if len(top_names) >= 2:
        bullets.append("le signal est cohérent sur " + ", ".join(top_names))

    info = info_graph.get("summary") if isinstance(info_graph.get("summary"), dict) else {}
    up = info.get("top_upstream_station")
    down = info.get("top_downstream_station")
    if up and down and _clamp01(info.get("information_corridor_score")) >= 0.45:
        bullets.append(f"le graphe amont indique une propagation possible de {up} vers {down}")

    radar = str(nowcast.get("radar_confirmation") or "none")
    lightning = str(nowcast.get("lightning_confirmation") or "none")
    if external_score <= 0 and radar == "none" and lightning == "none":
        bullets.append("aucune confirmation radar/foudre suffisante n’est encore active")
    elif external_score > 0:
        bullets.append(
            "une confirmation externe partielle est présente (radar, foudre ou officiel)"
        )

    return {
        "title": f"MeteoVoid passe en « {op_level.get('label')} » parce que :",
        "bullets": bullets or ["aucun moteur n’a renvoyé de signal notable sur la grille suivie."],
        "confirmation": {
            "radar": radar,
            "lightning": lightning,
            "external_score": round(external_score, 3),
            "nowcast_ready": bool(nowcast.get("nowcast_ready")),
        },
    }


def _timeline(report: dict[str, Any], timeseries: dict[str, Any]) -> dict[str, Any]:
    series = timeseries.get("timeline") if isinstance(timeseries.get("timeline"), list) else []
    hours: list[dict[str, Any]] = []
    for row in series:
        if not isinstance(row, dict):
            continue
        hours.append(
            {
                "time": row.get("time"),
                "hour": _hour_label(row.get("time")),
                "max_score": _round(row.get("max_score")),
                "mean_score": _round(row.get("mean_score")),
                "severity": str(row.get("severity") or "normal"),
                "class": _meta(row.get("severity"))["class"],
                "nb_high_or_more": row.get("nb_high_or_more"),
                "nb_alert": row.get("nb_alert"),
            }
        )

    summary = report.get("timeline_summary")
    summary = summary if isinstance(summary, dict) else {}
    markers = []
    for key, kind, label in [
        ("first_high_time", "start", "Entrée fenêtre sensible"),
        ("peak_time", "peak", "Pic de risque"),
        ("last_high_time", "end", "Sortie fenêtre sensible"),
    ]:
        when = summary.get(key)
        if when:
            markers.append({"time": when, "hour": _hour_label(when), "kind": kind, "label": label})

    return {
        "hours": hours,
        "markers": markers,
        "summary": str(summary.get("summary") or ""),
        "narrative": _timeline_narrative(hours, summary),
    }


def _timeline_narrative(
    hours: list[dict[str, Any]], summary: dict[str, Any]
) -> list[dict[str, Any]]:
    """Plain-language hourly story derived from the timeline."""
    out: list[dict[str, Any]] = []
    seen_watch = seen_high = False
    for row in hours:
        cls = row.get("class")
        rank = _CLASS_RANK.get(cls, 0)
        if rank >= _CLASS_RANK["watch"] and not seen_watch:
            seen_watch = True
            out.append(
                {"hour": row["hour"], "kind": "watch", "text": "potentiel latent qui se charge"}
            )
        if rank >= _CLASS_RANK["elevated"] and not seen_high:
            seen_high = True
            out.append(
                {
                    "hour": row["hour"],
                    "kind": "elevated",
                    "text": "la charge convective augmente, fenêtre sensible ouverte",
                }
            )
    peak = summary.get("peak_time")
    if peak:
        peak_score = _num(summary.get("peak_score"))
        text = "pic de risque modèle"
        if peak_score is not None:
            text = f"pic de risque modèle (score {peak_score:.2f})"
        out.append({"hour": _hour_label(peak), "kind": "peak", "text": text})
    last_high = summary.get("last_high_time")
    if last_high:
        out.append(
            {
                "hour": _hour_label(last_high),
                "kind": "end",
                "text": "maintien puis dissipation attendue",
            }
        )
    if not out:
        out.append(
            {
                "hour": "—",
                "kind": "calm",
                "text": "pas de fenêtre sensible identifiée sur la période.",
            }
        )
    return out


def _transition_blocks(
    transition: dict[str, Any],
    report: dict[str, Any],
    info_graph: dict[str, Any],
    nowcast: dict[str, Any],
    drivers: dict[str, float],
) -> list[dict[str, Any]]:
    national = transition.get("national") if isinstance(transition.get("national"), dict) else {}
    indices = national.get("indices") if isinstance(national.get("indices"), dict) else {}
    info = info_graph.get("summary") if isinstance(info_graph.get("summary"), dict) else {}

    def mean_of(name: str) -> float:
        item = indices.get(name) if isinstance(indices.get(name), dict) else {}
        return _clamp01(item.get("mean"))

    def fmt(value: float | None, unit: str) -> str | None:
        if value is None:
            return None
        return f"{value:.0f} {unit}".strip()

    def phrase(score: float, low: str, mid: str, high: str) -> str:
        if score >= 0.66:
            return high
        if score >= 0.4:
            return mid
        return low

    radar = str(nowcast.get("radar_confirmation") or "none")
    lightning = str(nowcast.get("lightning_confirmation") or "none")
    observed = mean_of("observed_emergence_index")
    obs_phrase = (
        "transition observée : confirmation radar/foudre active"
        if radar not in {"none", ""} or lightning not in {"none", ""}
        else phrase(
            observed,
            "potentiel sans observation : rien de confirmé pour l’instant",
            "observation émergente possible, à confirmer au radar/foudre",
            "potentiel élevé mais observation directe encore limitée",
        )
    )

    corridor = _clamp01(info.get("information_corridor_score"))
    void_signal = _clamp01(national.get("national_void_collapse_signal"))

    blocks = [
        {
            "key": "charge",
            "title": "Charge convective",
            "score": round(mean_of("convective_load_index"), 3),
            "phrase": phrase(
                mean_of("convective_load_index"),
                "réservoir d’énergie limité",
                "énergie qui s’accumule (chaleur + humidité)",
                "fort réservoir d’énergie : chaleur et humidité élevées",
            ),
            "drivers": [
                d
                for d in [
                    fmt(drivers.get("max_temperature_c"), "°C max"),
                    fmt(drivers.get("max_dew_point_c"), "°C point de rosée"),
                ]
                if d
            ],
        },
        {
            "key": "declencheur",
            "title": "Déclencheur",
            "score": round(mean_of("trigger_readiness_index"), 3),
            "phrase": phrase(
                mean_of("trigger_readiness_index"),
                "peu de forçage pour déclencher",
                "forçage proxy présent (pluie prévue, pression)",
                "déclenchement proche : précipitations et chute de pression",
            ),
            "drivers": [
                d
                for d in [
                    fmt(drivers.get("max_precip_probability_pct"), "% pluie"),
                    (
                        f"{drivers['max_pressure_drop_6h_hpa']:.1f} hPa/6h"
                        if drivers.get("max_pressure_drop_6h_hpa")
                        else None
                    ),
                ]
                if d
            ],
        },
        {
            "key": "organisation",
            "title": "Organisation",
            "score": round(mean_of("storm_organization_potential"), 3),
            "phrase": phrase(
                mean_of("storm_organization_potential"),
                "structures peu organisées",
                "organisation possible des cellules",
                "potentiel d’organisation marqué (vent, dynamique)",
            ),
            "drivers": [d for d in [fmt(drivers.get("max_wind_gust_ms"), "m/s rafales")] if d],
        },
        {
            "key": "couvercle",
            "title": "Couvercle (inhibition)",
            "score": round(mean_of("lid_fragility_index"), 3),
            "phrase": phrase(
                mean_of("lid_fragility_index"),
                "couvercle stable, inhibition probable",
                "couvercle fragilisé, érosion possible",
                "couvercle fragile : l’inhibition peut sauter",
            ),
            "drivers": [
                d
                for d in [
                    (
                        f"{drivers['max_pressure_drop_6h_hpa']:.1f} hPa/6h"
                        if drivers.get("max_pressure_drop_6h_hpa")
                        else None
                    )
                ]
                if d
            ],
        },
        {
            "key": "observation",
            "title": "Observation émergente",
            "score": round(observed, 3),
            "phrase": obs_phrase,
            "drivers": [
                f"radar : {radar}",
                f"foudre : {lightning}",
            ],
        },
        {
            "key": "amont",
            "title": "Propagation amont",
            "score": round(corridor, 3),
            "phrase": phrase(
                corridor,
                "pas de corridor amont net",
                "corridor informationnel partiel détecté",
                "corridor amont marqué : propagation cohérente",
            ),
            "drivers": [
                d
                for d in [
                    (
                        f"amont {info.get('top_upstream_station')}"
                        if info.get("top_upstream_station")
                        else None
                    ),
                    (
                        f"aval {info.get('top_downstream_station')}"
                        if info.get("top_downstream_station")
                        else None
                    ),
                ]
                if d
            ],
        },
        {
            "key": "void",
            "title": "Void Collapse Signal",
            "score": round(void_signal, 3),
            "phrase": phrase(
                void_signal,
                "le potentiel latent reste loin d’une actualisation",
                "le potentiel latent se rapproche d’une actualisation, dépendant du déclenchement",
                "bascule probable : les composantes convergent vers un régime convectif",
            ),
            "drivers": [f"niveau : {national.get('national_transition_level', 'stable')}"],
        },
    ]
    for block in blocks:
        block["level"] = _level_from_score(block["score"])
    return blocks


def _level_from_score(score: float) -> dict[str, Any]:
    score = _clamp01(score)
    if score >= 0.82:
        return _meta("void_collapse")
    if score >= 0.66:
        return _meta("transition_probable")
    if score >= 0.45:
        return _meta("latent_unstable")
    if score >= 0.3:
        return _meta("watch")
    return _meta("stable")


def _observation(obs_gap: dict[str, Any], nowcast: dict[str, Any]) -> dict[str, Any]:
    channels = []
    for key, label in [
        ("radar", "Radar pluie"),
        ("lightning", "Foudre"),
        ("satellite", "Satellite / sommets nuageux"),
        ("gnss_water_vapour", "Vapeur d’eau GNSS"),
        ("pressure_crowd", "Pression participative"),
    ]:
        item = obs_gap.get(key) if isinstance(obs_gap.get(key), dict) else {}
        channels.append(
            {
                "key": key,
                "label": label,
                "configured": bool(item.get("configured")),
                "status": str(item.get("status") or "non configuré"),
                "source": str(item.get("source") or ""),
            }
        )
    return {
        "channels": channels,
        "nowcast": {
            "radar_confirmation": str(nowcast.get("radar_confirmation") or "none"),
            "lightning_confirmation": str(nowcast.get("lightning_confirmation") or "none"),
            "nowcast_ready": bool(nowcast.get("nowcast_ready")),
            "nowcast_score": _round(nowcast.get("nowcast_score")),
            "meaning": str(nowcast.get("meaning") or ""),
        },
        "note": str(obs_gap.get("note") or ""),
    }


def build_view_model(report_dir: Path) -> dict[str, Any]:
    report = _load_json(report_dir / "belgium_alert_report.json")
    alert_state = _load_json(report_dir / "alert_state.json")
    transition = _load_json(report_dir / "convective_transition_report.json")
    timeseries = _load_json(report_dir / "risk_timeseries.json")
    early_warning = _load_json(report_dir / "early_warning_signals.json")
    info_graph = _load_json(report_dir / "information_graph_summary.json")
    validation = _load_json(report_dir / "validation_metrics.json")
    watchdog = _load_json(report_dir / "self_watchdog.json")
    source_status = _load_json(report_dir / "source_status.json")
    obs_gap = _load_json(report_dir / "observation_gap_status.json")
    nowcast = _load_json(report_dir / "nowcast_status.json")

    operational = report.get("operational_state")
    operational = operational if isinstance(operational, dict) else alert_state
    aggregate = report.get("aggregate") if isinstance(report.get("aggregate"), dict) else {}

    op_level = _meta(operational.get("level") or alert_state.get("level"))
    severity = _meta(aggregate.get("severity") or report.get("severity"))
    model_score = _round(aggregate.get("score") or operational.get("model_score"), 3)
    external_score = _clamp01(operational.get("external_confirmation_score"))

    window = _critical_window(report)
    zone = _main_zone(report)
    drivers = _network_drivers(report)
    confidence = _confidence(operational, watchdog, early_warning, info_graph)

    national = transition.get("national") if isinstance(transition.get("national"), dict) else {}
    headline_signals = []
    top_station = _stations(report, 1)
    if top_station:
        headline_signals = [str(s)[:90] for s in (top_station[0].get("signals") or [])][:3]

    meta = {
        "generated_at": report.get("generated_at") or alert_state.get("generated_at"),
        "run_id": report.get("run_id"),
        "timezone": report.get("timezone", "Europe/Brussels"),
        "data_mode": report.get("data_mode") or source_status.get("data_mode"),
        "window": (
            report.get("target_window") if isinstance(report.get("target_window"), dict) else {}
        ),
        "disclaimer": DISCLAIMER,
        "public_wording": operational.get("public_wording") or alert_state.get("public_wording"),
        "endpoints": {
            "latest": "api/latest.json",
            "stations": "api/stations.json",
            "timeline": "api/timeline.json",
            "transition": "api/transition.json",
            "sources": "api/sources.json",
            "validation": "api/validation.json",
        },
    }

    simple = {
        "operational_level": op_level,
        "severity": severity,
        "model_score": model_score,
        "confidence": confidence,
        "critical_window": window,
        "main_zone": zone,
        "synthesis": _synthesis(op_level, zone, window, model_score, external_score),
        "public_wording": meta["public_wording"],
        "reason": operational.get("reason"),
        "headline_signals": headline_signals,
    }

    operational_view = {
        "transition_level": _meta(national.get("national_transition_level")),
        "void_collapse_signal": _round(national.get("national_void_collapse_signal"), 3),
        "interpretation": transition.get("interpretation"),
        "external_emergence_proxy": _round(transition.get("external_emergence_proxy")),
        "blocks": _transition_blocks(transition, report, info_graph, nowcast, drivers),
        "timeline": _timeline(report, timeseries),
        "alert_explanation": _alert_explanation(
            report, op_level, window, drivers, info_graph, nowcast, external_score
        ),
    }

    expert = {
        "stations": [
            {
                "name": s.get("name"),
                "station_id": s.get("station_id"),
                "region": s.get("region"),
                "score": _round(s.get("score")),
                "severity": _meta(s.get("severity")),
                "worst_time": s.get("worst_time"),
                "lat": s.get("lat"),
                "lon": s.get("lon"),
                "signals": (s.get("signals") or [])[:4],
            }
            for s in _stations(report, 12)
        ],
        "provinces": [
            {
                "province": p.get("province"),
                "max_score": _round(p.get("max_score")),
                "severity": _meta(p.get("severity")),
                "top_station": p.get("top_station"),
                "station_count": p.get("station_count"),
            }
            for p in (report.get("province_summary") or [])
            if isinstance(p, dict)
        ],
        "validation": _validation(validation),
        "observation": _observation(obs_gap, nowcast),
        "sources": _sources(source_status, report),
        "watchdog": {
            "state": watchdog.get("state"),
            "coherence_loss_score": _round(watchdog.get("coherence_loss_score")),
            "source_health": watchdog.get("source_health"),
        },
        "early_warning": (
            early_warning.get("summary") if isinstance(early_warning.get("summary"), dict) else {}
        ),
        "information_graph": (
            info_graph.get("summary") if isinstance(info_graph.get("summary"), dict) else {}
        ),
        "frames": [
            {"group": group, "label": label, "file": "reports/latest/" + file}
            for group, label, file in EXPERT_FRAMES
        ],
        "exports": [{"label": label, "file": "reports/latest/" + file} for label, file in EXPORTS],
    }

    return {"meta": meta, "simple": simple, "operational": operational_view, "expert": expert}


def _validation(validation: dict[str, Any]) -> dict[str, Any]:
    scores = validation.get("scores") if isinstance(validation.get("scores"), dict) else {}
    confusion = validation.get("confusion") if isinstance(validation.get("confusion"), dict) else {}
    return {
        "status": validation.get("status"),
        "matched_event_count": validation.get("matched_event_count"),
        "scores": {
            "brier_score": _round(scores.get("brier_score"), 4),
            "pod": _round(scores.get("pod")),
            "far": _round(scores.get("far")),
            "csi": _round(scores.get("csi")),
            "model_probability": _round(scores.get("model_probability")),
        },
        "confusion": {
            "tp": confusion.get("tp"),
            "fp": confusion.get("fp"),
            "tn": confusion.get("tn"),
            "fn": confusion.get("fn"),
        },
    }


def _sources(source_status: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    aggregate = report.get("aggregate") if isinstance(report.get("aggregate"), dict) else {}
    external = (
        source_status.get("external_confirmation")
        if isinstance(source_status.get("external_confirmation"), dict)
        else {}
    )
    auto = external.get("auto_sources") if isinstance(external.get("auto_sources"), dict) else {}
    auto_status = auto.get("status") if isinstance(auto.get("status"), list) else []
    return {
        "data_mode": source_status.get("data_mode"),
        "ok_count": source_status.get("source_ok_count", aggregate.get("source_ok_count")),
        "error_count": source_status.get("source_error_count", aggregate.get("source_error_count")),
        "health": _round(source_status.get("source_health_score")),
        "external_confirmation": {
            "score": _round(external.get("score")),
            "status": external.get("status"),
            "summary": external.get("summary"),
        },
        "auto_sources": [
            {
                "name": item.get("name"),
                "ok": bool(item.get("ok")),
                "value": item.get("value"),
                "detail": str(item.get("detail") or "")[:120],
            }
            for item in auto_status
            if isinstance(item, dict)
        ],
        "integrations": (
            report.get("integrations") if isinstance(report.get("integrations"), dict) else {}
        ),
    }


# --- output writers --------------------------------------------------------------


def _copy_outputs(report_dir: Path, site_dir: Path) -> Path:
    latest_dir = site_dir / "reports" / "latest"
    latest_dir.mkdir(parents=True, exist_ok=True)
    for name in PUBLIC_FILES:
        src = report_dir / name
        if src.exists() and src.is_file():
            shutil.copy2(src, latest_dir / name)
    return latest_dir


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False), encoding="utf-8"
    )


def build_api(vm: dict[str, Any], site_dir: Path) -> None:
    """Write the clean static JSON API consumed by the page and external clients."""
    api_dir = site_dir / "api"
    meta = vm["meta"]
    generated_at = meta.get("generated_at")

    _write_json(
        api_dir / "latest.json",
        {
            "generated_at": generated_at,
            "run_id": meta.get("run_id"),
            "timezone": meta.get("timezone"),
            "data_mode": meta.get("data_mode"),
            "window": meta.get("window"),
            "disclaimer": meta.get("disclaimer"),
            "operational_level": vm["simple"]["operational_level"],
            "severity": vm["simple"]["severity"],
            "model_score": vm["simple"]["model_score"],
            "confidence": vm["simple"]["confidence"],
            "critical_window": vm["simple"]["critical_window"],
            "main_zone": vm["simple"]["main_zone"],
            "synthesis": vm["simple"]["synthesis"],
            "public_wording": vm["simple"]["public_wording"],
            "void_collapse_signal": vm["operational"]["void_collapse_signal"],
            "transition_level": vm["operational"]["transition_level"],
            "alert_explanation": vm["operational"]["alert_explanation"],
        },
    )
    _write_json(
        api_dir / "stations.json",
        {
            "generated_at": generated_at,
            "stations": vm["expert"]["stations"],
            "provinces": vm["expert"]["provinces"],
        },
    )
    _write_json(
        api_dir / "timeline.json",
        {"generated_at": generated_at, **vm["operational"]["timeline"]},
    )
    _write_json(
        api_dir / "transition.json",
        {
            "generated_at": generated_at,
            "transition_level": vm["operational"]["transition_level"],
            "void_collapse_signal": vm["operational"]["void_collapse_signal"],
            "interpretation": vm["operational"]["interpretation"],
            "external_emergence_proxy": vm["operational"]["external_emergence_proxy"],
            "blocks": vm["operational"]["blocks"],
        },
    )
    _write_json(
        api_dir / "sources.json",
        {
            "generated_at": generated_at,
            "sources": vm["expert"]["sources"],
            "observation": vm["expert"]["observation"],
            "watchdog": vm["expert"]["watchdog"],
        },
    )
    _write_json(
        api_dir / "validation.json",
        {"generated_at": generated_at, **vm["expert"]["validation"]},
    )
    _write_json(
        api_dir / "index.json",
        {
            "generated_at": generated_at,
            "description": "MeteoVoid Belgique static API",
            "endpoints": meta.get("endpoints"),
            "disclaimer": meta.get("disclaimer"),
        },
    )


def build_index(report_dir: Path, site_dir: Path) -> dict[str, Any]:
    site_dir.mkdir(parents=True, exist_ok=True)
    _copy_outputs(report_dir, site_dir)
    vm = build_view_model(report_dir)
    build_api(vm, site_dir)

    bootstrap = json.dumps(vm, ensure_ascii=False).replace("</", "<\\/")
    page = INDEX_TEMPLATE.replace("__BOOTSTRAP__", bootstrap).replace(
        "__GENERATED_AT__", str(vm["meta"].get("generated_at") or "")
    )
    (site_dir / "index.html").write_text(page, encoding="utf-8")
    (site_dir / "README.md").write_text(
        "# MeteoVoid Belgique\n\nSite statique généré automatiquement.\n"
        "Lecture en trois niveaux (simple, opérationnel, expert) et API JSON dans `api/`.\n",
        encoding="utf-8",
    )
    return vm


# The HTML/CSS/JS shell. Data is injected as __BOOTSTRAP__; the page reads the
# api/*.json files when served over HTTP and falls back to the inlined view-model.
INDEX_TEMPLATE = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>MeteoVoid Belgique · Veille de bascule convective</title>
<style>
:root{
  --bg:#0d1726; --bg2:#0f1d31; --panel:#ffffff; --panel2:#f4f7fb; --ink:#10243d; --ink2:#0d1726;
  --muted:#6a7b90; --line:#e1e9f3; --line2:#22344d;
  --calm:#2f9e6f; --info:#3f76c0; --watch:#d6a426; --elevated:#e07a2e; --high:#dd5a30; --danger:#cf3b3b;
  --shadow:0 16px 40px rgba(6,18,33,.10);
}
*{box-sizing:border-box;}
html,body{margin:0;}
body{font-family:Inter,Segoe UI,Roboto,Arial,sans-serif;background:var(--panel2);color:var(--ink);line-height:1.5;}
a{color:#1f63b8;text-decoration:none;font-weight:600;}
a:hover{text-decoration:underline;}
.topbar{background:linear-gradient(160deg,var(--bg),var(--bg2));color:#eaf2fb;padding:18px 22px;}
.topbar .wrap{max-width:1180px;margin:0 auto;display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;}
.brand{display:flex;align-items:center;gap:12px;}
.brand .mark{width:40px;height:40px;border-radius:12px;background:#ffffff1c;display:grid;place-items:center;font-weight:800;letter-spacing:.02em;}
.brand h1{font-size:18px;margin:0;letter-spacing:-.01em;}
.brand p{margin:2px 0 0;font-size:12px;color:#b6cae0;}
.stamp{font-size:12px;color:#b6cae0;text-align:right;}
.tabs{max-width:1180px;margin:0 auto;display:flex;gap:8px;padding:14px 22px 0;flex-wrap:wrap;}
.tab{border:0;background:#ffffff14;color:#cfe0f2;padding:10px 16px;border-radius:999px 999px 0 0;font-weight:700;cursor:pointer;font-size:14px;}
.tab.active{background:var(--panel2);color:var(--ink);}
main{max-width:1180px;margin:0 auto;padding:22px;}
.disclaimer{background:#fff7e8;border:1px solid #f0d9a8;border-left:4px solid var(--elevated);border-radius:12px;padding:11px 14px;font-size:13px;margin-bottom:20px;}
.view{display:none;}
.view.active{display:block;animation:fade .25s ease;}
@keyframes fade{from{opacity:0;transform:translateY(4px);}to{opacity:1;transform:none;}}
.hero{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);gap:18px;}
.bigcard{background:var(--panel);border:1px solid var(--line);border-radius:20px;padding:22px;box-shadow:var(--shadow);}
.kicker{font-size:11px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);font-weight:800;}
.level-pill{display:inline-flex;align-items:center;gap:10px;margin-top:10px;}
.dot{width:16px;height:16px;border-radius:50%;}
.level-name{font-size:30px;font-weight:800;letter-spacing:-.02em;}
.synthesis{font-size:17px;margin:16px 0 0;color:var(--ink);}
.metarow{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;margin-top:18px;}
.metric{background:var(--panel2);border:1px solid var(--line);border-radius:14px;padding:12px 14px;}
.metric .k{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-weight:800;}
.metric .v{font-size:22px;font-weight:800;margin-top:4px;}
.metric .s{font-size:12px;color:var(--muted);}
.grid{display:grid;gap:16px;}
.cards4{grid-template-columns:repeat(4,minmax(0,1fr));}
.cards3{grid-template-columns:repeat(3,minmax(0,1fr));}
.cards2{grid-template-columns:repeat(2,minmax(0,1fr));}
.card{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:16px;box-shadow:var(--shadow);}
.card h3{margin:0 0 4px;font-size:15px;}
.card .score{font-size:30px;font-weight:800;letter-spacing:-.02em;}
.card .phrase{font-size:13px;color:#33485f;margin:8px 0;}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px;}
.chip{background:var(--panel2);border:1px solid var(--line);border-radius:999px;padding:3px 9px;font-size:12px;color:#41576e;}
.section-title{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-weight:800;margin:26px 0 12px;}
.bar{height:7px;border-radius:999px;background:#e7eef6;overflow:hidden;margin-top:10px;}
.bar > span{display:block;height:100%;border-radius:999px;}
.badge{display:inline-flex;align-items:center;border-radius:999px;padding:3px 10px;color:#fff;font-weight:700;font-size:12px;}
.calm{background:var(--calm);} .info{background:var(--info);} .watch{background:var(--watch);color:#3a2f06;}
.elevated{background:var(--elevated);} .high{background:var(--high);} .danger{background:var(--danger);}
.txt-calm{color:var(--calm);} .txt-info{color:var(--info);} .txt-watch{color:var(--watch);}
.txt-elevated{color:var(--elevated);} .txt-high{color:var(--high);} .txt-danger{color:var(--danger);}
.explain{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:18px;box-shadow:var(--shadow);}
.explain h3{margin:0 0 10px;}
.explain ul{margin:0;padding-left:20px;}
.explain li{margin:6px 0;}
.timeline-wrap{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:16px;box-shadow:var(--shadow);}
svg.timeline{width:100%;height:200px;display:block;}
.tl-narrative{display:flex;flex-direction:column;gap:8px;margin-top:14px;}
.tl-step{display:flex;gap:12px;align-items:baseline;font-size:14px;}
.tl-hour{font-weight:800;min-width:52px;color:var(--ink2);}
table{width:100%;border-collapse:collapse;font-size:13px;}
th,td{border-bottom:1px solid var(--line);padding:9px 10px;text-align:left;vertical-align:top;}
th{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);}
.subtabs{display:flex;gap:8px;flex-wrap:wrap;margin:6px 0 12px;}
.subtab{border:1px solid #cdd9e8;background:#fff;color:var(--ink);border-radius:999px;padding:7px 13px;font-weight:700;cursor:pointer;font-size:13px;}
.subtab.active{background:var(--ink2);color:#fff;border-color:var(--ink2);}
.frame-wrap{background:#fff;border:1px solid var(--line);border-radius:16px;overflow:hidden;box-shadow:var(--shadow);}
iframe{width:100%;height:70vh;min-height:560px;border:0;display:block;background:#fff;}
.links{display:flex;flex-wrap:wrap;gap:8px;}
.links a{background:#fff;border:1px solid var(--line);border-radius:999px;padding:7px 12px;font-size:13px;}
.muted{color:var(--muted);font-size:13px;}
.detail{margin-top:10px;}
.detail summary{cursor:pointer;font-weight:700;color:var(--ink2);}
footer{max-width:1180px;margin:10px auto 40px;padding:0 22px;color:var(--muted);font-size:12px;}
@media(max-width:860px){.hero{grid-template-columns:1fr;}.cards4{grid-template-columns:1fr 1fr;}.cards3{grid-template-columns:1fr;}.cards2{grid-template-columns:1fr;}.metarow{grid-template-columns:1fr;}}
</style>
</head>
<body>
<div class="topbar">
  <div class="wrap">
    <div class="brand">
      <div class="mark">MV</div>
      <div><h1>MeteoVoid Belgique</h1><p>Détecter la bascule, pas seulement afficher la météo.</p></div>
    </div>
    <div class="stamp">Dernière génération<br><strong id="stamp">__GENERATED_AT__</strong></div>
  </div>
  <div class="tabs">
    <button class="tab active" data-view="simple">Vue simple</button>
    <button class="tab" data-view="operational">Vue opérationnelle</button>
    <button class="tab" data-view="expert">Vue expert</button>
  </div>
</div>
<main>
  <div class="disclaimer" id="disclaimer"></div>
  <section class="view active" id="view-simple"></section>
  <section class="view" id="view-operational"></section>
  <section class="view" id="view-expert"></section>
</main>
<footer id="footer"></footer>
<script id="bootstrap" type="application/json">__BOOTSTRAP__</script>
<script>
const FALLBACK = JSON.parse(document.getElementById('bootstrap').textContent);
const esc = (s)=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const num = (v,d='n/a')=> (v==null||v==='')?d:(typeof v==='number'? (Number.isInteger(v)?v:v.toFixed(2)) : v);
const pct = (v)=> v==null? '—' : Math.round(Math.max(0,Math.min(1,v))*100)+'%';
const cls = (m)=> (m&&m.class)||'calm';
const colorOf = (c)=>({calm:'#2f9e6f',info:'#3f76c0',watch:'#d6a426',elevated:'#e07a2e',high:'#dd5a30',danger:'#cf3b3b'}[c]||'#2f9e6f');

function bar(score,c){const w=Math.round(Math.max(0,Math.min(1,score||0))*100);return `<div class="bar"><span style="width:${w}%;background:${colorOf(c)}"></span></div>`;}

function renderSimple(vm){
  const s=vm.simple||{}, op=s.operational_level||{}, conf=s.confidence||{}, win=s.critical_window||{}, zone=s.main_zone||{};
  const c=cls(op);
  return `
  <div class="hero">
    <div class="bigcard">
      <div class="kicker">Niveau opérationnel</div>
      <div class="level-pill"><span class="dot" style="background:${colorOf(c)}"></span><span class="level-name txt-${c}">${esc(op.label)}</span></div>
      <p class="synthesis">${esc(s.synthesis)}</p>
      <div class="metarow">
        <div class="metric"><div class="k">Score MeteoVoid</div><div class="v">${num(s.model_score)}</div><div class="s">signal modèle (0–1)</div></div>
        <div class="metric"><div class="k">Confiance du run</div><div class="v txt-${cls(conf)}">${pct(conf.score)} · ${esc(conf.label)}</div><div class="s">qualité + corroboration</div></div>
        <div class="metric"><div class="k">Fenêtre critique</div><div class="v">${esc(win.label)}</div><div class="s">heure locale (${esc(vm.meta&&vm.meta.timezone)})</div></div>
        <div class="metric"><div class="k">Zone principale</div><div class="v" style="font-size:18px">${esc(zone.name)}</div><div class="s">${esc(zone.top_station||'')}</div></div>
      </div>
    </div>
    <div class="bigcard">
      <div class="kicker">Que faut-il retenir ?</div>
      <p class="muted" style="margin-top:8px">${esc(s.reason||s.public_wording||'')}</p>
      ${(s.headline_signals&&s.headline_signals.length)?'<div class="chips">'+s.headline_signals.map(x=>`<span class="chip">${esc(x)}</span>`).join('')+'</div>':''}
      <div class="section-title" style="margin-top:18px">Facteurs de confiance</div>
      ${(conf.factors||[]).map(f=>`<div style="margin:8px 0"><div style="display:flex;justify-content:space-between;font-size:13px"><span>${esc(f.name)}</span><strong>${pct(f.value)}</strong></div>${bar(f.value,'info')}</div>`).join('')}
      <button class="subtab" style="margin-top:16px" onclick="go('operational')">Voir l’analyse complète →</button>
    </div>
  </div>
  <div class="section-title">Lecture rapide</div>
  <div class="grid cards3">
    <div class="card"><div class="kicker">Sévérité dominante</div><div style="margin-top:8px"><span class="badge ${cls(s.severity)}">${esc((s.severity||{}).label)}</span></div><p class="phrase">Classe de risque modèle la plus marquée.</p></div>
    <div class="card"><div class="kicker">Bascule (void collapse)</div><div class="score txt-${cls(vm.operational&&vm.operational.transition_level)}">${num(vm.operational&&vm.operational.void_collapse_signal)}</div><p class="phrase">${esc((vm.operational&&vm.operational.transition_level||{}).label)}</p></div>
    <div class="card"><div class="kicker">Fenêtre sensible</div><div class="score">${esc(win.start_hour||'—')}</div><p class="phrase">${win.status==='available'?('jusqu’à '+esc(win.end_hour)+', pic '+esc(win.peak_hour)):'pas de fenêtre high identifiée'}</p></div>
  </div>`;
}

function renderOperational(vm){
  const o=vm.operational||{}, blocks=o.blocks||[], tl=o.timeline||{}, ax=o.alert_explanation||{};
  const blockCards = blocks.map(b=>{
    const c=cls(b.level);
    return `<div class="card">
      <div style="display:flex;justify-content:space-between;align-items:baseline"><h3>${esc(b.title)}</h3><span class="badge ${c}">${esc((b.level||{}).label)}</span></div>
      <div class="score txt-${c}">${num(b.score)}</div>
      ${bar(b.score,c)}
      <p class="phrase">${esc(b.phrase)}</p>
      ${(b.drivers&&b.drivers.length)?'<div class="chips">'+b.drivers.map(d=>`<span class="chip">${esc(d)}</span>`).join('')+'</div>':''}
    </div>`;}).join('');
  return `
  <div class="bigcard" style="margin-bottom:18px">
    <div class="kicker">Tableau de bord · Convective Transition</div>
    <div class="level-pill"><span class="dot" style="background:${colorOf(cls(o.transition_level))}"></span><span class="level-name txt-${cls(o.transition_level)}">${esc((o.transition_level||{}).label)}</span><span class="muted">signal ${num(o.void_collapse_signal)}</span></div>
    <p class="synthesis" style="font-size:15px">${esc(o.interpretation)}</p>
  </div>
  <div class="section-title">Jauge de bascule</div>
  <div class="grid cards4">${blockCards}</div>
  <div class="section-title">Timeline horaire</div>
  <div class="timeline-wrap">
    ${renderTimelineSvg(tl)}
    <div class="tl-narrative">${(tl.narrative||[]).map(n=>`<div class="tl-step"><span class="tl-hour txt-${({watch:'watch',elevated:'elevated',peak:'danger',end:'info',calm:'calm'}[n.kind]||'info')}">${esc(n.hour)}</span><span>${esc(n.text)}</span></div>`).join('')}</div>
    <p class="muted" style="margin-top:10px">${esc(tl.summary||'')}</p>
  </div>
  <div class="section-title">Pourquoi cette alerte ?</div>
  <div class="explain">
    <h3>${esc(ax.title)}</h3>
    <ul>${(ax.bullets||[]).map(b=>`<li>${esc(b)}</li>`).join('')}</ul>
  </div>`;
}

function renderTimelineSvg(tl){
  const hours=(tl.hours||[]).filter(h=>h.max_score!=null);
  if(!hours.length) return '<p class="muted">Timeline horaire indisponible pour ce run.</p>';
  const W=1000,H=180,pad=28;
  const n=hours.length;
  const x=i=> pad + (W-2*pad)*(n<=1?0.5:i/(n-1));
  const y=v=> (H-pad) - (H-2*pad)*Math.max(0,Math.min(1,v));
  let path='', area='';
  hours.forEach((h,i)=>{const px=x(i),py=y(h.max_score);path+=(i?'L':'M')+px.toFixed(1)+' '+py.toFixed(1)+' ';});
  area = `M ${x(0).toFixed(1)} ${(H-pad)} `+hours.map((h,i)=>'L '+x(i).toFixed(1)+' '+y(h.max_score).toFixed(1)).join(' ')+` L ${x(n-1).toFixed(1)} ${(H-pad)} Z`;
  const dots=hours.map((h,i)=>`<circle cx="${x(i).toFixed(1)}" cy="${y(h.max_score).toFixed(1)}" r="3" fill="${colorOf(h.class)}"></circle>`).join('');
  const ticks=hours.map((h,i)=> (i%3===0)?`<text x="${x(i).toFixed(1)}" y="${H-6}" font-size="10" text-anchor="middle" fill="#6a7b90">${esc(h.hour)}</text>`:'').join('');
  const markers=(tl.markers||[]).map(m=>{const idx=hours.findIndex(h=>h.time===m.time);if(idx<0)return '';const px=x(idx);return `<line x1="${px.toFixed(1)}" y1="${pad-6}" x2="${px.toFixed(1)}" y2="${H-pad}" stroke="${m.kind==='peak'?'#cf3b3b':'#9fb2c8'}" stroke-dasharray="3 3"></line>`;}).join('');
  return `<svg class="timeline" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Timeline horaire du score">
    <line x1="${pad}" y1="${y(0.65).toFixed(1)}" x2="${W-pad}" y2="${y(0.65).toFixed(1)}" stroke="#f0d9a8"></line>
    <path d="${area}" fill="#3f76c022"></path>
    <path d="${path}" fill="none" stroke="#3f76c0" stroke-width="2.5"></path>
    ${markers}${dots}${ticks}
  </svg>`;
}

function renderExpert(vm){
  const e=vm.expert||{};
  const groups={};
  (e.frames||[]).forEach(f=>{(groups[f.group]=groups[f.group]||[]).push(f);});
  const groupNames=Object.keys(groups);
  const stationRows=(e.stations||[]).map(s=>`<tr><td><strong>${esc(s.name)}</strong><div class="muted">${esc(s.region||'')}</div></td><td><span class="badge ${cls(s.severity)}">${esc((s.severity||{}).label)}</span></td><td>${num(s.score)}</td><td>${esc(s.worst_time||'—')}</td><td class="muted">${esc((s.signals||[]).join(' · '))}</td></tr>`).join('');
  const provRows=(e.provinces||[]).map(p=>`<tr><td>${esc(p.province)}</td><td><span class="badge ${cls(p.severity)}">${esc((p.severity||{}).label)}</span></td><td>${num(p.max_score)}</td><td class="muted">${esc(p.top_station||'')}</td></tr>`).join('');
  const val=e.validation||{}, vs=val.scores||{}, cf=val.confusion||{};
  const obs=e.observation||{}, channels=obs.channels||[];
  const src=e.sources||{}, ext=src.external_confirmation||{};
  return `
  <div class="subtabs" id="expert-subtabs">
    <button class="subtab active" data-sub="stations">Stations & zones</button>
    <button class="subtab" data-sub="observation">Observation émergente</button>
    <button class="subtab" data-sub="validation">Validation</button>
    <button class="subtab" data-sub="sources">Sources</button>
    <button class="subtab" data-sub="maps">Cartes & graphes</button>
    <button class="subtab" data-sub="exports">Exports & API</button>
  </div>

  <div class="sub" data-sub="stations">
    <div class="section-title">Stations les plus sensibles</div>
    <div class="card" style="padding:0;overflow:auto"><table><thead><tr><th>Station</th><th>Sévérité</th><th>Score</th><th>Heure sensible</th><th>Signaux</th></tr></thead><tbody>${stationRows||'<tr><td colspan="5" class="muted">Aucune station.</td></tr>'}</tbody></table></div>
    <div class="section-title">Synthèse par province</div>
    <div class="card" style="padding:0;overflow:auto"><table><thead><tr><th>Province</th><th>Sévérité</th><th>Score max</th><th>Station pilote</th></tr></thead><tbody>${provRows||'<tr><td colspan="4" class="muted">Aucune donnée.</td></tr>'}</tbody></table></div>
  </div>

  <div class="sub" data-sub="observation" style="display:none">
    <div class="section-title">Passage du latent vers l’actualisé</div>
    <div class="grid cards3">${channels.map(ch=>`<div class="card"><div style="display:flex;justify-content:space-between;align-items:center"><h3>${esc(ch.label)}</h3><span class="badge ${ch.configured?'calm':'info'}">${ch.configured?'configuré':'préparé'}</span></div><p class="phrase">${esc(ch.status)}</p><div class="muted">${esc(ch.source)}</div></div>`).join('')}</div>
    <div class="card" style="margin-top:14px"><h3>Nowcast</h3><div class="chips"><span class="chip">radar : ${esc(obs.nowcast&&obs.nowcast.radar_confirmation)}</span><span class="chip">foudre : ${esc(obs.nowcast&&obs.nowcast.lightning_confirmation)}</span><span class="chip">prêt : ${obs.nowcast&&obs.nowcast.nowcast_ready?'oui':'non'}</span></div><p class="muted" style="margin-top:8px">${esc((obs.nowcast&&obs.nowcast.meaning)||obs.note||'')}</p></div>
  </div>

  <div class="sub" data-sub="validation" style="display:none">
    <div class="section-title">Crédibilité & capacité à se tromper</div>
    <div class="grid cards4">
      <div class="card"><div class="kicker">Statut</div><div class="phrase">${esc(val.status||'n/a')}</div></div>
      <div class="card"><div class="kicker">Épisodes testés</div><div class="score">${num(val.matched_event_count,0)}</div></div>
      <div class="card"><div class="kicker">Brier score</div><div class="score">${num(vs.brier_score)}</div></div>
      <div class="card"><div class="kicker">Prob. modèle</div><div class="score">${num(vs.model_probability)}</div></div>
      <div class="card"><div class="kicker">POD</div><div class="score">${num(vs.pod)}</div></div>
      <div class="card"><div class="kicker">FAR</div><div class="score">${num(vs.far)}</div></div>
      <div class="card"><div class="kicker">CSI</div><div class="score">${num(vs.csi)}</div></div>
      <div class="card"><div class="kicker">Confusion</div><div class="phrase">VP ${num(cf.tp,0)} · FP ${num(cf.fp,0)} · VN ${num(cf.tn,0)} · FN ${num(cf.fn,0)}</div></div>
    </div>
    <p class="muted" style="margin-top:10px">Tant qu’aucun épisode vérifié n’est fourni, ces métriques restent un cadre prêt à être rempli (détection correcte, faux positifs/négatifs, lead time).</p>
  </div>

  <div class="sub" data-sub="sources" style="display:none">
    <div class="section-title">Santé des sources</div>
    <div class="grid cards4">
      <div class="card"><div class="kicker">Mode</div><div class="phrase">${esc(src.data_mode||'n/a')}</div></div>
      <div class="card"><div class="kicker">Sources OK</div><div class="score">${num(src.ok_count,0)}</div></div>
      <div class="card"><div class="kicker">Erreurs</div><div class="score">${num(src.error_count,0)}</div></div>
      <div class="card"><div class="kicker">Confirmation externe</div><div class="score">${num(ext.score)}</div><p class="phrase">${esc(ext.status||'')}</p></div>
    </div>
    ${(src.auto_sources&&src.auto_sources.length)?'<div class="section-title">Sources externes automatiques</div><div class="card" style="padding:0;overflow:auto"><table><thead><tr><th>Source</th><th>État</th><th>Détail</th></tr></thead><tbody>'+src.auto_sources.map(a=>`<tr><td>${esc(a.name)}</td><td><span class="badge ${a.ok?'calm':'elevated'}">${a.ok?'ok':esc(a.value||'erreur')}</span></td><td class="muted">${esc(a.detail)}</td></tr>`).join('')+'</tbody></table></div>':''}
  </div>

  <div class="sub" data-sub="maps" style="display:none">
    <div class="subtabs" id="frame-tabs">${groupNames.map((g,gi)=>groups[g].map((f,fi)=>`<button class="subtab ${gi===0&&fi===0?'active':''}" data-src="${esc(f.file)}">${esc(g)} · ${esc(f.label)}</button>`).join('')).join('')}</div>
    <div class="frame-wrap"><iframe id="viewer" title="MeteoVoid expert" src="${esc((e.frames&&e.frames[0]&&e.frames[0].file)||'')}" loading="lazy"></iframe></div>
    <p class="muted" style="margin-top:8px">Active une couche à la fois pour éviter l’effet « bouillie de points ».</p>
  </div>

  <div class="sub" data-sub="exports" style="display:none">
    <div class="section-title">Exports & API statique</div>
    <div class="links">${(e.exports||[]).map(x=>`<a href="${esc(x.file)}">${esc(x.label)}</a>`).join('')}</div>
    <p class="muted" style="margin-top:10px">L’API JSON (<code>api/latest.json</code>, <code>stations</code>, <code>timeline</code>, <code>transition</code>, <code>sources</code>, <code>validation</code>) est lue par cette page et réutilisable par d’autres clients.</p>
  </div>`;
}

let VM = FALLBACK;
function paint(){
  document.getElementById('disclaimer').innerHTML = '<strong>Prototype non officiel.</strong> '+esc((VM.meta&&VM.meta.disclaimer)||'');
  document.getElementById('stamp').textContent = (VM.meta&&VM.meta.generated_at)||'';
  document.getElementById('view-simple').innerHTML = renderSimple(VM);
  document.getElementById('view-operational').innerHTML = renderOperational(VM);
  document.getElementById('view-expert').innerHTML = renderExpert(VM);
  wireExpert();
  document.getElementById('footer').innerHTML = `MeteoVoid Belgique · run <code>${esc((VM.meta&&VM.meta.run_id)||'')}</code> · mode ${esc((VM.meta&&VM.meta.data_mode)||'')} · ${esc((VM.meta&&VM.meta.disclaimer)||'')}`;
}
function go(view){
  document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active',t.dataset.view===view));
  document.querySelectorAll('.view').forEach(v=>v.classList.toggle('active',v.id==='view-'+view));
  window.scrollTo({top:0,behavior:'smooth'});
}
function wireExpert(){
  const subtabs=document.getElementById('expert-subtabs');
  if(subtabs){subtabs.querySelectorAll('.subtab').forEach(btn=>btn.addEventListener('click',()=>{
    subtabs.querySelectorAll('.subtab').forEach(b=>b.classList.remove('active'));btn.classList.add('active');
    document.querySelectorAll('#view-expert .sub').forEach(s=>s.style.display=(s.dataset.sub===btn.dataset.sub)?'block':'none');
  }));}
  const frameTabs=document.getElementById('frame-tabs'), viewer=document.getElementById('viewer');
  if(frameTabs&&viewer){frameTabs.querySelectorAll('.subtab').forEach(btn=>btn.addEventListener('click',()=>{
    frameTabs.querySelectorAll('.subtab').forEach(b=>b.classList.remove('active'));btn.classList.add('active');viewer.src=btn.dataset.src;
  }));}
}
document.querySelectorAll('.tab').forEach(t=>t.addEventListener('click',()=>go(t.dataset.view)));
paint();

// Progressive enhancement: refresh from the static JSON API when served over HTTP.
(async()=>{
  try{
    const base=(VM.meta&&VM.meta.endpoints)||{};
    const [latest,stations,timeline,transition,sources,validation]=await Promise.all(
      ['latest','stations','timeline','transition','sources','validation'].map(k=>
        fetch(base[k]||('api/'+k+'.json'),{cache:'no-store'}).then(r=>r.ok?r.json():null).catch(()=>null)));
    if(!latest) return; // offline / file:// -> keep inlined fallback
    const merged=JSON.parse(JSON.stringify(FALLBACK));
    merged.meta.generated_at = latest.generated_at||merged.meta.generated_at;
    if(stations){merged.expert.stations=stations.stations||merged.expert.stations;merged.expert.provinces=stations.provinces||merged.expert.provinces;}
    if(timeline){merged.operational.timeline=timeline;}
    if(transition){merged.operational.blocks=transition.blocks||merged.operational.blocks;merged.operational.transition_level=transition.transition_level||merged.operational.transition_level;merged.operational.void_collapse_signal=transition.void_collapse_signal;merged.operational.interpretation=transition.interpretation;}
    if(sources){merged.expert.sources=sources.sources||merged.expert.sources;merged.expert.observation=sources.observation||merged.expert.observation;merged.expert.watchdog=sources.watchdog||merged.expert.watchdog;}
    if(validation){merged.expert.validation=validation;}
    if(latest.alert_explanation){merged.operational.alert_explanation=latest.alert_explanation;}
    const active=document.querySelector('.tab.active');
    VM=merged; paint();
    if(active) go(active.dataset.view);
  }catch(e){/* keep fallback */}
})();
</script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the three-level MeteoVoid Belgium public site and JSON API."
    )
    parser.add_argument("--report-dir", required=True, type=Path)
    parser.add_argument("--site-dir", required=True, type=Path)
    args = parser.parse_args()
    build_index(args.report_dir, args.site_dir)


if __name__ == "__main__":
    main()
