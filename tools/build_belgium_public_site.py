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
import math
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
    "belgium_public_latest.json",
    "meteovoid_api_latest.json",
    "upstream_watch.json",
    "upstream_watch_report.md",
    "european_upstream_map.html",
    "upstream_corridors.csv",
    "european_radar_sources_status.json",
    "radar_stack.json",
    "radar_stack_report.md",
    "rainviewer_radar_map.html",
    "rainviewer_status.json",
    "opera_ord_status.json",
    "opera_ord_inventory.json",
    "opera_ord_files_manifest.json",
    "opera_radar_metrics.json",
    "european_national_radar_status.json",
    "european_national_radar_metrics.json",
    "european_national_radar_sources.csv",
    "european_national_radar_map.html",
    "european_national_radar_report.md",
    "europe_page_model.json",
    "radar_processing_status.json",
    "pysteps_nowcast_status.json",
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
    ("Cartes", "Radar RainViewer", "rainviewer_radar_map.html"),
    ("Cartes", "Couches avancées", "belgium_weather_layers.html"),
    ("Analyse", "Synthèse détaillée", "belgium_alert_dashboard.html"),
    ("Analyse", "Transition convective", "convective_transition_dashboard.html"),
    ("Analyse", "Graphe amont", "upstream_graph.html"),
    ("Analyse", "Europe amont", "european_upstream_map.html"),
    ("Cartes", "Radars nationaux Europe", "european_national_radar_map.html"),
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
    ("API upstream JSON", "../api/upstream.json"),
    ("API radar JSON", "../api/radar.json"),
    ("Rapport Europe amont", "upstream_watch_report.md"),
    ("Rapport radar stack", "radar_stack_report.md"),
    ("Inventaire OPERA ORD", "opera_ord_inventory.json"),
    ("Métriques radar OPERA", "opera_radar_metrics.json"),
    ("Statut radars nationaux Europe", "european_national_radar_status.json"),
    ("Métriques radars nationaux", "european_national_radar_metrics.json"),
    ("Sources radars nationaux CSV", "european_national_radar_sources.csv"),
    ("Manifest fichiers OPERA", "opera_ord_files_manifest.json"),
    ("Corridors amont CSV", "upstream_corridors.csv"),
    ("CAP XML (test)", "belgium_alert_cap.xml"),
    ("Méthodologie", "../../methodology.html"),
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
    "alert_confirmed": "high",
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
    "pre_alert_confirmed": "Pré-alerte technique",
    "alert_confirmed": "Signal technique confirmé",
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


def _window_phrase(window: dict[str, Any]) -> str:
    """Human wording for an alert window; avoids 'between 18h and 18h'."""
    if window.get("status") != "available":
        return "sur la fenêtre surveillée"
    start_h = str(window.get("start_hour") or "")
    end_h = str(window.get("end_hour") or "")
    peak_h = str(window.get("peak_hour") or "")
    if start_h and end_h and start_h != end_h:
        return f"entre {start_h} et {end_h}"
    if peak_h and peak_h != "—":
        return f"vers {peak_h}"
    if start_h and start_h != "—":
        return f"vers {start_h}"
    return "sur la fenêtre sensible"


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


def _station_card(s: dict[str, Any]) -> dict[str, Any]:
    """A map/panel-ready station record with location, drivers and a compact hourly trace."""
    hourly = []
    for h in s.get("hourly_risk") or []:
        if isinstance(h, dict):
            hourly.append({"h": _hour_label(h.get("time")), "s": _round(h.get("score"))})
    return {
        "name": s.get("name"),
        "station_id": s.get("station_id"),
        "region": s.get("region"),
        "score": _round(s.get("score")),
        "heat_stress_score": _round(s.get("heat_stress_score")),
        "convective_risk_score": _round(s.get("convective_risk_score")),
        "native_convective_available": bool(s.get("native_convective_available")),
        "native_convective_fields": s.get("native_convective_fields") or [],
        "severity": _meta(s.get("severity")),
        "worst_time": s.get("worst_time"),
        "lat": _num(s.get("lat")),
        "lon": _num(s.get("lon")),
        "signals": (s.get("signals") or [])[:5],
        "drivers": {
            "temperature_c": _round(s.get("max_temperature_c"), 1),
            "dew_point_c": _round(s.get("max_dew_point_c"), 1),
            "precip_prob_pct": _round(s.get("max_precip_probability_pct"), 0),
            "pressure_drop_hpa": _round(s.get("max_pressure_drop_6h_hpa"), 1),
            "wind_gust_ms": _round(s.get("max_wind_gust_ms"), 0),
            "humidity_pct": _round(s.get("max_relative_humidity_pct"), 0),
        },
        "hourly": hourly,
    }


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
            f"la probabilité de précipitation monte à {precip:.0f} % {_window_phrase(window)}"
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
        "title": f"MeteoVoid classe le signal en « {op_level.get('label')} » parce que :",
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


# --- heat / thermal comfort -----------------------------------------------------
#
# The heat layer is intentionally kept *separate* from the convective risk layer:
# a hot, humid atmosphere (high heat_stress_score) is not the same thing as an
# imminent storm (convective_risk_score). MeteoVoid reads temperature + dew point
# already present in each station's ``hourly_risk`` trace and derives the humidex
# (IRM / Canadian formula) plus a sober six-level comfort classification.

# heat labels reuse the shared severity *class* vocabulary (calm..danger) so the
# existing palette/CSS applies, but carry heat-specific wording.
_HEAT_LEVELS = [
    ("comfortable", "Confortable", "calm"),
    ("mild", "Chaleur légère", "info"),
    ("moderate", "Chaleur modérée", "watch"),
    ("strong", "Chaleur forte", "elevated"),
    ("very_strong", "Chaleur très forte", "high"),
    ("extreme", "Chaleur extrême", "danger"),
]


def _humidex(temp_c: float | None, dew_point_c: float | None) -> float | None:
    """Humidex (IRM / Environment Canada). Returns None when inputs are missing."""
    t = _num(temp_c)
    td = _num(dew_point_c)
    if t is None or td is None:
        return None
    # saturation vapour pressure at the dew point (hPa), then the humidex offset.
    try:
        e = 6.11 * math.exp(5417.7530 * (1.0 / 273.16 - 1.0 / (273.16 + td)))
    except (ValueError, OverflowError):
        return None
    humidex = t + 0.5555 * (e - 10.0)
    # humidex below the air temperature is meaningless; clamp to the temperature.
    return round(max(humidex, t), 1)


def _heat_rank(temp_c: float | None, humidex: float | None, heat_stress: float | None) -> int:
    """Worst-of classification across temperature, humidex and the model heat layer."""
    rank = 0
    t = _num(temp_c)
    if t is not None:
        if t >= 35:
            rank = max(rank, 5)
        elif t >= 32:
            rank = max(rank, 4)
        elif t >= 29:
            rank = max(rank, 3)
        elif t >= 26:
            rank = max(rank, 2)
        elif t >= 22:
            rank = max(rank, 1)
    hx = _num(humidex)
    if hx is not None:
        if hx >= 54:
            rank = max(rank, 5)
        elif hx >= 46:
            rank = max(rank, 4)
        elif hx >= 40:
            rank = max(rank, 3)
        elif hx >= 35:
            rank = max(rank, 2)
        elif hx >= 30:
            rank = max(rank, 1)
    hs = _clamp01(heat_stress)
    if hs >= 0.85:
        rank = max(rank, 4)
    elif hs >= 0.66:
        rank = max(rank, 3)
    elif hs >= 0.45:
        rank = max(rank, 2)
    elif hs >= 0.25:
        rank = max(rank, 1)
    return min(rank, 5)


def _heat_meta(rank: int) -> dict[str, Any]:
    key, label, cls = _HEAT_LEVELS[max(0, min(rank, len(_HEAT_LEVELS) - 1))]
    return {"key": key, "label": label, "class": cls, "rank": rank}


def _heat_advice(rank: int) -> list[str]:
    """Graduated, non-alarmist precautions matching the comfort level."""
    base = ["s’hydrater régulièrement, sans attendre la sensation de soif"]
    if rank <= 0:
        return ["conditions de chaleur sans contrainte particulière"]
    if rank == 1:
        return base + ["rester attentif en cas d’effort prolongé au soleil"]
    if rank == 2:
        return base + [
            "limiter les efforts intenses aux heures les plus chaudes",
            "profiter des zones ombragées ou ventilées",
        ]
    if rank == 3:
        return base + [
            "éviter les efforts physiques entre 12 h et 16 h",
            "garder les logements au frais (volets, aération nocturne)",
            "prendre des nouvelles des personnes isolées ou fragiles",
        ]
    if rank == 4:
        return base + [
            "reporter les efforts physiques en extérieur",
            "rechercher activement les endroits frais plusieurs heures par jour",
            "surveiller de près enfants, personnes âgées et personnes isolées",
            "guetter les signes de coup de chaleur (maux de tête, vertiges, confusion)",
        ]
    return base + [
        "rester au frais et éviter toute exposition prolongée au soleil",
        "ne jamais laisser un enfant ou un animal dans un véhicule",
        "contacter et accompagner les personnes vulnérables de l’entourage",
        "consulter sans tarder en cas de malaise, crampes ou désorientation",
    ]


def _heat_timeline(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Network hourly heat curve: per hour, the hottest temperature/humidex seen."""
    by_hour: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for s in _stations(report):
        for h in s.get("hourly_risk") or []:
            if not isinstance(h, dict):
                continue
            label = _hour_label(h.get("time"))
            temp = _num(h.get("temperature_c"))
            if temp is None:
                continue
            slot = by_hour.get(label)
            if slot is None:
                slot = {"h": label, "t": temp, "dew": _num(h.get("dew_point_c"))}
                by_hour[label] = slot
                order.append(label)
            elif temp > slot["t"]:
                slot["t"] = temp
                slot["dew"] = _num(h.get("dew_point_c"))
    points: list[dict[str, Any]] = []
    for label in order:
        slot = by_hour[label]
        points.append(
            {
                "h": label,
                "t": _round(slot["t"], 1),
                "hx": _humidex(slot["t"], slot.get("dew")),
            }
        )
    return points


def _build_heat(report: dict[str, Any]) -> dict[str, Any]:
    """Compact heat/comfort section derived from station temperature + dew point."""
    drivers = _network_drivers(report)
    max_temp = drivers.get("max_temperature_c")
    max_dew = drivers.get("max_dew_point_c")
    max_humidity = drivers.get("max_relative_humidity_pct")

    aggregate = report.get("aggregate") if isinstance(report.get("aggregate"), dict) else {}
    heat_stress = _num(aggregate.get("heat_stress_score"))
    if heat_stress is None:
        heat_stress = max(
            (_num(s.get("heat_stress_score"), 0.0) or 0.0 for s in _stations(report)),
            default=0.0,
        )

    timeline = _heat_timeline(report)
    # network humidex peak: from the network max temp+dew, but also honour the curve.
    network_humidex = _humidex(max_temp, max_dew)
    curve_humidex = [p["hx"] for p in timeline if p.get("hx") is not None]
    max_humidex = max([h for h in [network_humidex, *curve_humidex] if h is not None], default=None)

    peak_hour = "—"
    if timeline:
        peak = max(timeline, key=lambda p: _num(p.get("t"), -99.0) or -99.0)
        peak_hour = peak.get("h", "—")

    rank = _heat_rank(max_temp, max_humidex, heat_stress)
    level = _heat_meta(rank)

    hottest = []
    for s in _stations(report):
        t = _num(s.get("max_temperature_c"))
        if t is None:
            continue
        hx = _humidex(t, s.get("max_dew_point_c"))
        hottest.append(
            {
                "name": s.get("name"),
                "region": s.get("region"),
                "temperature_c": _round(t, 1),
                "humidex": hx,
                "dew_point_c": _round(s.get("max_dew_point_c"), 1),
                "heat_stress_score": _round(s.get("heat_stress_score"), 3),
                "level": _heat_meta(_heat_rank(t, hx, s.get("heat_stress_score"))),
            }
        )
    hottest.sort(key=lambda r: _num(r.get("temperature_c"), -99.0) or -99.0, reverse=True)

    return {
        "level": level,
        "max_temperature_c": _round(max_temp, 1),
        "max_humidex": max_humidex,
        "max_dew_point_c": _round(max_dew, 1),
        "max_humidity_pct": _round(max_humidity, 0),
        "heat_stress_score": _round(heat_stress, 3),
        "peak_hour": peak_hour,
        "timeline": timeline,
        "hottest": hottest[:8],
        "advice": _heat_advice(rank),
        "notable": rank >= 3,
        "note": (
            "La chaleur (lourdeur thermique) est mesurée séparément du risque "
            "convectif. Une atmosphère chaude et humide n’implique pas un orage "
            "imminent ; les deux couches sont suivies indépendamment."
        ),
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
    upstream = _load_json(report_dir / "upstream_watch.json")
    radar_stack = _load_json(report_dir / "radar_stack.json")
    opera_metrics = _load_json(report_dir / "opera_radar_metrics.json")
    opera_inventory = _load_json(report_dir / "opera_ord_inventory.json")
    national_radar = _load_json(report_dir / "european_national_radar_status.json")
    national_radar_metrics = _load_json(report_dir / "european_national_radar_metrics.json")

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
        "official_alert": bool(
            operational.get("official_alert", alert_state.get("official_alert", False))
        ),
        "public_alert_allowed": bool(
            operational.get("public_alert_allowed", alert_state.get("public_alert_allowed", False))
        ),
        "strong_external_confirmation": bool(
            operational.get("strong_external_confirmation", False)
        ),
        "endpoints": {
            "latest": "api/latest.json",
            "stations": "api/stations.json",
            "timeline": "api/timeline.json",
            "transition": "api/transition.json",
            "sources": "api/sources.json",
            "validation": "api/validation.json",
            "upstream": "api/upstream.json",
            "radar": "api/radar.json",
            "europe": "api/europe.json",
        },
    }

    simple = {
        "operational_level": op_level,
        "severity": severity,
        "model_score": model_score,
        "score_layers": {
            "heat_stress_score": _round(aggregate.get("heat_stress_score"), 3),
            "convective_risk_score": _round(aggregate.get("convective_risk_score"), 3),
            "heat_stress_mean": _round(aggregate.get("heat_stress_mean"), 3),
            "convective_risk_mean": _round(aggregate.get("convective_risk_mean"), 3),
            "contract": aggregate.get("score_layer_contract"),
        },
        "confidence": confidence,
        "critical_window": window,
        "main_zone": zone,
        "synthesis": _synthesis(op_level, zone, window, model_score, external_score),
        "public_wording": meta["public_wording"],
        "reason": operational.get("reason"),
        "headline_signals": headline_signals,
        "official_alert": meta["official_alert"],
        "public_alert_allowed": meta["public_alert_allowed"],
        "strong_external_confirmation": meta["strong_external_confirmation"],
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
        "stations": [_station_card(s) for s in _stations(report)],
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
        "upstream_watch": (
            upstream.get("summary") if isinstance(upstream.get("summary"), dict) else {}
        ),
        "radar_stack": (
            radar_stack.get("summary") if isinstance(radar_stack.get("summary"), dict) else {}
        ),
        "opera_radar_metrics": opera_metrics,
        "european_national_radar": (
            national_radar.get("summary") if isinstance(national_radar.get("summary"), dict) else {}
        ),
        "european_national_radar_metrics": national_radar_metrics,
        "opera_ord_inventory": {
            "status": opera_inventory.get("status"),
            "enabled": opera_inventory.get("enabled"),
            "queries_count": (
                len(opera_inventory.get("queries", []))
                if isinstance(opera_inventory.get("queries"), list)
                else 0
            ),
            "data_links_count": (
                len(opera_inventory.get("data_links", []))
                if isinstance(opera_inventory.get("data_links"), list)
                else 0
            ),
        },
        "frames": [
            {"group": group, "label": label, "file": "reports/latest/" + file}
            for group, label, file in EXPERT_FRAMES
        ],
        "exports": [{"label": label, "file": "reports/latest/" + file} for label, file in EXPORTS],
    }

    return {
        "meta": meta,
        "simple": simple,
        "operational": operational_view,
        "heat": _build_heat(report),
        "expert": expert,
    }


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


_EUROPE_COUNTRY_LABELS = {
    "spain": "Espagne",
    "france": "France",
    "switzerland": "Suisse",
    "netherlands": "Pays-Bas",
}

_EUROPE_COUNTRY_CONTEXT = {
    "spain": {
        "role": "Source chaude et sèche/humide selon flux sud-ouest ; utile pour suivre les bouffées de chaleur qui remontent vers la France puis le Benelux.",
        "corridor": "Espagne → Golfe de Gascogne / sud-ouest France → nord France → Belgique",
        "priority": "moyenne à élevée lors des vagues de chaleur et situations de thalweg ibérique",
    },
    "france": {
        "role": "Principal couloir amont immédiat pour la Belgique : nord France, Manche, Champagne-Ardenne, Hauts-de-France.",
        "corridor": "France nord / Manche → Hainaut → Brabant wallon → Bruxelles / Namur",
        "priority": "très élevée pour les orages arrivant par le sud-ouest, l’ouest ou la Manche",
    },
    "switzerland": {
        "role": "Surveillance alpine et air instable circulant vers l’est de la France, le Jura, le Luxembourg et l’Allemagne de l’ouest.",
        "corridor": "Alpes / Jura → est France / Luxembourg → Ardennes / Liège",
        "priority": "contextuelle, forte si le flux est sud-est ou si une ligne se structure sur l’est de la France",
    },
    "netherlands": {
        "role": "Couloir nord et nord-est : cellules remontant vers Limbourg, Anvers, Flandre ou interaction avec mer du Nord.",
        "corridor": "Pays-Bas / mer du Nord → Limbourg / Anvers / Flandre → Belgique centre",
        "priority": "élevée pour les retours nord, lignes de convergence et orages passant par le Limbourg",
    },
}


def _status_label(status: Any) -> str:
    text = str(status or "unknown")
    return text.replace("_", " ")


def _machine_label(available: Any) -> str:
    return (
        "donnée machine exploitable"
        if bool(available)
        else "interface prête, donnée machine absente"
    )


def _build_europe_model_legacy(report_dir: Path, vm: dict[str, Any]) -> dict[str, Any]:
    """Build a full Europe view-model, not just a radar link page.

    The model mirrors the public Belgium philosophy: a simple layer, an
    operational layer, a radar/corridor layer, a source registry and an expert
    export layer. It stays honest: a country becomes machine radar evidence only
    when readable files/metrics exist.
    """
    status = _load_json(report_dir / "european_national_radar_status.json")
    metrics = _load_json(report_dir / "european_national_radar_metrics.json")
    upstream = _load_json(report_dir / "upstream_watch.json")
    radar_stack = _load_json(report_dir / "radar_stack.json")
    rainviewer = _load_json(report_dir / "rainviewer_status.json")
    opera_status = _load_json(report_dir / "opera_ord_status.json")
    opera_inventory = _load_json(report_dir / "opera_ord_inventory.json")
    opera_files = _load_json(report_dir / "opera_ord_files_manifest.json")
    opera_metrics = _load_json(report_dir / "opera_radar_metrics.json")

    metric_by_country = {
        str(row.get("country")): row
        for row in metrics.get("countries", [])
        if isinstance(row, dict) and row.get("country")
    }

    country_rows = [row for row in status.get("countries", []) if isinstance(row, dict)]
    if not country_rows:
        country_rows = [
            {
                "country": row.get("country"),
                "label": _EUROPE_COUNTRY_LABELS.get(
                    str(row.get("country")), str(row.get("country", "")).title()
                ),
                "local_file_metrics": row,
                "sources": [],
            }
            for row in metrics.get("countries", [])
            if isinstance(row, dict)
        ]

    raw_corridors = upstream.get("corridors") if isinstance(upstream.get("corridors"), list) else []
    corridors = [c for c in raw_corridors if isinstance(c, dict)]

    def _corridors_for_country(country: str) -> list[dict[str, Any]]:
        prefixes = {
            "france": ("FR_", "PARIS", "CHAMPAGNE", "ENGLISH_CHANNEL"),
            "netherlands": ("NL_",),
            "switzerland": ("CH_", "ALP", "JURA"),
            "spain": ("ES_", "IBER", "BISCAY", "GASCOGNE"),
        }.get(country, ())
        found: list[dict[str, Any]] = []
        for corridor in corridors:
            source = str(corridor.get("source_region") or "")
            cid = str(corridor.get("corridor_id") or "")
            name = str(corridor.get("name") or "")
            if any(
                source.startswith(p) or cid.startswith(p) or name.upper().startswith(p)
                for p in prefixes
            ):
                found.append(corridor)
        return sorted(
            found,
            key=lambda item: _num(item.get("corridor_score"), 0.0) or 0.0,
            reverse=True,
        )

    def _source_bucket(source: dict[str, Any]) -> str:
        status_text = str(source.get("status") or "")
        if source.get("machine_evidence"):
            return "machine"
        if status_text in {
            "reachable",
            "ok",
            "configured_not_probed",
            "covered_by_opera_ord_connector",
        }:
            return "ready"
        if status_text in {"requires_api_key", "endpoint_not_configured"}:
            return "blocked"
        return "unknown"

    countries: list[dict[str, Any]] = []
    flat_sources: list[dict[str, Any]] = []
    for row in country_rows:
        if not isinstance(row, dict):
            continue
        country = str(row.get("country") or "unknown")
        local_metrics = metric_by_country.get(country) or row.get("local_file_metrics") or {}
        if not isinstance(local_metrics, dict):
            local_metrics = {}
        sources = [s for s in row.get("sources", []) if isinstance(s, dict)]
        configured = [s for s in sources if s.get("status") != "endpoint_not_configured"]
        api_required = [s for s in sources if s.get("api_key_env")]
        missing_keys = [s for s in api_required if not s.get("api_key_configured")]
        opera_fallbacks = [s for s in sources if s.get("evidence_level") == "opera_ord_fallback"]
        machine_sources = [s for s in sources if s.get("machine_evidence")]
        linked_corridors = _corridors_for_country(country)
        best_corridor_score = max(
            (_num(c.get("corridor_score"), 0.0) or 0.0 for c in linked_corridors),
            default=0.0,
        )
        priority_text = str(row.get("priority_for_belgium") or "")
        priority_score = {"high": 0.75, "medium": 0.5, "low": 0.25}.get(priority_text, 0.35)
        machine_available = bool(
            row.get("machine_radar_available") or local_metrics.get("machine_radar_available")
        )
        activity_score = _round(
            (
                row.get("radar_activity_score")
                if row.get("radar_activity_score") is not None
                else local_metrics.get("radar_activity_score")
            ),
            3,
        )
        readiness_score = round(
            _clamp01(
                0.45 * priority_score
                + 0.25 * best_corridor_score
                + 0.2 * (1.0 if configured else 0.0)
                + 0.1 * (1.0 if machine_available else 0.0)
            ),
            3,
        )
        context = _EUROPE_COUNTRY_CONTEXT.get(country, {})
        blockers: list[str] = []
        if missing_keys:
            blockers.append(
                "clé API manquante : "
                + ", ".join(str(s.get("api_key_env")) for s in missing_keys if s.get("api_key_env"))
            )
        if not machine_available:
            blockers.append("aucun fichier radar national lisible dans ce run")
        if opera_fallbacks:
            blockers.append("fallback OPERA ORD disponible pour la couche paneuropéenne")
        if not sources:
            blockers.append("aucune source nationale référencée dans ce run")

        country_payload = {
            "country": country,
            "label": row.get("label") or _EUROPE_COUNTRY_LABELS.get(country, country.title()),
            "iso2": row.get("iso2"),
            "bbox": row.get("bbox") if isinstance(row.get("bbox"), dict) else {},
            "priority_for_belgium": priority_text or context.get("priority"),
            "priority_score": priority_score,
            "readiness_score": readiness_score,
            "upstream_role": row.get("upstream_role") or context.get("role"),
            "corridor": context.get("corridor"),
            "linked_corridor_count": len(linked_corridors),
            "best_corridor_score": round(best_corridor_score, 3),
            "source_count": len(sources),
            "configured_source_count": len(configured),
            "api_required_count": len(api_required),
            "missing_api_key_count": len(missing_keys),
            "opera_fallback_count": len(opera_fallbacks),
            "machine_source_count": len(machine_sources),
            "machine_radar_available": machine_available,
            "radar_activity_score": activity_score,
            "status": local_metrics.get("status")
            or row.get("status")
            or "interface_ready_no_machine_data",
            "evidence_state": "machine_metrics" if machine_available else "interface_only",
            "readable_file_count": local_metrics.get("readable_file_count", 0),
            "file_count": local_metrics.get("file_count", 0),
            "blockers": blockers,
            "next_steps": [
                "activer ou documenter l’accès fournisseur national",
                "fournir au moins une trame radar locale lisible pour produire des métriques",
                "croiser la source nationale avec OPERA ORD et RainViewer",
            ],
            "corridors": [
                {
                    "id": c.get("corridor_id"),
                    "name": c.get("name"),
                    "score": _round(c.get("corridor_score"), 3),
                    "confidence": c.get("confidence"),
                    "source_region": c.get("source_region"),
                    "target_region": c.get("target_region"),
                    "target_zones": (
                        c.get("target_zones") if isinstance(c.get("target_zones"), list) else []
                    ),
                    "estimated_arrival_hours": c.get("estimated_arrival_hours"),
                    "interpretation": c.get("interpretation"),
                }
                for c in linked_corridors[:6]
            ],
            "sources": [
                {
                    "id": s.get("id"),
                    "provider": s.get("provider"),
                    "role": s.get("role"),
                    "status": s.get("status"),
                    "bucket": _source_bucket(s),
                    "evidence_level": s.get("evidence_level"),
                    "expected_format": s.get("expected_format"),
                    "machine_evidence": bool(s.get("machine_evidence")),
                    "api_key_env": s.get("api_key_env"),
                    "api_key_configured": s.get("api_key_configured"),
                    "update_interval_minutes": s.get("update_interval_minutes"),
                    "public_reference": s.get("public_reference"),
                    "license_note": s.get("license_note"),
                    "note": s.get("note"),
                }
                for s in sources
            ],
        }
        countries.append(country_payload)
        for source in country_payload["sources"]:
            flat_sources.append({"country": country_payload["label"], **source})

    countries.sort(
        key=lambda item: (
            not bool(item.get("machine_radar_available")),
            -float(item.get("readiness_score") or 0.0),
            str(item.get("country")),
        )
    )
    machine_count = sum(1 for item in countries if item.get("machine_radar_available"))
    configured_count = sum(1 for item in countries if item.get("configured_source_count", 0) > 0)
    missing_key_count = sum(int(item.get("missing_api_key_count") or 0) for item in countries)
    total_sources = sum(int(item.get("source_count") or 0) for item in countries)
    source_ready_count = sum(1 for item in flat_sources if item.get("bucket") == "ready")
    source_blocked_count = sum(1 for item in flat_sources if item.get("bucket") == "blocked")
    upstream_summary = upstream.get("summary") if isinstance(upstream.get("summary"), dict) else {}
    radar_summary = (
        radar_stack.get("summary") if isinstance(radar_stack.get("summary"), dict) else {}
    )
    best_corridors = sorted(
        [
            {
                "id": c.get("corridor_id"),
                "name": c.get("name"),
                "score": _round(c.get("corridor_score"), 3),
                "confidence": c.get("confidence"),
                "source_region": c.get("source_region"),
                "target_region": c.get("target_region"),
                "target_zones": (
                    c.get("target_zones") if isinstance(c.get("target_zones"), list) else []
                ),
                "estimated_arrival_hours": c.get("estimated_arrival_hours"),
                "radar_confirmation_score": _round(c.get("radar_confirmation_score"), 3),
                "moisture_feed_score": _round(c.get("moisture_feed_score"), 3),
                "upstream_activity_score": _round(c.get("upstream_activity_score"), 3),
                "interpretation": c.get("interpretation"),
            }
            for c in corridors
        ],
        key=lambda item: _num(item.get("score"), 0.0) or 0.0,
        reverse=True,
    )

    opera_file_count = (
        len(opera_files.get("files", [])) if isinstance(opera_files.get("files"), list) else 0
    )
    opera_data_link_count = (
        len(opera_inventory.get("data_links", []))
        if isinstance(opera_inventory.get("data_links"), list)
        else 0
    )
    rainviewer_status = (
        rainviewer.get("status") or radar_summary.get("rainviewer_status") or "visual_layer"
    )
    radar_layers = [
        {
            "id": "rainviewer",
            "label": "RainViewer",
            "role": "affichage radar immédiat",
            "status": rainviewer_status,
            "evidence": "display_only",
            "machine": False,
            "link": "reports/latest/rainviewer_radar_map.html",
        },
        {
            "id": "opera_ord",
            "label": "OPERA ORD",
            "role": "radar paneuropéen machine si fichiers disponibles",
            "status": opera_status.get("status") or radar_summary.get("opera_ord_status"),
            "evidence": "machine_possible",
            "machine": bool(
                opera_metrics.get("machine_radar_available")
                or opera_status.get("machine_radar_available")
            ),
            "inventory_status": opera_inventory.get("status"),
            "data_links": opera_data_link_count,
            "file_count": opera_file_count,
            "link": "reports/latest/radar_stack_report.md",
        },
        {
            "id": "national_radars",
            "label": "Radars nationaux",
            "role": "Espagne, France, Suisse, Pays-Bas",
            "status": status.get("status") or status.get("summary", {}).get("status"),
            "evidence": "country_registry",
            "machine": bool(machine_count),
            "country_count": len(countries),
            "machine_country_count": machine_count,
            "link": "reports/latest/european_national_radar_report.md",
        },
    ]

    message = (
        "Données radar machine disponibles pour au moins un pays."
        if machine_count
        else "Interfaces européennes prêtes, mais aucune donnée radar nationale lisible n’est encore fournie."
    )
    if source_blocked_count:
        message += f" {source_blocked_count} source(s) restent bloquées par une clé API, un endpoint ou une licence."

    return {
        "generated_at": vm.get("meta", {}).get("generated_at"),
        "run_id": vm.get("meta", {}).get("run_id"),
        "page_contract": "meteovoid_europe_page_full_v2",
        "disclaimer": (
            "Page Europe expérimentale : elle relie les radars nationaux disponibles, "
            "OPERA ORD, RainViewer et les corridors amont sans inventer de donnée radar fine."
        ),
        "summary": {
            "country_count": len(countries),
            "machine_country_count": machine_count,
            "configured_country_count": configured_count,
            "source_count": total_sources,
            "source_ready_count": source_ready_count,
            "source_blocked_count": source_blocked_count,
            "missing_api_key_count": missing_key_count,
            "corridor_count": len(best_corridors),
            "status": (
                status.get("summary", {}).get("status")
                if isinstance(status.get("summary"), dict)
                else status.get("status", "interface_ready")
            ),
            "machine_radar_available": bool(machine_count),
            "message": message,
        },
        "simple": {
            "headline": "Surveillance Europe amont",
            "scope": "Espagne, France, Suisse, Pays-Bas + OPERA ORD + RainViewer",
            "status_label": (
                "Donnée machine disponible"
                if machine_count
                else "Interfaces prêtes, données machine absentes"
            ),
            "machine_radar_available": bool(machine_count),
            "best_corridor": best_corridors[0] if best_corridors else None,
            "most_important_countries": countries[:4],
        },
        "operational": {
            "radar_chain": [
                {
                    "step": 1,
                    "label": "Affichage",
                    "source": "RainViewer",
                    "status": rainviewer_status,
                },
                {
                    "step": 2,
                    "label": "Donnée paneuropéenne",
                    "source": "OPERA ORD",
                    "status": opera_status.get("status"),
                },
                {
                    "step": 3,
                    "label": "Sources nationales",
                    "source": "AEMET / Météo-France / MeteoSwiss / KNMI",
                    "status": status.get("status"),
                },
                {
                    "step": 4,
                    "label": "Métriques",
                    "source": "wradlib / analyse locale",
                    "status": metrics.get("status"),
                },
                {
                    "step": 5,
                    "label": "Corridors",
                    "source": "European Upstream Watch",
                    "status": upstream_summary.get("status") or "available_if_generated",
                },
            ],
            "gaps": [
                "aucune métrique machine nationale tant qu’aucun fichier radar lisible n’est fourni",
                "les clés API nationales doivent être configurées par environnement quand le fournisseur l’exige",
                "RainViewer reste une couche visuelle, pas une preuve radar calculée",
                "OPERA ORD reste la voie unifiée recommandée pour la donnée radar paneuropéenne",
            ],
        },
        "countries": countries,
        "radar_layers": radar_layers,
        "sources": flat_sources,
        "corridors": best_corridors,
        "links": {
            "map": "reports/latest/european_national_radar_map.html",
            "report": "reports/latest/european_national_radar_report.md",
            "sources_csv": "reports/latest/european_national_radar_sources.csv",
            "radar_api": "api/radar.json",
            "europe_api": "api/europe.json",
            "rainviewer": "reports/latest/rainviewer_radar_map.html",
            "opera_report": "reports/latest/radar_stack_report.md",
            "opera_inventory": "reports/latest/opera_ord_inventory.json",
            "opera_metrics": "reports/latest/opera_radar_metrics.json",
            "upstream_map": "reports/latest/european_upstream_map.html",
            "upstream_report": "reports/latest/upstream_watch_report.md",
            "belgium": "index.html",
        },
        "layers": {
            "rainviewer": rainviewer_status,
            "opera_ord": {
                "status": opera_status.get("status") or radar_summary.get("opera_ord_status"),
                "enabled": opera_status.get("enabled") or opera_inventory.get("enabled"),
                "machine_radar_available": bool(
                    opera_metrics.get("machine_radar_available")
                    or opera_status.get("machine_radar_available")
                ),
                "inventory_status": opera_inventory.get("status"),
                "data_links": opera_data_link_count,
                "files": opera_file_count,
            },
            "national_radars": {
                "status": status.get("status"),
                "contract": status.get("contract"),
                "metrics_status": metrics.get("status"),
                "machine_radar_available": bool(machine_count),
                "country_count": len(countries),
                "machine_country_count": machine_count,
            },
            "upstream_watch": upstream_summary,
        },
        "exports": [
            {"label": "API Europe", "href": "api/europe.json"},
            {"label": "API radar", "href": "api/radar.json"},
            {
                "label": "Carte radars nationaux",
                "href": "reports/latest/european_national_radar_map.html",
            },
            {
                "label": "Rapport radars nationaux",
                "href": "reports/latest/european_national_radar_report.md",
            },
            {
                "label": "Sources radars CSV",
                "href": "reports/latest/european_national_radar_sources.csv",
            },
            {"label": "Carte RainViewer", "href": "reports/latest/rainviewer_radar_map.html"},
            {"label": "Rapport radar stack", "href": "reports/latest/radar_stack_report.md"},
            {"label": "Inventaire OPERA ORD", "href": "reports/latest/opera_ord_inventory.json"},
            {"label": "Métriques OPERA", "href": "reports/latest/opera_radar_metrics.json"},
            {"label": "Carte Europe amont", "href": "reports/latest/european_upstream_map.html"},
            {"label": "Rapport Europe amont", "href": "reports/latest/upstream_watch_report.md"},
        ],
        "raw": {
            "national_status": status,
            "national_metrics": metrics,
            "radar_stack_summary": radar_summary,
            "opera_status": opera_status,
            "opera_inventory": opera_inventory,
            "opera_metrics": opera_metrics,
            "upstream_summary": upstream_summary,
        },
    }


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
            "score_layers": vm["simple"].get("score_layers"),
            "confidence": vm["simple"]["confidence"],
            "critical_window": vm["simple"]["critical_window"],
            "main_zone": vm["simple"]["main_zone"],
            "synthesis": vm["simple"]["synthesis"],
            "public_wording": vm["simple"]["public_wording"],
            "official_alert": vm["simple"]["official_alert"],
            "public_alert_allowed": vm["simple"]["public_alert_allowed"],
            "strong_external_confirmation": vm["simple"]["strong_external_confirmation"],
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
        api_dir / "upstream.json",
        {"generated_at": generated_at, **vm["expert"].get("upstream_watch", {})},
    )
    _write_json(
        api_dir / "radar.json",
        {
            "generated_at": generated_at,
            **vm["expert"].get("radar_stack", {}),
            "opera_radar_metrics": vm["expert"].get("opera_radar_metrics", {}),
            "european_national_radar": vm["expert"].get("european_national_radar", {}),
            "european_national_radar_metrics": vm["expert"].get(
                "european_national_radar_metrics", {}
            ),
            "opera_ord_inventory": vm["expert"].get("opera_ord_inventory", {}),
        },
    )
    _write_json(
        api_dir / "heat.json",
        {"generated_at": generated_at, **vm["heat"]},
    )
    _write_json(
        api_dir / "europe.json",
        build_europe_model(site_dir / "reports" / "latest", vm),
    )

    _write_json(
        api_dir / "index.json",
        {
            "generated_at": generated_at,
            "description": "MeteoVoid Belgique static API",
            "endpoints": meta.get("endpoints"),
            "extra_endpoints": {
                "radar": "api/radar.json",
                "heat": "api/heat.json",
                "europe": "api/europe.json",
            },
            "disclaimer": meta.get("disclaimer"),
        },
    )


def _write_europe_page(site_dir: Path, model: dict[str, Any]) -> None:
    payload = json.dumps(model, ensure_ascii=False).replace("</", "<\\/")
    page = EUROPE_TEMPLATE.replace("__EUROPE_BOOTSTRAP__", payload)
    (site_dir / "europe.html").write_text(page, encoding="utf-8")


EUROPE_TEMPLATE = r"""<!doctype html>
<html lang="fr" data-theme="light">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>MeteoVoid Europe · Veille radar amont</title>
<style>
:root{--bg:#eef3f9;--card:#fff;--ink:#132033;--muted:#65738a;--line:#d9e3f0;--accent:#2f7cc0;--ok:#1d9a63;--watch:#d28a19;--danger:#c74242;--soft:#f7fafc;--shadow:0 14px 34px rgba(18,34,58,.08)}
[data-theme=dark]{--bg:#0d1625;--card:#142237;--ink:#e7eef8;--muted:#a7b5c9;--line:#293b57;--accent:#71b8ff;--soft:#101b2d;--shadow:0 14px 34px rgba(0,0,0,.22)}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,Segoe UI,Arial,sans-serif;line-height:1.5}.top{position:sticky;top:0;z-index:50;background:rgba(255,255,255,.85);backdrop-filter:blur(14px);border-bottom:1px solid var(--line)}[data-theme=dark] .top{background:rgba(13,22,37,.86)}.topin{max-width:1240px;margin:auto;padding:14px 18px;display:flex;align-items:center;justify-content:space-between;gap:16px}.brand h1{margin:0;font-size:22px}.brand p{margin:2px 0 0;color:var(--muted);font-size:13px}.nav{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.nav a,.nav button{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:999px;padding:8px 12px;text-decoration:none;cursor:pointer}.hero{max-width:1240px;margin:22px auto 0;padding:0 18px}.hero-card{background:linear-gradient(135deg,rgba(47,124,192,.16),rgba(29,154,99,.09)),var(--card);border:1px solid var(--line);border-radius:28px;padding:26px;box-shadow:var(--shadow)}.eyebrow{text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-size:12px;font-weight:700}.title{font-size:42px;line-height:1.05;margin:8px 0 12px}.lead{max-width:900px;color:var(--muted);font-size:16px}.tabs{max-width:1240px;margin:18px auto 0;padding:0 18px;display:flex;gap:8px;flex-wrap:wrap}.tab{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:14px;padding:10px 13px;cursor:pointer}.tab.active{background:var(--accent);color:#fff;border-color:var(--accent)}main{max-width:1240px;margin:18px auto 56px;padding:0 18px}.view{display:none}.view.active{display:block}.grid{display:grid;gap:14px}.kpis{grid-template-columns:repeat(6,minmax(120px,1fr))}.cards2{grid-template-columns:1.15fr .85fr}.cards3{grid-template-columns:repeat(3,minmax(0,1fr))}.cards4{grid-template-columns:repeat(4,minmax(0,1fr))}.card{background:var(--card);border:1px solid var(--line);border-radius:22px;padding:18px;box-shadow:var(--shadow)}.kpi span{display:block;color:var(--muted);font-size:13px}.kpi b{font-size:28px}.notice{border:1px solid var(--line);background:var(--card);border-radius:18px;padding:14px 16px;margin-bottom:14px;color:var(--muted)}.section-title{margin:26px 0 10px;font-weight:800;font-size:18px}.pill,.badge{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);border-radius:999px;padding:5px 10px;background:var(--soft);font-size:13px}.dot{width:9px;height:9px;border-radius:99px;display:inline-block}.ok{color:var(--ok)}.watch{color:var(--watch)}.danger{color:var(--danger)}.muted{color:var(--muted)}.score{font-size:34px;font-weight:800}.bar{height:9px;background:var(--soft);border:1px solid var(--line);border-radius:99px;overflow:hidden}.bar i{display:block;height:100%;background:var(--accent);width:0}.country-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.country h3{margin:0;font-size:22px}.head{display:flex;justify-content:space-between;gap:12px;align-items:start}.dl{display:flex;justify-content:space-between;gap:14px;border-top:1px solid var(--line);padding:9px 0}.dl span{color:var(--muted)}table{width:100%;border-collapse:collapse}th,td{border-bottom:1px solid var(--line);padding:10px;text-align:left;vertical-align:top}th{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.06em}iframe{width:100%;height:620px;border:1px solid var(--line);border-radius:20px;background:var(--card)}.links{display:flex;gap:8px;flex-wrap:wrap}.links a{border:1px solid var(--line);border-radius:999px;padding:7px 10px;color:var(--ink);text-decoration:none;background:var(--soft)}pre{white-space:pre-wrap;background:var(--soft);border:1px solid var(--line);border-radius:16px;padding:14px;max-height:420px;overflow:auto}.chain{display:grid;gap:10px}.chain-step{display:grid;grid-template-columns:48px 1fr auto;gap:10px;align-items:center}.chain-step .num{width:38px;height:38px;border-radius:99px;display:grid;place-items:center;background:var(--soft);border:1px solid var(--line);font-weight:800}.small{font-size:13px}.footer{max-width:1240px;margin:0 auto 40px;padding:0 18px;color:var(--muted)}@media(max-width:900px){.title{font-size:32px}.kpis,.cards2,.cards3,.cards4,.country-grid{grid-template-columns:1fr}iframe{height:480px}.chain-step{grid-template-columns:40px 1fr}}
</style>
</head>
<body>
<header class="top"><div class="topin"><div class="brand"><h1>MeteoVoid Europe</h1><p>Page Europe complète · radars nationaux · OPERA ORD · RainViewer · corridors amont</p></div><nav class="nav"><a href="index.html">Belgique</a><a href="europe.html">Europe</a><a href="methodology.html">Méthodologie</a><button id="theme">Thème</button></nav></div></header>
<section class="hero"><div class="hero-card"><div class="eyebrow">Surveillance européenne amont</div><h2 class="title">Espagne · France · Suisse · Pays-Bas</h2><p class="lead" id="lead"></p><div class="grid kpis" id="kpis"></div></div></section>
<div class="tabs"><button class="tab active" data-view="simple">Vue simple</button><button class="tab" data-view="operationnel">Opérationnel</button><button class="tab" data-view="carte">Carte Europe</button><button class="tab" data-view="pays">Pays</button><button class="tab" data-view="corridors">Corridors</button><button class="tab" data-view="sources">Sources</button><button class="tab" data-view="expert">Expert</button></div>
<main>
  <section class="view active" id="view-simple"></section>
  <section class="view" id="view-operationnel"></section>
  <section class="view" id="view-carte"></section>
  <section class="view" id="view-pays"></section>
  <section class="view" id="view-corridors"></section>
  <section class="view" id="view-sources"></section>
  <section class="view" id="view-expert"></section>
</main>
<footer class="footer" id="foot"></footer>
<script id="europe-bootstrap" type="application/json">__EUROPE_BOOTSTRAP__</script>
<script>
const MODEL=JSON.parse(document.getElementById('europe-bootstrap').textContent);
const esc=s=>String(s??'').replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));
const num=(v,d=2)=>v==null||v===''?'—':(typeof v==='number'?v.toFixed(d):esc(v));
const pct=v=>v==null?'—':Math.round(Number(v)*100)+' %';
const dot=(kind)=>`<span class="dot" style="background:var(--${kind})"></span>`;
const state=(ok)=>ok?`<span class="ok">${dot('ok')}donnée machine</span>`:`<span class="watch">${dot('watch')}interface prête</span>`;
function bar(v){const w=Math.max(0,Math.min(1,Number(v||0)))*100;return `<div class="bar"><i style="width:${w}%"></i></div>`}
function pill(text,kind='accent'){return `<span class="pill">${dot(kind)}${esc(text)}</span>`}
function renderKpis(){const s=MODEL.summary||{};document.getElementById('lead').textContent=MODEL.disclaimer||'';document.getElementById('kpis').innerHTML=[['Pays suivis',s.country_count],['Métriques machine',s.machine_country_count],['Sources radar',s.source_count],['Sources prêtes',s.source_ready_count],['Sources bloquées',s.source_blocked_count],['Corridors',s.corridor_count]].map(x=>`<div class="card kpi"><span>${esc(x[0])}</span><b>${esc(x[1]??0)}</b></div>`).join('')}
function renderSimple(){const s=MODEL.summary||{},simple=MODEL.simple||{},best=simple.best_corridor||{};const countries=(MODEL.countries||[]).slice(0,4);return `<div class="notice"><b>Statut Europe :</b> ${esc(s.message||'')} MeteoVoid Europe ne transforme pas une carte affichée en preuve radar : la preuve machine exige un fichier radar lisible et des métriques calculées.</div><div class="grid cards2"><div class="card"><div class="eyebrow">Lecture simple</div><h2>${esc(simple.status_label||'Interface prête')}</h2><p class="muted">${esc(simple.scope||'')}</p><div class="links">${(MODEL.radar_layers||[]).map(l=>pill(l.label+': '+(l.status||'n/a'),l.machine?'ok':'watch')).join('')}</div><div class="section-title">Meilleur corridor amont</div>${best&&best.name?`<h3>${esc(best.name)}</h3><p class="muted">${esc(best.interpretation||'')}</p>${bar(best.score)}<p class="small muted">score ${num(best.score)} · confiance ${esc(best.confidence||'—')}</p>`:'<p class="muted">Aucun corridor amont détaillé disponible dans ce run.</p>'}</div><div class="card"><div class="eyebrow">Pays prioritaires</div>${countries.map(c=>`<div class="dl"><span>${esc(c.label)}</span><strong>${esc(c.priority_for_belgium||'—')} · ${state(c.machine_radar_available)}</strong></div>`).join('')}<div class="section-title">À retenir</div><p class="muted">France et Pays-Bas sont les couloirs les plus proches pour la Belgique. Espagne et Suisse servent surtout à lire l’origine de l’énergie, de l’humidité et des flux plus lointains.</p></div></div>`}
function renderOperational(){const op=MODEL.operational||{};return `<div class="grid cards2"><div class="card"><div class="eyebrow">Chaîne opérationnelle Europe</div><h2>Source → radar → métrique → corridor</h2><div class="chain">${(op.radar_chain||[]).map(step=>`<div class="chain-step"><div class="num">${esc(step.step)}</div><div><b>${esc(step.label)}</b><p class="muted small">${esc(step.source)}</p></div><span class="badge">${esc(step.status||'n/a')}</span></div>`).join('')}</div></div><div class="card"><div class="eyebrow">Limites actives</div><h2>Ce qui manque encore</h2><ul>${(op.gaps||[]).map(g=>`<li>${esc(g)}</li>`).join('')}</ul><p class="muted">Cette page est conçue pour afficher la différence entre interface disponible, source joignable, fichier lisible et preuve radar calculée.</p></div></div><div class="section-title">Couches radar</div><div class="grid cards3">${(MODEL.radar_layers||[]).map(l=>`<div class="card"><h3>${esc(l.label)}</h3><p class="muted">${esc(l.role)}</p><div class="score ${l.machine?'ok':'watch'}">${l.machine?'OK':'PRÊT'}</div><div class="dl"><span>Statut</span><strong>${esc(l.status||'n/a')}</strong></div><div class="dl"><span>Preuve</span><strong>${esc(l.evidence||'')}</strong></div>${l.link?`<div class="links"><a href="${esc(l.link)}">ouvrir</a></div>`:''}</div>`).join('')}</div>`}
function renderMap(){return `<div class="grid cards2"><iframe src="reports/latest/european_national_radar_map.html" title="Carte radars nationaux Europe"></iframe><div class="card"><div class="eyebrow">Cartes liées</div><h2>Radar et amont</h2><p class="muted">La carte nationale montre les zones couvertes par Espagne, France, Suisse et Pays-Bas. Elle ne confirme pas seule une cellule active.</p><div class="links">${[['Radars nationaux','reports/latest/european_national_radar_map.html'],['RainViewer','reports/latest/rainviewer_radar_map.html'],['Europe amont','reports/latest/european_upstream_map.html'],['Belgique','index.html']].map(x=>`<a href="${x[1]}">${x[0]}</a>`).join('')}</div><div class="section-title">Lecture des couleurs</div><p class="muted">Vert signifie que des métriques machine existent. Orange ou bleu signifie que l’interface est prête mais qu’aucune donnée lisible n’a encore été injectée.</p></div></div>`}
function countryCard(c){return `<article class="card country"><div class="head"><div><div class="eyebrow">${esc(c.iso2||c.country)}</div><h3>${esc(c.label)}</h3></div><span class="badge">${state(c.machine_radar_available)}</span></div><p class="muted">${esc(c.upstream_role||'')}</p><p><b>Corridor :</b> ${esc(c.corridor||'—')}</p><div class="score">${num(c.readiness_score)}</div><div class="muted">indice de préparation Europe</div>${bar(c.readiness_score)}<div class="dl"><span>Priorité Belgique</span><strong>${esc(c.priority_for_belgium||'—')}</strong></div><div class="dl"><span>Sources</span><strong>${esc(c.configured_source_count||0)} prêtes / ${esc(c.source_count||0)} référencées</strong></div><div class="dl"><span>Fichiers lisibles</span><strong>${esc(c.readable_file_count||0)} / ${esc(c.file_count||0)}</strong></div><div class="dl"><span>Corridors liés</span><strong>${esc(c.linked_corridor_count||0)}</strong></div><div class="section-title">Blocages</div><ul>${(c.blockers||[]).map(b=>`<li>${esc(b)}</li>`).join('')}</ul></article>`}
function renderCountries(){return `<div class="section-title">Lecture par pays</div><div class="grid country-grid">${(MODEL.countries||[]).map(countryCard).join('')}</div>`}
function renderCorridors(){const rows=(MODEL.corridors||[]);return `<div class="card"><div class="eyebrow">Propagation vers la Belgique</div><h2>Corridors amont</h2><p class="muted">Ces corridors relient les zones sources européennes à des zones belges cibles. Ils ne sont pas une trajectoire radar certaine, mais une lecture de propagation possible.</p></div><div class="card" style="overflow:auto;margin-top:14px"><table><thead><tr><th>Corridor</th><th>Score</th><th>Source</th><th>Cibles</th><th>Fenêtre</th><th>Lecture</th></tr></thead><tbody>${rows.map(c=>`<tr><td><b>${esc(c.name||c.id)}</b><p class="muted small">${esc(c.id||'')}</p></td><td>${num(c.score)}</td><td>${esc(c.source_region||'—')}</td><td>${esc((c.target_zones||[]).join(', '))}</td><td>${esc((c.estimated_arrival_hours||[]).join(' à '))} h</td><td>${esc(c.interpretation||'')}</td></tr>`).join('')}</tbody></table></div>`}
function renderSources(){const rows=MODEL.sources||[];return `<div class="grid cards3"><div class="card"><h3>Sources prêtes</h3><div class="score ok">${esc((MODEL.summary||{}).source_ready_count||0)}</div></div><div class="card"><h3>Sources bloquées</h3><div class="score watch">${esc((MODEL.summary||{}).source_blocked_count||0)}</div></div><div class="card"><h3>Clés manquantes</h3><div class="score watch">${esc((MODEL.summary||{}).missing_api_key_count||0)}</div></div></div><div class="section-title">Registre des sources</div><div class="card" style="overflow:auto"><table><thead><tr><th>Pays</th><th>Fournisseur</th><th>Statut</th><th>Niveau</th><th>Format</th><th>Clé</th></tr></thead><tbody>${rows.map(s=>`<tr><td><b>${esc(s.country)}</b></td><td>${esc(s.provider)}<p class="muted small">${esc(s.role||'')}</p></td><td>${esc(s.status||'')}</td><td>${esc(s.evidence_level||'')}</td><td>${esc(s.expected_format||'—')}</td><td>${s.api_key_env?esc(s.api_key_env)+(s.api_key_configured?' configurée':' manquante'):'—'}</td></tr>`).join('')}</tbody></table></div>`}
function renderExpert(){return `<div class="grid cards2"><div class="card"><div class="eyebrow">Exports</div><h2>Données Europe</h2><div class="links">${(MODEL.exports||[]).map(x=>`<a href="${esc(x.href)}">${esc(x.label)}</a>`).join('')}</div></div><div class="card"><div class="eyebrow">Contrat</div><h2>${esc(MODEL.page_contract||'')}</h2><p class="muted">Run ${esc(MODEL.run_id||'')} · ${esc(MODEL.generated_at||'')}</p></div></div><div class="section-title">Modèle brut</div><pre>${esc(JSON.stringify(MODEL,null,2))}</pre>`}
function paint(){renderKpis();document.getElementById('view-simple').innerHTML=renderSimple();document.getElementById('view-operationnel').innerHTML=renderOperational();document.getElementById('view-carte').innerHTML=renderMap();document.getElementById('view-pays').innerHTML=renderCountries();document.getElementById('view-corridors').innerHTML=renderCorridors();document.getElementById('view-sources').innerHTML=renderSources();document.getElementById('view-expert').innerHTML=renderExpert();document.getElementById('foot').textContent=`MeteoVoid Europe · ${MODEL.generated_at||''} · ${MODEL.run_id||''}`}
document.querySelectorAll('.tab').forEach(btn=>btn.addEventListener('click',()=>{document.querySelectorAll('.tab').forEach(b=>b.classList.remove('active'));btn.classList.add('active');document.querySelectorAll('.view').forEach(v=>v.classList.toggle('active',v.id==='view-'+btn.dataset.view));window.scrollTo({top:0,behavior:'smooth'});}));document.getElementById('theme').onclick=()=>{document.documentElement.dataset.theme=document.documentElement.dataset.theme==='dark'?'light':'dark'};paint();
</script>
</body>
</html>"""


def _write_methodology_page(site_dir: Path) -> None:
    html_page = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>MeteoVoid Belgique · Méthodologie</title>
<style>
body{margin:0;font-family:Inter,Segoe UI,Arial,sans-serif;background:#f5f7fb;color:#162033;line-height:1.6}main{max-width:920px;margin:0 auto;padding:32px 18px 56px}.card{background:white;border:1px solid #dbe3ef;border-radius:18px;padding:20px;margin:16px 0;box-shadow:0 8px 22px rgba(15,31,53,.06)}h1{font-size:30px;margin:0 0 8px}h2{font-size:19px;margin:0 0 8px}.muted{color:#697386}.pill{display:inline-block;border:1px solid #cad7e7;border-radius:999px;padding:4px 10px;margin:3px;background:#eef4fb;font-size:13px}code{background:#edf2f7;border-radius:7px;padding:2px 6px}a{color:#174d86}</style>
</head>
<body><main>
<a href="index.html">Retour au tableau de bord</a>
<h1>Méthodologie MeteoVoid Belgique</h1>
<p class="muted">Prototype technique expérimental. Cette page explique le contrat public, les limites et la séparation entre modèle interne, confirmation externe et sources officielles.</p>
<div class="card"><h2>Statut non officiel</h2><p>MeteoVoid ne publie pas une alerte officielle et ne remplace pas l’IRM/KMI, MeteoAlarm, les autorités locales, le radar ou le nowcast foudre. Le système produit une veille expérimentale destinée à repérer une dynamique à surveiller.</p></div>
<div class="card"><h2>Trois niveaux de signal</h2><p><span class="pill">Signal interne</span> score calculé à partir des stations et des composantes météo disponibles.</p><p><span class="pill">Confirmation externe</span> signaux officiels, radar, foudre, MeteoAlarm ou ESTOFEX lorsqu’ils sont renseignés.</p><p><span class="pill">Publication prudente</span> niveau opérationnel qui dépend de la convergence entre modèle et confirmation externe.</p></div>
<div class="card"><h2>Séparation des scores</h2><p>Le score global est complété par deux couches distinctes : <code>heat_stress_score</code> pour la lourdeur thermique et <code>convective_risk_score</code> pour le risque convectif. Cela évite de confondre une atmosphère chaude et humide avec un orage violent déjà probable.</p></div>
<div class="card"><h2>Indices convectifs natifs</h2><p>Le contrat <code>native_convective_fields_optional_v1</code> prépare l’intégration de champs comme CAPE, CIN, Lifted Index, cisaillement 0-6 km, SRH, LCL, LFC, eau précipitable et lapse rate. Si le fournisseur météo ne livre pas ces champs, MeteoVoid conserve un mode proxy explicite.</p></div>
<div class="card"><h2>Validation historique</h2><p>Le fichier <code>config/belgium_verified_storm_events.csv</code> sert de registre d’événements vérifiés pour mesurer vrais positifs, faux positifs, faux négatifs et délai de détection. Sans événements vérifiés, le replay indique que la validation historique reste à compléter.</p></div>
<div class="card"><h2>Europe amont</h2><p>La couche <code>European Upstream Watch</code> suit des régions sources et des couloirs de propagation vers la Belgique. Elle peut utiliser Open‑Meteo comme fallback pour les flux et les niveaux de pression. Les cartes radar européennes ou la foudre ne sont intégrées que si une interface/licence explicite est configurée ; sinon le rapport indique <code>interface_only_unconfigured</code> et n’invente aucune confirmation.</p></div>
<div class="card"><h2>Contrats publics</h2><p>Le fichier canonique de statut public est <code>belgium_public_latest.json</code>. L’ancien <code>meteovoid_api_latest.json</code> reste disponible comme alias de compatibilité.</p></div>
</main></body></html>"""
    (site_dir / "methodology.html").write_text(html_page, encoding="utf-8")


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
    _write_europe_page(site_dir, build_europe_model(site_dir / "reports" / "latest", vm))
    _write_methodology_page(site_dir)
    (site_dir / "README.md").write_text(
        "# MeteoVoid Belgique\n\nSite statique généré automatiquement.\n"
        "Lecture en trois niveaux (simple, opérationnel, expert), page Europe, page méthodologie et API JSON dans `api/`.\n",
        encoding="utf-8",
    )
    return vm


# The HTML/CSS/JS shell. Data is injected as __BOOTSTRAP__; the page reads the
# api/*.json files when served over HTTP and falls back to the inlined view-model.
INDEX_TEMPLATE = r"""<!doctype html>
<html lang="fr" data-theme="light">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>MeteoVoid Belgique · Veille de bascule convective</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<style>
:root{
  --bg:#e9edf3; --bg-2:#eef2f7; --panel:#ffffff; --panel-2:#f4f7fb; --inset:#eef3f9;
  --ink:#0a1322; --ink-2:#43546b; --muted:#82909f; --line:#e1e8f0; --line-2:#edf1f6;
  --accent:#2f49d8; --accent-soft:#eaedfb;
  --grid:rgba(20,40,80,.035);
  --shadow-sm:0 1px 2px rgba(13,28,55,.05), 0 2px 8px rgba(13,28,55,.04);
  --shadow:0 2px 4px rgba(13,28,55,.05), 0 12px 30px rgba(13,28,55,.07);
  --shadow-lg:0 30px 70px rgba(10,22,48,.16);
  --r:14px; --r-sm:10px; --r-lg:20px;
  --f-display:'Space Grotesk',ui-sans-serif,system-ui,Segoe UI,sans-serif;
  --f-body:'Inter',ui-sans-serif,system-ui,Segoe UI,Roboto,Arial,sans-serif;
  --f-mono:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,monospace;
  --c-calm:#16a075; --c-info:#3a7ec4; --c-watch:#cf9a1f; --c-elevated:#dd7634; --c-high:#d65238; --c-danger:#cf2e39;
}
[data-theme="dark"]{
  --bg:#070b13; --bg-2:#0a101b; --panel:#111826; --panel-2:#0d141f; --inset:#0c121d;
  --ink:#e9f0fa; --ink-2:#9fb1c8; --muted:#697a92; --line:#1e293b; --line-2:#172132;
  --accent:#6f84ff; --accent-soft:#1a2240;
  --grid:rgba(120,160,230,.045);
  --shadow-sm:0 1px 2px rgba(0,0,0,.4);
  --shadow:0 2px 6px rgba(0,0,0,.45), 0 18px 40px rgba(0,0,0,.5);
  --shadow-lg:0 30px 80px rgba(0,0,0,.6);
  --c-calm:#1cb98a; --c-info:#5298e0; --c-watch:#e3b13b; --c-elevated:#ef8a4c; --c-high:#ec6a50; --c-danger:#e74752;
}
*{box-sizing:border-box;}
html,body{margin:0;}
body{font-family:var(--f-body);color:var(--ink);line-height:1.5;-webkit-font-smoothing:antialiased;background:var(--bg);
  background-image:
    radial-gradient(1200px 480px at 84% -10%, color-mix(in srgb,var(--accent) 7%, transparent), transparent),
    linear-gradient(var(--grid) 1px, transparent 1px),
    linear-gradient(90deg, var(--grid) 1px, transparent 1px);
  background-size:auto, 34px 34px, 34px 34px; background-attachment:fixed;}
a{color:var(--accent);text-decoration:none;font-weight:600;} a:hover{text-decoration:underline;}
button{font-family:inherit;}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:6px;}
.mono{font-family:var(--f-mono);} .display{font-family:var(--f-display);}
.tabular,.read,.tile-v,.kpi-v,.score,.gauge-num{font-variant-numeric:tabular-nums;}
.icon{width:18px;height:18px;stroke:currentColor;fill:none;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round;display:block;}
/* severity tokens: one accent per class, washes via color-mix so they adapt to theme */
.ac-calm{--ac:var(--c-calm);} .ac-info{--ac:var(--c-info);} .ac-watch{--ac:var(--c-watch);}
.ac-elevated{--ac:var(--c-elevated);} .ac-high{--ac:var(--c-high);} .ac-danger{--ac:var(--c-danger);}
.ac-calm,.ac-info,.ac-watch,.ac-elevated,.ac-high,.ac-danger{--aci:color-mix(in srgb, var(--ac), var(--ink) 30%);--acw:color-mix(in srgb, var(--ac) 12%, var(--panel));}
[data-theme="dark"] .ac-calm,[data-theme="dark"] .ac-info,[data-theme="dark"] .ac-watch,[data-theme="dark"] .ac-elevated,[data-theme="dark"] .ac-high,[data-theme="dark"] .ac-danger{--aci:color-mix(in srgb, var(--ac), white 22%);--acw:color-mix(in srgb, var(--ac) 16%, var(--panel));}
.txt-calm{color:var(--c-calm);} .txt-info{color:var(--c-info);} .txt-watch{color:var(--c-watch);} .txt-elevated{color:var(--c-elevated);} .txt-high{color:var(--c-high);} .txt-danger{color:var(--c-danger);}
[data-theme="dark"] .txt-calm,[data-theme="dark"] .txt-info,[data-theme="dark"] .txt-watch,[data-theme="dark"] .txt-elevated,[data-theme="dark"] .txt-high,[data-theme="dark"] .txt-danger{filter:brightness(1.12);}
/* ---- command bar ---- */
.cmd{position:sticky;top:0;z-index:20;background:color-mix(in srgb,var(--panel) 86%, transparent);backdrop-filter:blur(14px) saturate(1.3);-webkit-backdrop-filter:blur(14px) saturate(1.3);border-bottom:1px solid var(--line);}
.cmd-wrap{max-width:1240px;margin:0 auto;display:flex;align-items:center;gap:18px;padding:12px 24px;}
.brand{display:flex;align-items:center;gap:12px;min-width:0;}
.brand .mark{width:40px;height:40px;border-radius:12px;background:linear-gradient(140deg,#1c9f9c,#2f49d8);display:grid;place-items:center;box-shadow:0 6px 18px color-mix(in srgb,var(--accent) 40%, transparent);flex:none;}
.brand .mark svg{width:22px;height:22px;color:#fff;}
.brand h1{font-family:var(--f-display);font-size:17px;font-weight:600;margin:0;letter-spacing:-.02em;line-height:1.1;}
.brand p{margin:1px 0 0;font-size:11.5px;color:var(--muted);letter-spacing:.01em;}
.cmd-right{margin-left:auto;display:flex;align-items:center;gap:14px;}
.status-chip{display:flex;align-items:center;gap:9px;border:1px solid var(--line);border-radius:999px;padding:6px 12px 6px 11px;background:var(--panel-2);}
.live-dot{width:8px;height:8px;border-radius:50%;background:var(--c-calm);position:relative;flex:none;}
.live-dot:after{content:"";position:absolute;inset:-4px;border-radius:50%;border:1.5px solid var(--c-calm);opacity:.7;animation:pulse 2s ease-out infinite;}
@keyframes pulse{0%{transform:scale(.55);opacity:.7;}100%{transform:scale(2);opacity:0;}}
.status-chip .st-k{font-family:var(--f-mono);font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;}
.status-chip .st-v{font-family:var(--f-mono);font-size:12px;color:var(--ink);font-weight:600;}
.tgl{width:38px;height:38px;border-radius:11px;border:1px solid var(--line);background:var(--panel-2);color:var(--ink-2);display:grid;place-items:center;cursor:pointer;transition:.15s;flex:none;}
.tgl:hover{color:var(--ink);border-color:color-mix(in srgb,var(--ink) 24%, var(--line));}
.tgl .icon{width:19px;height:19px;}
/* tabs */
.tabs{max-width:1240px;margin:0 auto;display:flex;gap:2px;padding:0 24px;overflow-x:auto;scrollbar-width:none;}
.tabs::-webkit-scrollbar{display:none;}
.tab{position:relative;border:0;background:transparent;color:var(--muted);padding:12px 15px 13px;font-weight:600;cursor:pointer;font-size:13.5px;white-space:nowrap;letter-spacing:-.005em;}
.tab:after{content:"";position:absolute;left:12px;right:12px;bottom:0;height:2px;background:var(--accent);border-radius:2px 2px 0 0;transform:scaleX(0);transition:transform .22s cubic-bezier(.2,.7,.2,1);}
.tab:hover{color:var(--ink);} .tab.active{color:var(--ink);} .tab.active:after{transform:scaleX(1);}
.tab .tab-led{display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:7px;vertical-align:middle;background:var(--led,transparent);}
main{max-width:1240px;margin:0 auto;padding:26px 24px 10px;}
.disclaimer{display:flex;gap:10px;align-items:flex-start;border:1px solid color-mix(in srgb,var(--c-watch) 32%, var(--line));border-left:3px solid var(--c-watch);border-radius:var(--r-sm);padding:11px 14px;font-size:12.5px;color:var(--ink-2);margin-bottom:22px;background:color-mix(in srgb,var(--c-watch) 8%, var(--panel));}
.disclaimer .icon{width:17px;height:17px;color:var(--c-watch);flex:none;margin-top:1px;}
.disclaimer b{color:var(--ink);font-weight:700;}
.view{display:none;} .view.active{display:block;}
.view.active>*{animation:rise .4s both;} .view.active>*:nth-child(2){animation-delay:.04s;} .view.active>*:nth-child(3){animation-delay:.08s;} .view.active>*:nth-child(4){animation-delay:.12s;}
@keyframes rise{from{opacity:0;transform:translateY(10px);}to{opacity:1;transform:none;}}
.eyebrow{font-family:var(--f-mono);font-size:10.5px;text-transform:uppercase;letter-spacing:.14em;color:var(--muted);font-weight:600;}
.section-title{font-family:var(--f-mono);font-size:11px;text-transform:uppercase;letter-spacing:.13em;color:var(--muted);font-weight:600;margin:30px 0 13px;display:flex;align-items:center;gap:10px;}
.section-title:before{content:"";width:5px;height:5px;border-radius:50%;background:var(--accent);}
.muted{color:var(--muted);font-size:13px;} .lead{color:var(--ink-2);margin:0 0 12px;}
/* ---- hero ---- */
.hero{position:relative;border:1px solid var(--line);border-radius:var(--r-lg);background:var(--panel);box-shadow:var(--shadow);overflow:hidden;}
.hero:before{content:"";position:absolute;inset:0;background:radial-gradient(620px 280px at 90% -40%, var(--acw,transparent), transparent);pointer-events:none;}
.hero-top{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:24px;align-items:center;padding:26px 28px 8px;}
.hero-led{display:inline-flex;align-items:center;gap:9px;margin-bottom:6px;}
.hero-led .led{width:9px;height:9px;border-radius:50%;background:var(--ac,var(--accent));box-shadow:0 0 0 4px var(--acw,transparent);}
.hero-led .led-k{font-family:var(--f-mono);font-size:10.5px;text-transform:uppercase;letter-spacing:.13em;color:var(--muted);font-weight:600;}
.hero-level{font-family:var(--f-display);font-size:clamp(30px,5vw,46px);line-height:1.02;margin:4px 0 10px;letter-spacing:-.03em;color:var(--aci,var(--ink));font-weight:600;}
.hero-syn{font-size:15px;color:var(--ink-2);margin:0;max-width:60ch;}
.hero-tags{margin-top:13px;display:flex;gap:7px;flex-wrap:wrap;}
.hero-dial{display:grid;place-items:center;}
/* signature: transition track */
.track-zone{padding:14px 28px 24px;}
.track-head{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:4px;}
.track-head .tk{font-family:var(--f-mono);font-size:10.5px;text-transform:uppercase;letter-spacing:.13em;color:var(--muted);font-weight:600;}
.track-head .tv{font-family:var(--f-display);font-size:15px;color:var(--aci,var(--ink));font-weight:600;}
.transition-track{display:block;width:100%;height:auto;overflow:visible;}
.tt-base{fill:var(--inset);}
.tt-grad{opacity:.5;}
.tt-thr{stroke:var(--ink-2);stroke-width:1.4;stroke-dasharray:3 3;opacity:.55;}
.tt-thr-cap{font-family:var(--f-mono);font-size:9.5px;fill:var(--ink-2);text-transform:uppercase;letter-spacing:.06em;}
.tt-mark{transition:transform .9s cubic-bezier(.2,.75,.2,1);}
.tt-lab{font-family:var(--f-mono);font-size:9.5px;fill:var(--muted);letter-spacing:.04em;}
.tt-lab.on{fill:var(--aci);font-weight:600;}
/* ring / gauge */
.dial{display:block;} .dial .arc{transition:stroke-dasharray .9s cubic-bezier(.2,.75,.2,1);}
.gauge-num{font-family:var(--f-display);font-weight:600;letter-spacing:-.02em;}
.gauge-cap{font-family:var(--f-mono);font-size:9.5px;fill:var(--muted);text-transform:uppercase;letter-spacing:.1em;}
.gauge-sub{font-family:var(--f-mono);font-size:10px;fill:var(--muted);}
/* kpi tiles */
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:13px;margin:20px 0;}
.kpi{position:relative;background:var(--panel);border:1px solid var(--line);border-radius:var(--r);padding:16px 16px 15px;box-shadow:var(--shadow-sm);transition:transform .16s, box-shadow .16s, border-color .16s;overflow:hidden;}
.kpi:hover{transform:translateY(-2px);box-shadow:var(--shadow);border-color:color-mix(in srgb,var(--ac,var(--accent)) 30%, var(--line));}
.kpi:before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--ac,var(--accent));opacity:.85;}
.kpi-head{display:flex;align-items:center;gap:8px;color:var(--ac,var(--accent));margin-bottom:9px;}
.kpi-head .icon{width:17px;height:17px;}
.kpi-k{font-family:var(--f-mono);font-size:10px;text-transform:uppercase;letter-spacing:.09em;color:var(--muted);font-weight:600;}
.kpi-v{font-family:var(--f-display);font-size:25px;font-weight:600;letter-spacing:-.02em;color:var(--ink);line-height:1.1;}
.kpi-s{font-size:11.5px;color:var(--muted);margin-top:3px;}
/* panels */
.split{display:grid;grid-template-columns:1fr 1fr;gap:14px;}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);padding:20px;box-shadow:var(--shadow-sm);}
.panel-h{display:flex;align-items:center;gap:9px;margin-bottom:12px;}
.panel-h .icon{width:18px;height:18px;color:var(--muted);} .panel-h h3{margin:0;font-family:var(--f-display);font-size:16px;font-weight:600;letter-spacing:-.01em;}
.quick{display:flex;flex-direction:column;gap:11px;margin:6px 0;}
.quick-i{display:flex;align-items:center;gap:11px;font-size:13px;color:var(--ink-2);}
.quick-i .qn{font-family:var(--f-display);font-size:18px;font-weight:600;min-width:52px;color:var(--ink);}
.cta-row{display:flex;flex-wrap:wrap;gap:9px;margin-top:16px;}
.cta{display:inline-flex;align-items:center;gap:8px;border:0;background:var(--ink);color:var(--bg);border-radius:var(--r-sm);padding:11px 15px;font-weight:600;cursor:pointer;font-size:13.5px;transition:.15s;}
.cta:hover{transform:translateY(-1px);filter:brightness(1.08);} .cta .icon{width:16px;height:16px;}
.cta.ghost{background:var(--panel-2);color:var(--ink);border:1px solid var(--line);} .cta.ghost:hover{border-color:color-mix(in srgb,var(--ink) 24%, var(--line));filter:none;}
.meter{margin:12px 0;} .meter-top{display:flex;justify-content:space-between;font-size:12.5px;margin-bottom:6px;color:var(--ink-2);} .meter-top b{font-family:var(--f-mono);font-weight:600;}
.bar{height:7px;border-radius:999px;background:var(--inset);overflow:hidden;}
.bar>span{display:block;height:100%;border-radius:999px;background:var(--ac,var(--accent));transition:width .9s cubic-bezier(.2,.75,.2,1);}
/* badges + leds */
.badge{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:4px 11px;font-weight:600;font-size:11.5px;background:var(--acw);color:var(--aci);border:1px solid color-mix(in srgb,var(--ac) 26%, transparent);}
.badge .bd{width:6px;height:6px;border-radius:50%;background:var(--ac);}
.chip{font-family:var(--f-mono);background:var(--panel-2);border:1px solid var(--line);border-radius:8px;padding:4px 9px;font-size:11px;color:var(--ink-2);}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:9px;}
/* component blocks */
.blocks{display:grid;grid-template-columns:repeat(4,1fr);gap:13px;}
.block{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);padding:16px;box-shadow:var(--shadow-sm);}
.block-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:11px;}
.block-ic{width:34px;height:34px;border-radius:10px;background:var(--acw);color:var(--aci);display:grid;place-items:center;} .block-ic .icon{width:18px;height:18px;}
.block-sc{font-family:var(--f-display);font-size:18px;font-weight:600;color:var(--aci);}
.block h4{margin:0 0 8px;font-size:14px;font-weight:600;}
.minitrack{height:6px;border-radius:999px;background:var(--inset);overflow:hidden;position:relative;margin:8px 0 10px;}
.minitrack>span{position:absolute;left:0;top:0;bottom:0;border-radius:999px;background:var(--ac);transition:width .9s cubic-bezier(.2,.75,.2,1);}
.minitrack .thr{position:absolute;top:-2px;bottom:-2px;width:1.5px;background:var(--ink-2);opacity:.4;}
.block .phrase{font-size:12.5px;color:var(--ink-2);margin:0 0 9px;}
/* timeline */
.timeline{width:100%;height:auto;display:block;}
.ax{font-family:var(--f-mono);font-size:10px;fill:var(--muted);}
.legend{display:flex;gap:18px;flex-wrap:wrap;margin:12px 2px 2px;font-size:11.5px;color:var(--muted);font-family:var(--f-mono);}
.legend i.lg{display:inline-block;width:16px;height:3px;border-radius:2px;vertical-align:middle;margin-right:6px;}
.legend i.lg.dash{background:repeating-linear-gradient(90deg,currentColor 0 4px,transparent 4px 8px)!important;color:var(--muted);}
.tl-steps{display:flex;flex-direction:column;gap:10px;margin-top:16px;}
.tl-step{display:flex;gap:11px;align-items:center;font-size:13.5px;color:var(--ink-2);}
.tl-node{width:9px;height:9px;border-radius:50%;background:var(--ac,var(--accent));flex:none;box-shadow:0 0 0 4px var(--acw,var(--inset));}
.tl-hour{font-family:var(--f-mono);font-weight:600;min-width:44px;}
/* alert explanation */
.alertcard{display:flex;gap:15px;background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--ac,var(--accent));border-radius:var(--r);padding:20px;box-shadow:var(--shadow-sm);}
.alertcard-ic{width:38px;height:38px;border-radius:11px;background:var(--acw);color:var(--aci);display:grid;place-items:center;flex:none;} .alertcard-ic .icon{width:20px;height:20px;}
.alertcard h3{margin:0 0 10px;font-family:var(--f-display);font-size:15px;font-weight:600;}
.alertcard ul{margin:0;padding-left:18px;color:var(--ink-2);} .alertcard li{margin:7px 0;}
/* generic cards / tables */
.grid{display:grid;gap:13px;} .cards4{grid-template-columns:repeat(4,1fr);} .cards3{grid-template-columns:repeat(3,1fr);} .cards2{grid-template-columns:repeat(2,1fr);}
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);padding:16px;box-shadow:var(--shadow-sm);}
.card .kicker{font-family:var(--f-mono);font-size:10px;text-transform:uppercase;letter-spacing:.09em;color:var(--muted);font-weight:600;}
.card h3{margin:0 0 4px;font-family:var(--f-display);font-size:15px;font-weight:600;}
.score{font-family:var(--f-display);font-size:26px;font-weight:600;letter-spacing:-.02em;margin-top:4px;color:var(--ink);}
.phrase{font-size:12.5px;color:var(--ink-2);margin:8px 0 0;}
.subtabs{display:flex;gap:7px;flex-wrap:wrap;margin:4px 0 16px;}
.subtab{border:1px solid var(--line);background:var(--panel);color:var(--ink-2);border-radius:999px;padding:8px 14px;font-weight:600;cursor:pointer;font-size:12.5px;transition:.15s;}
.subtab:hover{border-color:color-mix(in srgb,var(--ink) 22%, var(--line));color:var(--ink);} .subtab.active{background:var(--ink);color:var(--bg);border-color:var(--ink);}
.frame-wrap{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);overflow:hidden;box-shadow:var(--shadow);}
iframe{width:100%;height:70vh;min-height:540px;border:0;display:block;background:#fff;}
.links{display:flex;flex-wrap:wrap;gap:8px;} .links a{font-family:var(--f-mono);font-size:12px;background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:8px 12px;color:var(--ink-2);} .links a:hover{border-color:color-mix(in srgb,var(--ink) 22%, var(--line));text-decoration:none;color:var(--ink);}
table{width:100%;border-collapse:collapse;font-size:13px;}
thead th{position:sticky;top:0;background:var(--panel-2);}
th,td{border-bottom:1px solid var(--line);padding:11px 13px;text-align:left;vertical-align:top;}
th{font-family:var(--f-mono);font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:600;}
td.num{font-family:var(--f-mono);font-variant-numeric:tabular-nums;}
tbody tr:hover{background:var(--panel-2);}
.table-wrap{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);overflow:auto;box-shadow:var(--shadow-sm);}
/* heat */
.heat-hero{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:24px;align-items:center;border:1px solid var(--line);border-radius:var(--r-lg);padding:26px 28px;box-shadow:var(--shadow);background:var(--panel);position:relative;overflow:hidden;}
.heat-hero:before{content:"";position:absolute;inset:0;background:radial-gradient(560px 240px at 92% -30%, var(--acw,transparent), transparent);pointer-events:none;}
.heat-sun{width:104px;height:104px;display:block;color:var(--ac,var(--c-elevated));}
.heat-sun .core{fill:currentColor;}
.heat-sun .rays{transform-origin:52px 52px;animation:spin 30s linear infinite;}
.heat-sun .rays line{stroke:currentColor;stroke-width:3.4;stroke-linecap:round;opacity:.8;}
@keyframes spin{to{transform:rotate(360deg);}}
.heat-curve{width:100%;height:auto;display:block;}
.heat-advice{margin:0;padding-left:18px;color:var(--ink-2);} .heat-advice li{margin:7px 0;}
.heat-note{background:color-mix(in srgb,var(--c-watch) 9%, var(--panel));border:1px solid color-mix(in srgb,var(--c-watch) 30%, var(--line));border-left:3px solid var(--c-watch);border-radius:var(--r-sm);padding:12px 14px;font-size:12.5px;color:var(--ink-2);margin-top:16px;}
.heat-strip{display:flex;align-items:center;gap:15px;border:1px solid var(--line);border-left:3px solid var(--ac,var(--c-elevated));border-radius:var(--r);padding:14px 18px;margin:18px 0;box-shadow:var(--shadow-sm);background:var(--panel);}
.heat-strip .heat-strip-ic{width:42px;height:42px;border-radius:11px;background:var(--acw);color:var(--aci);display:grid;place-items:center;flex:none;} .heat-strip .heat-strip-ic .icon{width:23px;height:23px;}
.heat-strip-main{flex:1;min-width:0;} .heat-strip-main strong{font-family:var(--f-display);font-size:15px;font-weight:600;}
.heat-strip-num{font-family:var(--f-display);font-size:26px;font-weight:600;letter-spacing:-.02em;color:var(--aci);}
/* map */
.map-bar{display:flex;flex-wrap:wrap;gap:11px;align-items:center;margin-bottom:14px;}
.map-pick{display:flex;align-items:center;gap:8px;background:var(--panel);border:1px solid var(--line);border-radius:var(--r-sm);padding:7px 12px;box-shadow:var(--shadow-sm);}
.map-pick label{display:flex;align-items:center;gap:6px;color:var(--muted);font-family:var(--f-mono);font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;} .map-pick .icon{width:15px;height:15px;}
#locsel{border:0;font-size:13.5px;font-weight:600;color:var(--ink);background:transparent;max-width:230px;cursor:pointer;}
.map-toggle{display:flex;align-items:center;gap:8px;font-size:12.5px;font-weight:500;color:var(--ink-2);background:var(--panel);border:1px solid var(--line);border-radius:var(--r-sm);padding:8px 12px;box-shadow:var(--shadow-sm);cursor:pointer;}
.map-legend{display:flex;gap:13px;flex-wrap:wrap;margin-left:auto;font-family:var(--f-mono);font-size:11px;color:var(--muted);}
.map-legend i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px;vertical-align:middle;}
.map-wrap{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:14px;}
.mvmap{height:66vh;min-height:440px;border-radius:var(--r);overflow:hidden;border:1px solid var(--line);box-shadow:var(--shadow);z-index:0;background:var(--inset);}
.map-detail{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);padding:18px;box-shadow:var(--shadow);max-height:66vh;overflow:auto;}
.map-fallback{display:grid;place-items:center;height:100%;color:var(--muted);padding:24px;text-align:center;}
.md-head{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;border-left:3px solid var(--ac,var(--accent));padding-left:12px;margin-bottom:12px;}
.md-head h3{margin:2px 0 0;font-family:var(--f-display);font-size:18px;font-weight:600;}
.md-score{display:flex;justify-content:space-between;align-items:center;gap:10px;margin:4px 0 12px;}
.spark{display:block;}
.dl{display:flex;justify-content:space-between;font-size:13px;padding:8px 0;border-bottom:1px solid var(--line-2);} .dl span{color:var(--muted);} .dl strong{font-family:var(--f-mono);font-weight:600;}
.md-sig{margin:8px 0 0;padding-left:18px;color:var(--ink-2);font-size:12.5px;} .md-sig li{margin:5px 0;}
.leaflet-container{font:inherit;background:var(--inset);}
[data-theme="dark"] .leaflet-tile{filter:brightness(.78) contrast(1.05) hue-rotate(178deg) invert(.92);}
footer{max-width:1240px;margin:26px auto 44px;padding:14px 24px 0;color:var(--muted);font-family:var(--f-mono);font-size:11px;border-top:1px solid var(--line);}
footer code{background:var(--panel-2);border-radius:6px;padding:2px 6px;}
@media(prefers-reduced-motion:reduce){*{animation-duration:.001ms!important;transition-duration:.001ms!important;} .live-dot:after,.heat-sun .rays{animation:none;}}
@media(max-width:980px){.kpis{grid-template-columns:1fr 1fr;}.blocks{grid-template-columns:1fr 1fr;}.cards4{grid-template-columns:1fr 1fr;}.cards3{grid-template-columns:1fr;}.split{grid-template-columns:1fr;}.hero-top,.heat-hero{grid-template-columns:1fr;}.hero-dial{justify-self:start;}.map-wrap{grid-template-columns:1fr;}.mvmap{height:52vh;}.map-detail{max-height:none;}.map-legend{margin-left:0;}}
@media(max-width:560px){.kpis,.blocks,.cards4{grid-template-columns:1fr;}.status-chip .st-k{display:none;}}
</style>
</head>
<body>
<header class="cmd">
  <div class="cmd-wrap">
    <div class="brand">
      <div class="mark"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 17a8 8 0 0 1 16 0"/><path d="M12 17l4.5-4.5"/><circle cx="12" cy="17" r="1.4" fill="currentColor" stroke="none"/></svg></div>
      <div><h1>MeteoVoid Belgique</h1><p>Veille de bascule · prototype ORI-C</p></div>
    </div>
    <div class="cmd-right">
      <div class="status-chip"><span class="live-dot"></span><div><div class="st-k">run</div><div class="st-v" id="stamp">__GENERATED_AT__</div></div></div>
      <button class="tgl" id="themetgl" aria-label="Basculer le thème" title="Basculer clair / sombre"></button>
    </div>
  </div>
  <nav class="tabs" id="tabs">
    <button class="tab active" data-view="simple">Vue simple</button>
    <button class="tab" data-view="operational">Vue opérationnelle</button>
    <button class="tab" data-view="heat">Chaleur</button>
    <button class="tab" data-view="map">Carte</button>
    <button class="tab" data-view="expert">Vue expert</button>
    <a class="tab" href="europe.html" style="text-decoration:none">Europe</a>
    <a class="tab" href="methodology.html" style="text-decoration:none">Méthodologie</a>
  </nav>
</header>
<main>
  <div class="disclaimer" id="disclaimer"></div>
  <section class="view active" id="view-simple"></section>
  <section class="view" id="view-operational"></section>
  <section class="view" id="view-heat"></section>
  <section class="view" id="view-map"></section>
  <section class="view" id="view-expert"></section>
</main>
<footer id="footer"></footer>
<script id="bootstrap" type="application/json">__BOOTSTRAP__</script>
<script>
const FALLBACK = JSON.parse(document.getElementById('bootstrap').textContent);
const esc=(s)=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const num=(v,d='n/a')=> (v==null||v==='')?d:(typeof v==='number'? (Number.isInteger(v)?v:v.toFixed(2)) : v);
const pct=(v)=> v==null? '—' : Math.round(Math.max(0,Math.min(1,v))*100)+'%';
const cls=(m)=> (m&&m.class)||'calm';
const clamp01=(v)=>Math.max(0,Math.min(1,(typeof v==='number'?v:0)||0));
const cssvar=(n)=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const colorOf=(c)=> cssvar('--c-'+(c||'info'))||'#3a7ec4';
const inkOf=(c)=> colorOf(c);
let GID=0;

const ICONS={
  gauge:'<path d="M4 18a8 8 0 0 1 16 0"/><path d="M12 18l4.2-4.2"/><circle cx="12" cy="18" r="1.3" fill="currentColor" stroke="none"/>',
  shield:'<path d="M12 3l7 3v5c0 4.2-3 7.4-7 9-4-1.6-7-4.8-7-9V6l7-3z"/>',
  clock:'<circle cx="12" cy="12" r="8.2"/><path d="M12 8v4.3l3 1.8"/>',
  pin:'<path d="M12 21s-6-5.4-6-10a6 6 0 1 1 12 0c0 4.6-6 10-6 10z"/><circle cx="12" cy="11" r="2.2"/>',
  flame:'<path d="M12 3c2.2 3 5 4.2 5 8a5 5 0 0 1-10 0c0-2 .9-3.2 2-4.2.4 2 2 2.4 3 2.2-1-2-1.2-4 0-6z"/>',
  bolt:'<path d="M13 2 5 13h5l-1 9 9-12h-5l1-8z"/>',
  wind:'<path d="M3 8h10a2.6 2.6 0 1 0-2.6-2.6"/><path d="M3 12.5h14a2.6 2.6 0 1 1-2.6 2.6"/><path d="M3 16.5h7"/>',
  layers:'<path d="M12 3 3 8l9 5 9-5-9-5z"/><path d="M3.5 13 12 17.7 20.5 13"/>',
  eye:'<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>',
  flow:'<path d="M4 12h12"/><path d="M12.5 6.5 19 12l-6.5 5.5"/>',
  target:'<circle cx="12" cy="12" r="8.2"/><circle cx="12" cy="12" r="3.6"/><circle cx="12" cy="12" r=".9" fill="currentColor" stroke="none"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><circle cx="12" cy="7.8" r="1" fill="currentColor" stroke="none"/>',
  chart:'<path d="M4 19V5"/><path d="M4 19h16"/><path d="M7.5 15l3.2-4 3 2 4-5.5"/>',
  activity:'<path d="M3 12h4l2.5-7 5 14 2.5-7H21"/>',
  sun:'<circle cx="12" cy="12" r="4.2"/><path d="M12 2.5v2.4M12 19.1v2.4M4.3 4.3l1.7 1.7M18 18l1.7 1.7M2.5 12h2.4M19.1 12h2.4M4.3 19.7 6 18M18 6l1.7-1.7"/>',
  thermo:'<path d="M14 14.8V5a2 2 0 0 0-4 0v9.8a4 4 0 1 0 4 0z"/><path d="M12 9v6.5"/>',
  drop:'<path d="M12 3c3.2 4 5.5 6.7 5.5 10a5.5 5.5 0 1 1-11 0c0-3.3 2.3-6 5.5-10z"/>',
  alert:'<path d="M12 3 2 20h20L12 3z"/><path d="M12 10v4.5"/><circle cx="12" cy="17.4" r="1" fill="currentColor" stroke="none"/>',
  download:'<path d="M12 4v10"/><path d="M8 11l4 4 4-4"/><path d="M5 19h14"/>'
};
function icon(name){return `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]||ICONS.info}</svg>`;}
const SUN_T='<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4.2"/><path d="M12 2.5v2.4M12 19.1v2.4M4.3 4.3l1.7 1.7M18 18l1.7 1.7M2.5 12h2.4M19.1 12h2.4M4.3 19.7 6 18M18 6l1.7-1.7"/></svg>';
const MOON_T='<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z"/></svg>';

function bar(score,c){const w=Math.round(clamp01(score)*100);return `<div class="bar"><span class="ac-${c||'info'}" style="width:${w}%"></span></div>`;}

/* radial dial for quality-type readings (confidence) */
function dial(value,opts){opts=opts||{};
  const size=opts.size||186, sw=opts.sw||13, cx=size/2, r=(size-sw)/2-2, C=2*Math.PI*r, SPAN=.74;
  const v=clamp01(value), track=C*SPAN, gap=C-track, val=track*v;
  const c=opts.cls||'info', col=colorOf(c), gid='dl'+(GID++);
  const center=opts.center!=null?opts.center:Math.round(v*100);
  return `<svg class="dial" viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" role="img" aria-label="indicateur ${esc(center)}">
    <defs><linearGradient id="${gid}" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="${col}" stop-opacity=".35"/><stop offset="1" stop-color="${col}"/></linearGradient></defs>
    <g transform="rotate(133 ${cx} ${cx})">
      <circle cx="${cx}" cy="${cx}" r="${r}" fill="none" stroke="${cssvar('--inset')}" stroke-width="${sw}" stroke-linecap="round" stroke-dasharray="${track.toFixed(1)} ${gap.toFixed(1)}"/>
      <circle class="arc" cx="${cx}" cy="${cx}" r="${r}" fill="none" stroke="url(#${gid})" stroke-width="${sw}" stroke-linecap="round" stroke-dasharray="${val.toFixed(1)} ${(C-val).toFixed(1)}" data-arc="${val.toFixed(1)}" data-circ="${C.toFixed(1)}"/>
    </g>
    <text x="${cx}" y="${cx-2}" text-anchor="middle" class="gauge-num" style="font-size:34px;fill:var(--aci,${col})">${esc(center)}</text>
    ${opts.label?`<text x="${cx}" y="${cx+18}" text-anchor="middle" class="gauge-cap">${esc(opts.label)}</text>`:''}
    ${opts.sub?`<text x="${cx}" y="${cx+33}" text-anchor="middle" class="gauge-sub">${esc(opts.sub)}</text>`:''}
  </svg>`;}

function ring(value,c,size){size=size||58;const sw=6,cx=size/2,r=(size-sw)/2,C=2*Math.PI*r;
  const v=clamp01(value),off=C*(1-v),col=colorOf(c||'info');
  return `<svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" aria-hidden="true">
    <circle cx="${cx}" cy="${cx}" r="${r}" fill="none" stroke="${cssvar('--inset')}" stroke-width="${sw}"/>
    <circle class="arc" cx="${cx}" cy="${cx}" r="${r}" fill="none" stroke="${col}" stroke-width="${sw}" stroke-linecap="round" stroke-dasharray="${C.toFixed(1)}" stroke-dashoffset="${off.toFixed(1)}" data-off="${off.toFixed(1)}" data-circ="${C.toFixed(1)}" transform="rotate(-90 ${cx} ${cx})"/>
    <text x="${cx}" y="${cx+4}" text-anchor="middle" class="gauge-num" style="font-size:15px;fill:var(--aci,${col})">${Math.round(v*100)}</text>
  </svg>`;}

/* SIGNATURE: transition track — position of the system on the regime continuum */
const REGIMES=[{v:0.0,l:'Stable'},{v:0.45,l:'Latent'},{v:0.66,l:'Transition'},{v:0.86,l:'Bascule'}];
function transitionTrack(value,c,opts){opts=opts||{};
  const W=opts.w||760,H=opts.h||72,padX=16,top=22,th=12,thr=0.66;
  const v=clamp01(value),col=colorOf(c||'info');
  const x=t=>padX+(W-2*padX)*clamp01(t);
  const gid='tt'+(GID++);
  const stops=['calm','info','watch','elevated','high','danger'].map((k,i)=>`<stop offset="${(i/5*100).toFixed(0)}%" stop-color="${colorOf(k)}"/>`).join('');
  const ticks=REGIMES.map(rg=>rg.v>0?`<line x1="${x(rg.v).toFixed(1)}" y1="${top}" x2="${x(rg.v).toFixed(1)}" y2="${top+th}" stroke="${cssvar('--panel')}" stroke-width="2"/>`:'').join('');
  const labs=REGIMES.map((rg,i)=>{const nx=i===0?x(0.0):(i===REGIMES.length-1?x(0.93):x(rg.v));const anchor=i===0?'start':(i===REGIMES.length-1?'end':'middle');const on=(v>=rg.v && (REGIMES[i+1]?v<REGIMES[i+1].v:true))?' on':'';return `<text x="${nx.toFixed(1)}" y="${top+th+20}" text-anchor="${anchor}" class="tt-lab${on}">${rg.l}</text>`;}).join('');
  const mx=x(v);
  return `<svg class="transition-track" viewBox="0 0 ${W} ${H}" role="img" aria-label="position du système, ${Math.round(v*100)} sur 100 vers la bascule">
    <defs><linearGradient id="${gid}" x1="0" x2="1" y1="0" y2="0">${stops}</linearGradient></defs>
    <rect class="tt-base" x="${padX}" y="${top}" width="${(W-2*padX).toFixed(1)}" height="${th}" rx="${th/2}"/>
    <rect class="tt-grad" x="${padX}" y="${top}" width="${(W-2*padX).toFixed(1)}" height="${th}" rx="${th/2}" fill="url(#${gid})"/>
    ${ticks}
    <line class="tt-thr" x1="${x(thr).toFixed(1)}" y1="${top-9}" x2="${x(thr).toFixed(1)}" y2="${top+th+5}"/>
    <text class="tt-thr-cap" x="${x(thr).toFixed(1)}" y="${top-13}" text-anchor="middle">seuil de bascule</text>
    ${labs}
    <g class="tt-mark" transform="translate(${mx.toFixed(1)} 0)" style="transform:translateX(${padX}px)" data-tx="${mx.toFixed(1)}">
      <line x1="0" y1="${top-5}" x2="0" y2="${top+th+5}" stroke="${col}" stroke-width="2.5"/>
      <circle cx="0" cy="${top+th/2}" r="6.5" fill="${col}" stroke="${cssvar('--panel')}" stroke-width="2.5"/>
    </g>
  </svg>`;}

function smoothPath(pts){if(pts.length<2)return pts.length?`M ${pts[0][0]} ${pts[0][1]}`:'';
  let d=`M ${pts[0][0].toFixed(1)} ${pts[0][1].toFixed(1)}`;
  for(let i=0;i<pts.length-1;i++){const p0=pts[i-1]||pts[i],p1=pts[i],p2=pts[i+1],p3=pts[i+2]||p2;
    const c1x=p1[0]+(p2[0]-p0[0])/6,c1y=p1[1]+(p2[1]-p0[1])/6,c2x=p2[0]-(p3[0]-p1[0])/6,c2y=p2[1]-(p3[1]-p1[1])/6;
    d+=` C ${c1x.toFixed(1)} ${c1y.toFixed(1)}, ${c2x.toFixed(1)} ${c2y.toFixed(1)}, ${p2[0].toFixed(1)} ${p2[1].toFixed(1)}`;}
  return d;}

function animateArcs(){try{requestAnimationFrame(()=>{
  document.querySelectorAll('.dial .arc, svg .arc').forEach(el=>{
    const arc=el.getAttribute('data-arc'),off=el.getAttribute('data-off'),circ=parseFloat(el.getAttribute('data-circ'));
    if(arc!=null){el.style.strokeDasharray='0 '+circ;requestAnimationFrame(()=>{el.style.strokeDasharray=arc+' '+(circ-parseFloat(arc));});}
    else if(off!=null){el.style.strokeDashoffset=circ;requestAnimationFrame(()=>{el.style.strokeDashoffset=off;});}
  });
  document.querySelectorAll('.tt-mark').forEach(el=>{const tx=el.getAttribute('data-tx');el.style.transform='translateX(16px)';requestAnimationFrame(()=>{el.style.transform='translateX('+tx+'px)';});});
});}catch(e){}}

function animateCounts(root){(root||document).querySelectorAll('[data-count]').forEach(el=>{
  const target=parseFloat(el.getAttribute('data-count')); if(isNaN(target))return;
  const dec=parseInt(el.getAttribute('data-dec')||'0',10), suf=el.getAttribute('data-suffix')||'';
  const dur=700,t0=performance.now();
  function step(t){const k=Math.min(1,(t-t0)/dur),e=1-Math.pow(1-k,3),val=target*e;el.textContent=val.toFixed(dec)+suf;if(k<1)requestAnimationFrame(step);}
  requestAnimationFrame(step);
});}

/* ---------------- simple view ---------------- */
function renderSimple(vm){
  const s=vm.simple||{},op=s.operational_level||{},conf=s.confidence||{},win=s.critical_window||{},zone=s.main_zone||{},o=vm.operational||{};
  const c=cls(op),tc=cls(o.transition_level);
  const kpi=(ic,ac,k,v,sub)=>`<div class="kpi ${ac}"><div class="kpi-head">${icon(ic)}<span class="kpi-k">${esc(k)}</span></div><div class="kpi-v">${v}</div><div class="kpi-s">${esc(sub)}</div></div>`;
  return `
  <section class="hero ac-${tc}">
    <div class="hero-top">
      <div>
        <div class="hero-led ac-${c}"><span class="led"></span><span class="led-k">État opérationnel · non officiel</span></div>
        <h1 class="hero-level ac-${c}">${esc(op.label)}</h1>
        <p class="hero-syn">${esc(s.synthesis)}</p>
        ${(s.headline_signals&&s.headline_signals.length)?'<div class="hero-tags">'+s.headline_signals.map(x=>`<span class="chip">${esc(x)}</span>`).join('')+'</div>':''}
      </div>
      <div class="hero-dial ac-${cls(conf)}">${dial(conf.score,{cls:cls(conf),center:pct(conf.score).replace('%',''),label:'confiance',sub:esc(conf.label)})}</div>
    </div>
    <div class="track-zone ac-${tc}">
      <div class="track-head"><span class="tk">Distance à la bascule · void collapse</span><span class="tv">${num(o.void_collapse_signal)} · ${esc((o.transition_level||{}).label)}</span></div>
      ${transitionTrack(o.void_collapse_signal,tc)}
    </div>
  </section>
  <div class="kpis">
    ${kpi('gauge','ac-'+c,'Score modèle',num(s.model_score),'signal MeteoVoid (0–1)')}
    ${kpi('shield','ac-'+cls(conf),'Confiance du run',pct(conf.score),esc(conf.label)+' · qualité + corroboration')}
    ${kpi('clock','ac-info','Fenêtre critique',esc(win.label),'heure locale '+((vm.meta&&vm.meta.timezone)||''))}
    ${kpi('pin','ac-info','Zone principale',esc(zone.name),zone.top_station||'—')}
  </div>
  ${heatStrip(vm)}
  <div class="split">
    <div class="panel">
      <div class="panel-h">${icon('info')}<h3>Ce qu'il faut retenir</h3></div>
      <p class="lead">${esc(s.reason||s.public_wording||'')}</p>
      <div class="quick">
        <div class="quick-i"><span class="badge ac-${cls(s.severity)}"><span class="bd"></span>${esc((s.severity||{}).label)}</span><span>sévérité modèle dominante</span></div>
        <div class="quick-i"><span class="qn txt-${tc}">${num(o.void_collapse_signal)}</span><span>signal de bascule — ${esc((o.transition_level||{}).label)}</span></div>
        <div class="quick-i"><span class="qn">${esc(win.start_hour||'—')}</span><span>${win.status==='available'?('fenêtre jusqu’à '+esc(win.end_hour)+', pic '+esc(win.peak_hour)):'pas de fenêtre sensible identifiée'}</span></div>
      </div>
      <div class="cta-row"><button class="cta" onclick="go('operational')">Analyse complète ${icon('flow')}</button><button class="cta ghost" onclick="go('map')">Ouvrir la carte ${icon('pin')}</button></div>
    </div>
    <div class="panel">
      <div class="panel-h">${icon('shield')}<h3>Confiance du signal</h3></div>
      ${(conf.factors||[]).map(f=>`<div class="meter ac-info"><div class="meter-top"><span>${esc(f.name)}</span><b>${pct(f.value)}</b></div>${bar(f.value,'info')}</div>`).join('')}
      <p class="muted" style="margin-top:10px">Score global ${pct(conf.score)} (${esc(conf.label)}) : qualité des sources, cohérence interne, confirmation externe et cohérence spatiale.</p>
    </div>
  </div>`;
}

/* ---------------- operational view ---------------- */
function renderOperational(vm){
  const o=vm.operational||{},blocks=o.blocks||[],tl=o.timeline||{},ax=o.alert_explanation||{};
  const BI={charge:'flame',declencheur:'bolt',organisation:'wind',couvercle:'layers',observation:'eye',amont:'flow',void:'target'};
  const thr=0.66;
  const blockCards=blocks.map(b=>{const c=cls(b.level);const w=Math.round(clamp01(b.score)*100);
    return `<div class="block ac-${c}">
      <div class="block-top"><div class="block-ic">${icon(BI[b.key]||'chart')}</div><div class="block-sc">${num(b.score)}</div></div>
      <h4>${esc(b.title)}</h4>
      <div class="minitrack"><span style="width:${w}%"></span><i class="thr" style="left:${thr*100}%"></i></div>
      <div><span class="badge ac-${c}"><span class="bd"></span>${esc((b.level||{}).label)}</span></div>
      <p class="phrase">${esc(b.phrase)}</p>
      ${(b.drivers&&b.drivers.length)?'<div class="chips">'+b.drivers.map(d=>`<span class="chip">${esc(d)}</span>`).join('')+'</div>':''}
    </div>`;}).join('');
  const tc=cls(o.transition_level);
  return `
  <section class="hero ac-${tc}">
    <div class="hero-top">
      <div>
        <div class="hero-led ac-${tc}"><span class="led"></span><span class="led-k">Convective transition · jauge de bascule</span></div>
        <h1 class="hero-level ac-${tc}">${esc((o.transition_level||{}).label)}</h1>
        <p class="hero-syn">${esc(o.interpretation)}</p>
      </div>
      <div class="hero-dial ac-${tc}">${dial(o.void_collapse_signal,{cls:tc,center:num(o.void_collapse_signal),label:'void collapse',sub:'signal 0–1'})}</div>
    </div>
    <div class="track-zone ac-${tc}">
      <div class="track-head"><span class="tk">Continuum de régime</span><span class="tv">${num(o.void_collapse_signal)}</span></div>
      ${transitionTrack(o.void_collapse_signal,tc)}
    </div>
  </section>
  <div class="section-title">Jauge de bascule · 7 composantes</div>
  <div class="blocks">${blockCards}</div>
  <div class="section-title">Timeline horaire</div>
  <div class="panel">
    ${renderTimelineSvg(tl)}
    <div class="legend"><span><i class="lg" style="background:${colorOf('info')}"></i>score modèle (max horaire)</span><span><i class="lg dash"></i>fenêtre sensible</span><span><i class="lg" style="background:${colorOf('danger')}"></i>pic</span></div>
    <div class="tl-steps">${(tl.narrative||[]).map(n=>{const k=({watch:'watch',elevated:'elevated',peak:'danger',end:'info',calm:'calm'}[n.kind]||'info');return `<div class="tl-step ac-${k}"><span class="tl-node"></span><span class="tl-hour txt-${k}">${esc(n.hour)}</span><span>${esc(n.text)}</span></div>`;}).join('')}</div>
    <p class="muted" style="margin-top:10px">${esc(tl.summary||'')}</p>
  </div>
  <div class="section-title">Pourquoi cette lecture ?</div>
  <div class="alertcard ac-${cls((vm.simple||{}).operational_level)}">
    <div class="alertcard-ic">${icon('alert')}</div>
    <div><h3>${esc(ax.title)}</h3><ul>${(ax.bullets||[]).map(b=>`<li>${esc(b)}</li>`).join('')}</ul></div>
  </div>`;
}

function renderTimelineSvg(tl){
  const hours=(tl.hours||[]).filter(h=>h.max_score!=null);
  if(!hours.length) return '<p class="muted">Timeline horaire indisponible pour ce run.</p>';
  const W=1000,H=210,padX=38,padT=22,padB=30,n=hours.length;
  const x=i=>padX+(W-2*padX)*(n<=1?0.5:i/(n-1));
  const y=v=>(H-padB)-(H-padT-padB)*clamp01(v);
  const pts=hours.map((h,i)=>[x(i),y(h.max_score)]);
  const line=smoothPath(pts);
  const area=line+` L ${x(n-1).toFixed(1)} ${H-padB} L ${x(0).toFixed(1)} ${H-padB} Z`;
  const grid=[0,.25,.5,.75,1].map(g=>`<line x1="${padX}" y1="${y(g).toFixed(1)}" x2="${W-padX}" y2="${y(g).toFixed(1)}" stroke="${cssvar('--line-2')}"/>`).join('');
  const thr=`<line x1="${padX}" y1="${y(.66).toFixed(1)}" x2="${W-padX}" y2="${y(.66).toFixed(1)}" stroke="${colorOf('watch')}" stroke-dasharray="4 4" opacity=".7"/><text x="${(W-padX).toFixed(1)}" y="${(y(.66)-5).toFixed(1)}" text-anchor="end" class="ax">seuil élevé</text>`;
  const markers=(tl.markers||[]).map(m=>{const idx=hours.findIndex(h=>h.time===m.time);if(idx<0)return '';const px=x(idx);const col=m.kind==='peak'?colorOf('danger'):cssvar('--muted');
    return `<line x1="${px.toFixed(1)}" y1="${padT}" x2="${px.toFixed(1)}" y2="${(H-padB).toFixed(1)}" stroke="${col}" stroke-dasharray="3 4" opacity=".75"/><text x="${px.toFixed(1)}" y="${(padT-6).toFixed(1)}" text-anchor="middle" class="ax" style="fill:${col}">${esc(m.hour)}</text>`;}).join('');
  const dots=hours.map((h,i)=>`<circle cx="${x(i).toFixed(1)}" cy="${y(h.max_score).toFixed(1)}" r="${(h.class==='danger'||h.class==='high')?4:3}" fill="${colorOf(h.class)}" stroke="${cssvar('--panel')}" stroke-width="1.5"/>`).join('');
  const ticks=hours.map((h,i)=>(i%3===0)?`<text x="${x(i).toFixed(1)}" y="${H-8}" text-anchor="middle" class="ax">${esc(h.hour)}</text>`:'').join('');
  return `<svg class="timeline" viewBox="0 0 ${W} ${H}" role="img" aria-label="Timeline horaire du score modèle">
    <defs><linearGradient id="tlfill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${colorOf('info')}" stop-opacity=".24"/><stop offset="1" stop-color="${colorOf('info')}" stop-opacity="0"/></linearGradient></defs>
    ${grid}${thr}${markers}
    <path d="${area}" fill="url(#tlfill)"/>
    <path d="${line}" fill="none" stroke="${colorOf('info')}" stroke-width="2.6" stroke-linejoin="round" stroke-linecap="round"/>
    ${dots}${ticks}
  </svg>`;
}

/* ---------------- heat view ---------------- */
function heatStrip(vm){
  const h=vm.heat||{}; if(!h.notable) return '';
  const c=cls(h.level),t=h.max_temperature_c,hx=h.max_humidex;
  const sub=[h.peak_hour&&h.peak_hour!=='—'?('pic vers '+esc(h.peak_hour)):'',hx!=null?('humidex jusqu’à '+Math.round(hx)):''].filter(Boolean).join(' · ');
  return `<div class="heat-strip ac-${c}">
    <div class="heat-strip-ic">${icon('sun')}</div>
    <div class="heat-strip-main"><strong class="txt-${c}">${esc((h.level||{}).label)}</strong><div class="muted">${esc(sub||'chaleur notable sur le réseau')}</div></div>
    <div class="heat-strip-num">${t!=null?(t.toFixed(0)+' °C'):'—'}</div>
    <button class="cta ghost" onclick="go('heat')">Détail ${icon('flow')}</button>
  </div>`;
}

function renderHeatCurve(timeline){
  const pts=(timeline||[]).filter(p=>p.t!=null);
  if(pts.length<2) return '<p class="muted">Courbe de température indisponible pour ce run.</p>';
  const W=1000,H=230,padX=44,padT=24,padB=30,n=pts.length;
  const temps=pts.map(p=>p.t),hxs=pts.map(p=>p.hx).filter(v=>v!=null);
  const lo=Math.floor(Math.min(...temps,...hxs)-2),hi=Math.ceil(Math.max(...temps,...hxs)+2),span=Math.max(1,hi-lo);
  const x=i=>padX+(W-2*padX)*(n<=1?0.5:i/(n-1));
  const y=v=>(H-padB)-(H-padT-padB)*((v-lo)/span);
  const tPts=pts.map((p,i)=>[x(i),y(p.t)]),tLine=smoothPath(tPts);
  const area=tLine+` L ${x(n-1).toFixed(1)} ${H-padB} L ${x(0).toFixed(1)} ${H-padB} Z`;
  const hxPts=pts.map((p,i)=>p.hx!=null?[x(i),y(p.hx)]:null).filter(Boolean),hxLine=hxPts.length>1?smoothPath(hxPts):'';
  const gl=[lo,Math.round((lo+hi)/2),hi];
  const grid=gl.map(g=>`<line x1="${padX}" y1="${y(g).toFixed(1)}" x2="${W-padX}" y2="${y(g).toFixed(1)}" stroke="${cssvar('--line-2')}"/><text x="${padX-9}" y="${(y(g)+4).toFixed(1)}" text-anchor="end" class="ax">${g}°</text>`).join('');
  const peakIdx=temps.indexOf(Math.max(...temps));
  const peak=`<line x1="${x(peakIdx).toFixed(1)}" y1="${padT}" x2="${x(peakIdx).toFixed(1)}" y2="${(H-padB).toFixed(1)}" stroke="${colorOf('high')}" stroke-dasharray="3 4" opacity=".7"/><text x="${x(peakIdx).toFixed(1)}" y="${(padT-6).toFixed(1)}" text-anchor="middle" class="ax" style="fill:${colorOf('high')}">${esc(pts[peakIdx].h)}</text>`;
  const dots=pts.map((p,i)=>`<circle cx="${x(i).toFixed(1)}" cy="${y(p.t).toFixed(1)}" r="3" fill="${colorOf('elevated')}" stroke="${cssvar('--panel')}" stroke-width="1.4"/>`).join('');
  const ticks=pts.map((p,i)=>(i%3===0||i===n-1)?`<text x="${x(i).toFixed(1)}" y="${H-8}" text-anchor="middle" class="ax">${esc(p.h)}</text>`:'').join('');
  return `<svg class="heat-curve" viewBox="0 0 ${W} ${H}" role="img" aria-label="Courbe horaire de température et humidex">
    <defs><linearGradient id="heatfill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${colorOf('elevated')}" stop-opacity=".24"/><stop offset="1" stop-color="${colorOf('elevated')}" stop-opacity="0"/></linearGradient></defs>
    ${grid}${peak}
    <path d="${area}" fill="url(#heatfill)"/>
    ${hxLine?`<path d="${hxLine}" fill="none" stroke="${colorOf('danger')}" stroke-width="2" stroke-dasharray="5 4" stroke-linecap="round" opacity=".8"/>`:''}
    <path d="${tLine}" fill="none" stroke="${colorOf('elevated')}" stroke-width="2.6" stroke-linejoin="round" stroke-linecap="round"/>
    ${dots}${ticks}
  </svg>`;
}

function renderHeat(vm){
  const h=vm.heat||{},c=cls(h.level);
  const sun=`<svg class="heat-sun" viewBox="0 0 104 104" role="img" aria-label="chaleur">
    <g class="rays">
      <line x1="52" y1="26" x2="52" y2="15"/><line x1="71" y1="33" x2="78" y2="26"/>
      <line x1="78" y1="52" x2="89" y2="52"/><line x1="71" y1="71" x2="78" y2="78"/>
      <line x1="52" y1="78" x2="52" y2="89"/><line x1="33" y1="71" x2="26" y2="78"/>
      <line x1="26" y1="52" x2="15" y2="52"/><line x1="33" y1="33" x2="26" y2="26"/>
    </g><circle class="core" cx="52" cy="52" r="16"/></svg>`;
  const tile=(ic,k,v,sub,dec,suf)=>`<div class="kpi ac-${c}"><div class="kpi-head">${icon(ic)}<span class="kpi-k">${esc(k)}</span></div><div class="kpi-v"><span ${v!=null?`data-count="${v}" data-dec="${dec||0}" data-suffix="${esc(suf||'')}"`:''}>${v!=null?'0'+esc(suf||''):'—'}</span></div><div class="kpi-s">${esc(sub)}</div></div>`;
  const hot=(h.hottest||[]).map(s=>`<tr><td><strong>${esc(s.name)}</strong><div class="muted">${esc(regionLabel(s.region))}</div></td><td><span class="badge ac-${cls(s.level)}"><span class="bd"></span>${esc((s.level||{}).label)}</span></td><td class="num">${s.temperature_c!=null?s.temperature_c.toFixed(1)+' °C':'—'}</td><td class="num">${s.humidex!=null?Math.round(s.humidex):'—'}</td><td class="num">${s.dew_point_c!=null?s.dew_point_c.toFixed(1)+' °C':'—'}</td></tr>`).join('');
  return `
  <section class="heat-hero ac-${c}">
    <div>
      <div class="hero-led ac-${c}"><span class="led"></span><span class="led-k">Confort thermique · chaleur</span></div>
      <h1 class="hero-level ac-${c}">${esc((h.level||{}).label)}</h1>
      <p class="hero-syn">${h.peak_hour&&h.peak_hour!=='—'?('Pic de chaleur attendu vers '+esc(h.peak_hour)+'. '):''}Lecture indépendante du risque convectif.</p>
    </div>
    <div>${sun}</div>
  </section>
  <div class="kpis">
    ${tile('thermo','Température max',h.max_temperature_c,'maximum réseau',0,' °C')}
    ${tile('sun','Humidex',h.max_humidex,'ressenti chaleur + humidité',0,'')}
    ${tile('drop','Point de rosée',h.max_dew_point_c,'humidité de l’air',0,' °C')}
    ${tile('layers','Humidité relative',h.max_humidity_pct,'maximum réseau',0,' %')}
  </div>
  <div class="section-title">Courbe horaire · température & humidex</div>
  <div class="panel">
    ${renderHeatCurve(h.timeline)}
    <div class="legend"><span><i class="lg" style="background:${colorOf('elevated')}"></i>température (°C)</span><span><i class="lg" style="background:${colorOf('danger')};-webkit-mask:repeating-linear-gradient(90deg,#000 0 4px,transparent 4px 8px);mask:repeating-linear-gradient(90deg,#000 0 4px,transparent 4px 8px)"></i>humidex (ressenti)</span><span><i class="lg" style="background:${colorOf('high')}"></i>pic</span></div>
  </div>
  <div class="split" style="margin-top:18px">
    <div class="panel">
      <div class="panel-h">${icon('thermo')}<h3>Lieux les plus chauds</h3></div>
      <div class="table-wrap"><table><thead><tr><th>Lieu</th><th>Niveau</th><th>Temp.</th><th>Humidex</th><th>Pt rosée</th></tr></thead><tbody>${hot||'<tr><td colspan="5" class="muted">Pas de relevé de température.</td></tr>'}</tbody></table></div>
    </div>
    <div class="panel">
      <div class="panel-h">${icon('shield')}<h3>Conseils de prudence</h3></div>
      <ul class="heat-advice">${(h.advice||[]).map(a=>`<li>${esc(a)}</li>`).join('')}</ul>
      <div class="heat-note">${esc(h.note)}</div>
    </div>
  </div>`;
}

/* ---------------- expert view ---------------- */
function renderExpert(vm){
  const e=vm.expert||{};
  const groups={};(e.frames||[]).forEach(f=>{(groups[f.group]=groups[f.group]||[]).push(f);});
  const groupNames=Object.keys(groups);
  const stationRows=(e.stations||[]).slice(0,12).map(s=>`<tr><td><strong>${esc(s.name)}</strong><div class="muted">${esc(s.region||'')}</div></td><td><span class="badge ac-${cls(s.severity)}"><span class="bd"></span>${esc((s.severity||{}).label)}</span></td><td class="num">${num(s.score)}</td><td class="num">${esc(s.worst_time||'—')}</td><td class="muted">${esc((s.signals||[]).join(' · '))}</td></tr>`).join('');
  const provRows=(e.provinces||[]).map(p=>`<tr><td>${esc(p.province)}</td><td><span class="badge ac-${cls(p.severity)}"><span class="bd"></span>${esc((p.severity||{}).label)}</span></td><td class="num">${num(p.max_score)}</td><td class="muted">${esc(p.top_station||'')}</td></tr>`).join('');
  const val=e.validation||{},vs=val.scores||{},cf=val.confusion||{};
  const obs=e.observation||{},channels=obs.channels||[];
  const src=e.sources||{},ext=src.external_confirmation||{};
  const radar=e.radar_stack||{};
  const national=e.european_national_radar||{};
  const nationalMetrics=e.european_national_radar_metrics||{};
  const countries=Array.isArray(nationalMetrics.countries)?nationalMetrics.countries:[];
  const countryLabels={spain:'Espagne',france:'France',switzerland:'Suisse',netherlands:'Pays-Bas'};
  const countryRows=countries.map(c=>`<tr><td><strong>${esc(countryLabels[c.country]||c.country)}</strong></td><td><span class="badge ac-${c.machine_radar_available?'calm':'info'}"><span class="bd"></span>${c.machine_radar_available?'donnée exploitable':'interface prête'}</span></td><td class="muted">${esc(c.status||'')}</td><td class="num">${num(c.file_count,0)}</td><td class="num">${num(c.readable_file_count,0)}</td><td class="num">${num(c.radar_activity_score)}</td></tr>`).join('');
  return `
  <div class="subtabs" id="expert-subtabs">
    <button class="subtab active" data-sub="stations">Stations & zones</button>
    <button class="subtab" data-sub="observation">Observation émergente</button>
    <button class="subtab" data-sub="validation">Validation</button>
    <button class="subtab" data-sub="sources">Sources</button>
    <button class="subtab" data-sub="radars">Radars Europe</button>
    <button class="subtab" data-sub="maps">Cartes & graphes</button>
    <button class="subtab" data-sub="exports">Exports & API</button>
  </div>
  <div class="sub" data-sub="stations">
    <div class="section-title">Stations les plus sensibles</div>
    <div class="table-wrap"><table><thead><tr><th>Station</th><th>Sévérité</th><th>Score</th><th>Heure sensible</th><th>Signaux</th></tr></thead><tbody>${stationRows||'<tr><td colspan="5" class="muted">Aucune station.</td></tr>'}</tbody></table></div>
    <div class="section-title">Synthèse par province</div>
    <div class="table-wrap"><table><thead><tr><th>Province</th><th>Sévérité</th><th>Score max</th><th>Station pilote</th></tr></thead><tbody>${provRows||'<tr><td colspan="4" class="muted">Aucune donnée.</td></tr>'}</tbody></table></div>
  </div>
  <div class="sub" data-sub="observation" style="display:none">
    <div class="section-title">Passage du latent vers l’actualisé</div>
    <div class="grid cards3">${channels.map(ch=>`<div class="card"><div style="display:flex;justify-content:space-between;align-items:center;gap:8px"><h3>${esc(ch.label)}</h3><span class="badge ac-${ch.configured?'calm':'info'}"><span class="bd"></span>${ch.configured?'configuré':'préparé'}</span></div><p class="phrase">${esc(ch.status)}</p><div class="muted">${esc(ch.source)}</div></div>`).join('')}</div>
    <div class="card" style="margin-top:14px"><h3>Nowcast</h3><div class="chips"><span class="chip">radar : ${esc(obs.nowcast&&obs.nowcast.radar_confirmation)}</span><span class="chip">foudre : ${esc(obs.nowcast&&obs.nowcast.lightning_confirmation)}</span><span class="chip">prêt : ${obs.nowcast&&obs.nowcast.nowcast_ready?'oui':'non'}</span></div><p class="muted" style="margin-top:10px">${esc((obs.nowcast&&obs.nowcast.meaning)||obs.note||'')}</p></div>
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
    <p class="muted" style="margin-top:12px">Tant qu’aucun épisode vérifié n’est fourni, ces métriques restent un cadre prêt à être rempli (détection correcte, faux positifs/négatifs, lead time).</p>
  </div>
  <div class="sub" data-sub="sources" style="display:none">
    <div class="section-title">Santé des sources</div>
    <div class="grid cards4">
      <div class="card"><div class="kicker">Mode</div><div class="phrase">${esc(src.data_mode||'n/a')}</div></div>
      <div class="card"><div class="kicker">Sources OK</div><div class="score">${num(src.ok_count,0)}</div></div>
      <div class="card"><div class="kicker">Erreurs</div><div class="score">${num(src.error_count,0)}</div></div>
      <div class="card"><div class="kicker">Confirmation externe</div><div class="score">${num(ext.score)}</div><p class="phrase">${esc(ext.status||'')}</p></div>
    </div>
    ${(src.auto_sources&&src.auto_sources.length)?'<div class="section-title">Sources externes automatiques</div><div class="table-wrap"><table><thead><tr><th>Source</th><th>État</th><th>Détail</th></tr></thead><tbody>'+src.auto_sources.map(a=>`<tr><td>${esc(a.name)}</td><td><span class="badge ac-${a.ok?'calm':'elevated'}"><span class="bd"></span>${a.ok?'ok':esc(a.value||'erreur')}</span></td><td class="muted">${esc(a.detail)}</td></tr>`).join('')+'</tbody></table></div>':''}
  </div>
  <div class="sub" data-sub="radars" style="display:none">
    <div class="section-title">Radars Europe · Espagne, France, Suisse, Pays-Bas</div>
    <div class="grid cards4">
      <div class="card"><div class="kicker">RainViewer</div><div class="phrase">${esc(radar.rainviewer_evidence_level||'display_only')}</div><p class="muted">affichage radar immédiat, non utilisé comme preuve machine.</p></div>
      <div class="card"><div class="kicker">OPERA ORD</div><div class="phrase">${esc(radar.opera_ord_status||'non configuré')}</div><p class="muted">données européennes exploitables seulement si accès/licence configuré.</p></div>
      <div class="card"><div class="kicker">Radars nationaux</div><div class="score">${num(national.country_count,0)}</div><p class="phrase">${esc(national.status||'interfaces non chargées')}</p></div>
      <div class="card"><div class="kicker">Pays avec donnée machine</div><div class="score">${num(national.machine_country_count,0)}</div><p class="muted">si 0, la carte montre les interfaces prêtes, pas une confirmation radar.</p></div>
    </div>
    <div class="links" style="margin:14px 0">
      <a href="reports/latest/european_national_radar_map.html">${icon('map')}Carte radars nationaux Europe</a>
      <a href="reports/latest/european_national_radar_report.md">${icon('report')}Rapport radars nationaux</a>
      <a href="reports/latest/european_national_radar_sources.csv">${icon('download')}Sources CSV</a>
      <a href="api/radar.json">${icon('download')}API radar</a>
    </div>
    <div class="table-wrap"><table><thead><tr><th>Pays</th><th>État</th><th>Statut</th><th>Fichiers</th><th>Lus</th><th>Activité</th></tr></thead><tbody>${countryRows||'<tr><td colspan="6" class="muted">Aucun statut national disponible.</td></tr>'}</tbody></table></div>
    <div class="frame-wrap" style="margin-top:14px"><iframe title="Radars nationaux Europe" src="reports/latest/european_national_radar_map.html" loading="lazy"></iframe></div>
    <p class="muted" style="margin-top:10px">Cette vue expose les interfaces Espagne, France, Suisse et Pays-Bas. MeteoVoid ne transforme ces sources en preuve radar que si des fichiers lisibles sont réellement fournis ou récupérés.</p>
  </div>
  <div class="sub" data-sub="maps" style="display:none">
    <div class="subtabs" id="frame-tabs">${groupNames.map((g,gi)=>groups[g].map((f,fi)=>`<button class="subtab ${gi===0&&fi===0?'active':''}" data-src="${esc(f.file)}">${esc(g)} · ${esc(f.label)}</button>`).join('')).join('')}</div>
    <div class="frame-wrap"><iframe id="viewer" title="MeteoVoid expert" src="${esc((e.frames&&e.frames[0]&&e.frames[0].file)||'')}" loading="lazy"></iframe></div>
    <p class="muted" style="margin-top:10px">Une couche à la fois pour éviter l’effet « bouillie de points ».</p>
  </div>
  <div class="sub" data-sub="exports" style="display:none">
    <div class="section-title">Exports & API statique</div>
    <div class="links">${(e.exports||[]).map(x=>`<a href="${esc(x.file)}">${icon('download')}${esc(x.label)}</a>`).join('')}</div>
    <p class="muted" style="margin-top:12px">L’API JSON (<code>api/latest.json</code>, <code>stations</code>, <code>timeline</code>, <code>transition</code>, <code>sources</code>, <code>validation</code>, <code>upstream</code>, <code>heat</code>) est lue par cette page et réutilisable par d’autres clients.</p>
  </div>`;
}

/* ---------------- map ---------------- */
const REGION={belgium_center:'Centre',belgium_west:'Ouest',belgium_east:'Est',belgium_north:'Nord',belgium_south:'Sud',belgium_coast:'Littoral',belgium_ardennes:'Ardenne',belgium_brussels:'Bruxelles'};
function regionLabel(r){r=String(r||'');if(REGION[r])return REGION[r];return r.replace(/^belgium_/,'').replace(/_/g,' ').replace(/\b\w/g,c=>c.toUpperCase())||'Autre';}
let MAP={inst:null,markers:{},radarLayer:null,booted:false};

function renderMap(vm){
  const st=(vm.expert&&vm.expert.stations)||[];
  const groups={'Belgique':[],'Approches frontalières':[]};
  st.forEach(s=>{(String(s.region||'').indexOf('belgium')===0?groups['Belgique']:groups['Approches frontalières']).push(s);});
  const opts=Object.keys(groups).filter(g=>groups[g].length).map(g=>`<optgroup label="${esc(g)}">`+groups[g].map(s=>`<option value="${esc(s.station_id)}">${esc(s.name)} — ${num(s.score)}</option>`).join('')+'</optgroup>').join('');
  const leg={calm:'faible',watch:'modéré',elevated:'élevé',danger:'critique'};
  return `
  <div class="map-bar">
    <div class="map-pick"><label>${icon('pin')}<span>Lieu</span></label><select id="locsel" aria-label="Choisir un lieu">${opts}</select></div>
    <label class="map-toggle"><input type="checkbox" id="radartog"> Radar pluie (RainViewer)</label>
    <div class="map-legend">${['calm','watch','elevated','danger'].map(c=>`<span><i style="background:${colorOf(c)}"></i>${leg[c]}</span>`).join('')}</div>
  </div>
  <div class="map-wrap">
    <div id="mvmap" class="mvmap"></div>
    <aside id="mapdetail" class="map-detail"><p class="muted">Choisis un lieu dans la liste ou clique un point sur la carte.</p></aside>
  </div>
  <p class="muted" style="margin-top:10px">Les marqueurs forment la grille de stations MeteoVoid (taille selon le score). Le radar est une couche d’observation optionnelle, désactivée par défaut.</p>`;
}

function miniSpark(hourly){
  const v=(hourly||[]).map(x=>x.s).filter(x=>x!=null);
  if(v.length<2) return '';
  const W=160,H=46,n=v.length;
  const pts=v.map((s,i)=>[6+(W-12)*i/(n-1),H-5-(H-12)*clamp01(s)]);
  const line=smoothPath(pts);
  return `<svg class="spark" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" aria-hidden="true"><path d="${line} L ${pts[n-1][0].toFixed(1)} ${H-5} L ${pts[0][0].toFixed(1)} ${H-5} Z" fill="${colorOf('info')}22"/><path d="${line}" fill="none" stroke="${colorOf('info')}" stroke-width="2"/></svg>`;
}

function renderLocationDetail(s){
  const c=cls(s.severity),d=s.drivers||{};
  const row=(k,v,u)=>(v==null||v==='')?'':`<div class="dl"><span>${esc(k)}</span><strong>${esc(v)}${esc(u||'')}</strong></div>`;
  const wh=s.worst_time?String(s.worst_time).split('T').pop():'';
  return `<div class="md-head ac-${c}"><div><div class="eyebrow">${esc(regionLabel(s.region))}</div><h3>${esc(s.name)}</h3></div><span class="badge ac-${c}"><span class="bd"></span>${esc((s.severity||{}).label)}</span></div>
    <div class="md-score"><div><div class="eyebrow">Score MeteoVoid</div><div class="score txt-${c}">${num(s.score)}</div></div>${miniSpark(s.hourly)}</div>
    <div>
      ${row('Heure sensible',wh||'—')}
      ${row('Température',d.temperature_c,' °C')}
      ${row('Point de rosée',d.dew_point_c,' °C')}
      ${row('Proba pluie',d.precip_prob_pct,' %')}
      ${row('Chute pression 6h',d.pressure_drop_hpa,' hPa')}
      ${row('Rafales',d.wind_gust_ms,' m/s')}
    </div>
    ${(s.signals&&s.signals.length)?'<div class="eyebrow" style="margin-top:14px">Signaux</div><ul class="md-sig">'+s.signals.map(x=>`<li>${esc(x)}</li>`).join('')+'</ul>':''}`;
}

function selectLocation(id){
  const st=((VM.expert&&VM.expert.stations)||[]).find(s=>s.station_id===id);
  if(!st) return;
  const sel=document.getElementById('locsel'); if(sel&&sel.value!==id) sel.value=id;
  if(MAP.inst&&st.lat!=null&&st.lon!=null){MAP.inst.flyTo([st.lat,st.lon],9,{duration:.6});const m=MAP.markers[id];if(m&&m.openTooltip)m.openTooltip();}
  const det=document.getElementById('mapdetail'); if(det) det.innerHTML=renderLocationDetail(st);
}

function toggleRadar(on){
  if(!MAP.inst||!window.L) return;
  if(!on){if(MAP.radarLayer){MAP.inst.removeLayer(MAP.radarLayer);MAP.radarLayer=null;}return;}
  fetch('https://api.rainviewer.com/public/weather-maps.json',{cache:'no-store'}).then(r=>r.json()).then(d=>{
    const host=d.host||'https://tilecache.rainviewer.com';
    const frames=((d.radar&&d.radar.past)||[]).concat((d.radar&&d.radar.nowcast)||[]);
    const last=frames.length?frames[frames.length-1]:null; if(!last)return;
    MAP.radarLayer=L.tileLayer(host+last.path+'/256/{z}/{x}/{y}/4/1_1.png',{opacity:.6,attribution:'RainViewer'}).addTo(MAP.inst);
  }).catch(()=>{const t=document.getElementById('radartog');if(t)t.checked=false;});
}

function initMap(){
  const host=document.getElementById('mvmap'); if(!host) return;
  if(!window.L){
    host.innerHTML='<div class="map-fallback">Fond de carte indisponible (réseau). La sélection de lieu et le détail ci-contre restent utilisables.</div>';
    const sel=document.getElementById('locsel'); if(sel&&!sel._wired){sel._wired=true;sel.addEventListener('change',()=>selectLocation(sel.value));}
    const st=(VM.expert&&VM.expert.stations)||[]; if(st.length)selectLocation(st[0].station_id);
    return;
  }
  if(MAP.booted){if(MAP.inst)MAP.inst.invalidateSize();return;}
  MAP.booted=true;
  const map=L.map(host,{zoomControl:true,scrollWheelZoom:true}).setView([50.6,4.7],7);
  MAP.inst=map;
  L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',{subdomains:'abcd',maxZoom:19,attribution:'&copy; OpenStreetMap, &copy; CARTO'}).addTo(map);
  const st=(VM.expert&&VM.expert.stations)||[];
  st.forEach(s=>{if(s.lat==null||s.lon==null)return;
    const c=cls(s.severity),r=8+Math.round(clamp01(s.score)*14);
    const m=L.circleMarker([s.lat,s.lon],{radius:r,color:'#fff',weight:1.5,fillColor:colorOf(c),fillOpacity:.85});
    m.addTo(map);m.on('click',()=>selectLocation(s.station_id));
    m.bindTooltip(esc(s.name)+' · '+num(s.score),{direction:'top'});
    MAP.markers[s.station_id]=m;});
  const sel=document.getElementById('locsel'); if(sel)sel.addEventListener('change',()=>selectLocation(sel.value));
  const tog=document.getElementById('radartog'); if(tog)tog.addEventListener('change',()=>toggleRadar(tog.checked));
  if(st.length)selectLocation(st[0].station_id);
  setTimeout(()=>map.invalidateSize(),60);
}

/* ---------------- theme ---------------- */
function applyTheme(t){document.documentElement.setAttribute('data-theme',t);
  const b=document.getElementById('themetgl'); if(b)b.innerHTML=(t==='dark')?SUN_T:MOON_T;
  try{localStorage.setItem('mv-theme',t);}catch(e){}}
function initTheme(){let t='light';try{t=localStorage.getItem('mv-theme')|| (matchMedia&&matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');}catch(e){}applyTheme(t);
  const b=document.getElementById('themetgl'); if(b)b.addEventListener('click',()=>{const cur=document.documentElement.getAttribute('data-theme');applyTheme(cur==='dark'?'light':'dark');paint();const a=document.querySelector('.tab.active');if(a)go(a.dataset.view);});}

/* ---------------- boot ---------------- */
let VM = FALLBACK;
function paint(){
  document.getElementById('disclaimer').innerHTML = icon('info')+'<div><b>Prototype non officiel.</b> '+esc((VM.meta&&VM.meta.disclaimer)||'')+'</div>';
  document.getElementById('stamp').textContent = (VM.meta&&VM.meta.generated_at)||'—';
  document.getElementById('view-simple').innerHTML = renderSimple(VM);
  document.getElementById('view-operational').innerHTML = renderOperational(VM);
  document.getElementById('view-heat').innerHTML = renderHeat(VM);
  document.getElementById('view-map').innerHTML = renderMap(VM);
  document.getElementById('view-expert').innerHTML = renderExpert(VM);
  wireExpert();
  animateArcs();
  animateCounts();
  try{if(MAP.inst)MAP.inst.remove();}catch(e){}
  MAP.inst=null;MAP.markers={};MAP.radarLayer=null;MAP.booted=false;
  if(document.getElementById('view-map').classList.contains('active'))initMap();
  document.getElementById('footer').innerHTML = `MeteoVoid Belgique · run <code>${esc((VM.meta&&VM.meta.run_id)||'')}</code> · mode <code>${esc((VM.meta&&VM.meta.data_mode)||'')}</code> · ${esc((VM.meta&&VM.meta.disclaimer)||'')}`;
}
function go(view){
  document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active',t.dataset.view===view));
  document.querySelectorAll('.view').forEach(v=>v.classList.toggle('active',v.id==='view-'+view));
  if(view==='map') initMap();
  window.scrollTo({top:0,behavior:'smooth'});
}
function wireExpert(){
  const subtabs=document.getElementById('expert-subtabs');
  if(subtabs){subtabs.querySelectorAll('.subtab').forEach(btn=>btn.addEventListener('click',()=>{
    subtabs.querySelectorAll('.subtab').forEach(b=>b.classList.remove('active'));btn.classList.add('active');
    document.querySelectorAll('#view-expert .sub').forEach(s=>s.style.display=(s.dataset.sub===btn.dataset.sub)?'block':'none');
  }));}
  const frameTabs=document.getElementById('frame-tabs'),viewer=document.getElementById('viewer');
  if(frameTabs&&viewer){frameTabs.querySelectorAll('.subtab').forEach(btn=>btn.addEventListener('click',()=>{
    frameTabs.querySelectorAll('.subtab').forEach(b=>b.classList.remove('active'));btn.classList.add('active');viewer.src=btn.dataset.src;
  }));}
}
document.querySelectorAll('.tab[data-view]').forEach(t=>t.addEventListener('click',()=>go(t.dataset.view)));
initTheme();
paint();

(async()=>{
  try{
    const base=(VM.meta&&VM.meta.endpoints)||{};
    const [latest,stations,timeline,transition,sources,validation,heat]=await Promise.all(
      ['latest','stations','timeline','transition','sources','validation','heat'].map(k=>
        fetch(base[k]||('api/'+k+'.json'),{cache:'no-store'}).then(r=>r.ok?r.json():null).catch(()=>null)));
    if(!latest) return;
    const merged=JSON.parse(JSON.stringify(FALLBACK));
    merged.meta.generated_at = latest.generated_at||merged.meta.generated_at;
    if(stations){merged.expert.stations=stations.stations||merged.expert.stations;merged.expert.provinces=stations.provinces||merged.expert.provinces;}
    if(timeline){merged.operational.timeline=timeline;}
    if(transition){merged.operational.blocks=transition.blocks||merged.operational.blocks;merged.operational.transition_level=transition.transition_level||merged.operational.transition_level;merged.operational.void_collapse_signal=transition.void_collapse_signal;merged.operational.interpretation=transition.interpretation;}
    if(sources){merged.expert.sources=sources.sources||merged.expert.sources;merged.expert.observation=sources.observation||merged.expert.observation;merged.expert.watchdog=sources.watchdog||merged.expert.watchdog;}
    if(validation){merged.expert.validation=validation;}
    if(heat){merged.heat=heat;}
    if(latest.alert_explanation){merged.operational.alert_explanation=latest.alert_explanation;}
    const active=document.querySelector('.tab.active');
    VM=merged; paint();
    if(active) go(active.dataset.view);
  }catch(e){}
})();
</script>
</body>
</html>
"""


# --- Europe public page v3 -------------------------------------------------------
# Override the first Europe builder with a fuller page that reuses the same
# MeteoVoid visual language as the Belgium dashboard. The Belgium page is left
# untouched; this adds a richer Europe contract and page.


def _source_bucket_v3(source: dict[str, Any]) -> str:
    evidence = str(source.get("evidence_level") or "")
    status = str(source.get("status") or "")
    family = str(source.get("source_family") or "")
    if source.get("machine_evidence"):
        return "machine"
    if evidence in {"display_only", "wms_open_data"} or family in {"display", "wms_display"}:
        return "display"
    if evidence in {"open_data_api", "stac_open_data", "api_required"}:
        return "national"
    if evidence in {"national_nowcast", "data_on_request"} or family == "forecast_nowcast":
        return "nowcast"
    if evidence == "opera_ord_fallback" or family == "opera_fallback":
        return "opera"
    if status in {"requires_api_key", "endpoint_not_configured"}:
        return "blocked"
    return "other"


def _country_completeness(country: dict[str, Any]) -> float:
    source_count = int(country.get("source_count") or 0)
    configured = int(country.get("configured_source_count") or 0)
    machine = 1 if country.get("machine_radar_available") else 0
    corridors = int(country.get("linked_corridor_count") or 0)
    required = int(country.get("required_key_count") or 0)
    missing = int(country.get("missing_api_key_count") or 0)
    source_score = min(1.0, source_count / 5.0)
    configured_score = min(1.0, configured / max(1, source_count))
    corridor_score = min(1.0, corridors / 2.0)
    key_score = 1.0 if required == 0 else max(0.0, 1.0 - missing / max(1, required))
    return round(
        _clamp01(
            0.28 * source_score
            + 0.24 * configured_score
            + 0.22 * corridor_score
            + 0.16 * key_score
            + 0.10 * machine
        ),
        3,
    )


def _load_europe_registry(report_dir: Path) -> dict[str, Any]:
    for candidate in [
        Path("config/european_national_radars.yaml"),
        report_dir.parent.parent / "config" / "european_national_radars.yaml",
    ]:
        try:
            if candidate.exists():
                import yaml  # type: ignore[import-untyped]

                payload = yaml.safe_load(candidate.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    return payload
        except (OSError, ImportError):
            continue
    return {}


def build_europe_model(report_dir: Path, vm: dict[str, Any]) -> dict[str, Any]:
    status = _load_json(report_dir / "european_national_radar_status.json")
    metrics = _load_json(report_dir / "european_national_radar_metrics.json")
    upstream = _load_json(report_dir / "upstream_watch.json")
    radar_stack = _load_json(report_dir / "radar_stack.json")
    rainviewer = _load_json(report_dir / "rainviewer_status.json")
    opera_status = _load_json(report_dir / "opera_ord_status.json")
    opera_inventory = _load_json(report_dir / "opera_ord_inventory.json")
    opera_files = _load_json(report_dir / "opera_ord_files_manifest.json")
    opera_metrics = _load_json(report_dir / "opera_radar_metrics.json")
    registry = _load_europe_registry(report_dir)

    metric_by_country = {
        str(row.get("country")): row
        for row in metrics.get("countries", [])
        if isinstance(row, dict) and row.get("country")
    }
    registry_countries = (
        registry.get("countries") if isinstance(registry.get("countries"), dict) else {}
    )
    status_countries = [row for row in status.get("countries", []) if isinstance(row, dict)]
    row_by_country = {
        str(row.get("country")): row for row in status_countries if row.get("country")
    }

    base_order = ["france", "netherlands", "spain", "switzerland"]
    extra = sorted(
        (
            set(registry_countries.keys())
            | set(row_by_country.keys())
            | set(metric_by_country.keys())
        )
        - set(base_order)
    )
    country_keys = [*base_order, *extra]

    corridors_raw = upstream.get("corridors") if isinstance(upstream.get("corridors"), list) else []
    corridors = [row for row in corridors_raw if isinstance(row, dict)]

    def _corridors_for_country(country: str) -> list[dict[str, Any]]:
        prefixes = {
            "france": ("FR_", "PARIS", "CHAMPAGNE", "ENGLISH_CHANNEL"),
            "netherlands": ("NL_", "NETHER", "NORTH_SEA"),
            "switzerland": ("CH_", "ALP", "JURA"),
            "spain": ("ES_", "IBER", "BISCAY", "GASCOGNE"),
        }.get(country, ())
        found: list[dict[str, Any]] = []
        for corridor in corridors:
            text = " ".join(
                str(corridor.get(key) or "")
                for key in ["source_region", "corridor_id", "name", "target_region"]
            ).upper()
            if any(prefix.upper() in text for prefix in prefixes):
                found.append(corridor)
        return sorted(
            found,
            key=lambda item: _num(item.get("corridor_score"), 0.0) or 0.0,
            reverse=True,
        )

    countries: list[dict[str, Any]] = []
    flat_sources: list[dict[str, Any]] = []
    source_families: dict[str, int] = {}

    for country in country_keys:
        cfg = registry_countries.get(country) if isinstance(registry_countries, dict) else {}
        cfg = cfg if isinstance(cfg, dict) else {}
        row = row_by_country.get(country, {})
        metric = metric_by_country.get(country, {})
        sources_from_status = row.get("sources") if isinstance(row.get("sources"), list) else []
        sources_from_cfg = cfg.get("sources") if isinstance(cfg.get("sources"), list) else []
        merged_sources: dict[str, dict[str, Any]] = {}
        for item in sources_from_cfg:
            if isinstance(item, dict):
                merged_sources[str(item.get("id") or len(merged_sources))] = dict(item)
        for item in sources_from_status:
            if isinstance(item, dict):
                key = str(item.get("id") or len(merged_sources))
                base = merged_sources.get(key, {})
                merged_sources[key] = {**base, **item}
        raw_sources = list(merged_sources.values())
        sources: list[dict[str, Any]] = []
        for source in raw_sources:
            if not isinstance(source, dict):
                continue
            normalized = dict(source)
            if "status" not in normalized:
                evidence = str(normalized.get("evidence_level") or "")
                if evidence == "api_required" and normalized.get("api_key_env"):
                    normalized["status"] = "requires_api_key"
                elif evidence == "opera_ord_fallback":
                    normalized["status"] = "covered_by_opera_ord_connector"
                elif evidence in {
                    "display_only",
                    "stac_open_data",
                    "wms_open_data",
                    "data_on_request",
                }:
                    normalized["status"] = "interface_ready"
                else:
                    normalized["status"] = "interface_only_unconfigured"
            normalized["bucket"] = _source_bucket_v3(normalized)
            sources.append(normalized)
            source_families[normalized["bucket"]] = source_families.get(normalized["bucket"], 0) + 1

        required_env = cfg.get("required_env") if isinstance(cfg.get("required_env"), list) else []
        missing_env = [
            env
            for env in required_env
            if env
            and not any(s.get("api_key_configured") for s in sources if s.get("api_key_env") == env)
        ]
        configured_sources = [
            s
            for s in sources
            if str(s.get("status"))
            not in {"endpoint_not_configured", "interface_only_unconfigured"}
        ]
        machine_sources = [s for s in sources if s.get("machine_evidence")]
        display_sources = [s for s in sources if s.get("bucket") == "display"]
        national_sources = [s for s in sources if s.get("bucket") == "national"]
        nowcast_sources = [s for s in sources if s.get("bucket") == "nowcast"]
        opera_sources = [s for s in sources if s.get("bucket") == "opera"]
        linked_corridors = _corridors_for_country(country)
        best_corridor_score = max(
            (_num(c.get("corridor_score"), 0.0) or 0.0 for c in linked_corridors),
            default=0.0,
        )
        priority_text = str(
            row.get("priority_for_belgium") or cfg.get("priority_for_belgium") or "medium"
        )
        priority_score = {"high": 0.82, "medium": 0.55, "low": 0.30}.get(priority_text, 0.45)
        machine_available = bool(
            row.get("machine_radar_available") or metric.get("machine_radar_available")
        )
        readiness_score = round(
            _clamp01(
                0.28 * priority_score
                + 0.23 * min(1.0, len(sources) / 5.0)
                + 0.20 * min(1.0, len(configured_sources) / max(1, len(sources)))
                + 0.17 * min(1.0, len(linked_corridors) / 2.0)
                + 0.12 * (1.0 if machine_available else 0.0)
            ),
            3,
        )
        blockers: list[str] = []
        if missing_env:
            blockers.append("clé API manquante : " + ", ".join(str(env) for env in missing_env))
        if not machine_available:
            blockers.append("aucune trame radar nationale lisible dans ce run")
        if opera_sources:
            blockers.append("fallback OPERA ORD utilisable pour la couche paneuropéenne")
        if not sources:
            blockers.append("aucune source nationale référencée")

        payload = {
            "country": country,
            "label": row.get("label")
            or cfg.get("label")
            or _EUROPE_COUNTRY_LABELS.get(country, country.title()),
            "iso2": row.get("iso2") or cfg.get("iso2"),
            "bbox": row.get("bbox") if isinstance(row.get("bbox"), dict) else cfg.get("bbox", {}),
            "priority_for_belgium": priority_text,
            "priority_score": priority_score,
            "readiness_score": readiness_score,
            "completeness_score": 0.0,
            "upstream_role": row.get("upstream_role")
            or cfg.get("upstream_role")
            or _EUROPE_COUNTRY_CONTEXT.get(country, {}).get("role"),
            "belgium_relevance": row.get("belgium_relevance") or cfg.get("belgium_relevance"),
            "corridor_family": row.get("corridor_family")
            or cfg.get("corridor_family")
            or _EUROPE_COUNTRY_CONTEXT.get(country, {}).get("corridor"),
            "watch_zones": (
                cfg.get("watch_zones") if isinstance(cfg.get("watch_zones"), list) else []
            ),
            "required_env": required_env,
            "required_key_count": len(required_env),
            "missing_api_key_count": len(missing_env),
            "source_count": len(sources),
            "configured_source_count": len(configured_sources),
            "display_source_count": len(display_sources),
            "national_source_count": len(national_sources),
            "nowcast_source_count": len(nowcast_sources),
            "opera_fallback_count": len(opera_sources),
            "machine_source_count": len(machine_sources),
            "machine_radar_available": machine_available,
            "radar_activity_score": _round(
                (
                    row.get("radar_activity_score")
                    if row.get("radar_activity_score") is not None
                    else metric.get("radar_activity_score")
                ),
                3,
            ),
            "status": metric.get("status")
            or row.get("status")
            or "interface_ready_no_machine_data",
            "evidence_state": "machine_metrics" if machine_available else "interface_only",
            "readable_file_count": metric.get("readable_file_count", 0),
            "file_count": metric.get("file_count", 0),
            "best_corridor_score": round(best_corridor_score, 3),
            "linked_corridor_count": len(linked_corridors),
            "blockers": blockers,
            "next_steps": [
                "configurer les clés API nationales quand elles sont requises",
                "télécharger ou fournir au moins une trame radar lisible par pays",
                "calculer des métriques radar et les relier aux corridors vers la Belgique",
                "croiser la source nationale avec OPERA ORD et RainViewer",
            ],
            "corridors": [
                {
                    "id": c.get("corridor_id"),
                    "name": c.get("name"),
                    "score": _round(c.get("corridor_score"), 3),
                    "confidence": c.get("confidence"),
                    "source_region": c.get("source_region"),
                    "target_region": c.get("target_region"),
                    "target_zones": (
                        c.get("target_zones") if isinstance(c.get("target_zones"), list) else []
                    ),
                    "estimated_arrival_hours": c.get("estimated_arrival_hours"),
                    "interpretation": c.get("interpretation"),
                }
                for c in linked_corridors[:8]
            ],
            "sources": [
                {
                    "id": s.get("id"),
                    "provider": s.get("provider"),
                    "role": s.get("role"),
                    "status": s.get("status"),
                    "bucket": s.get("bucket"),
                    "source_family": s.get("source_family"),
                    "evidence_level": s.get("evidence_level"),
                    "expected_format": s.get("expected_format"),
                    "machine_evidence": bool(s.get("machine_evidence")),
                    "api_key_env": s.get("api_key_env"),
                    "api_key_configured": s.get("api_key_configured"),
                    "update_interval_minutes": s.get("update_interval_minutes"),
                    "public_reference": s.get("public_reference"),
                    "license_note": s.get("license_note"),
                    "note": s.get("note"),
                }
                for s in sources
            ],
        }
        payload["completeness_score"] = _country_completeness(payload)
        countries.append(payload)
        for source in payload["sources"]:
            flat_sources.append({"country": payload["label"], "country_key": country, **source})

    countries.sort(
        key=lambda item: (
            str(item.get("priority_for_belgium")) != "high",
            -float(item.get("readiness_score") or 0.0),
            str(item.get("country")),
        )
    )
    machine_count = sum(1 for item in countries if item.get("machine_radar_available"))
    source_count = sum(int(item.get("source_count") or 0) for item in countries)
    missing_keys = sum(int(item.get("missing_api_key_count") or 0) for item in countries)
    corridor_count = sum(int(item.get("linked_corridor_count") or 0) for item in countries)
    configured_count = sum(int(item.get("configured_source_count") or 0) for item in countries)
    readiness_mean = round(
        sum(float(item.get("readiness_score") or 0.0) for item in countries)
        / max(1, len(countries)),
        3,
    )

    pan_layers = (
        registry.get("pan_european_layers")
        if isinstance(registry.get("pan_european_layers"), list)
        else []
    )
    radar_layers = [
        {
            "id": "rainviewer_display",
            "label": "RainViewer",
            "role": "affichage radar immédiat",
            "status": rainviewer.get("status") or "display_layer_ready",
            "evidence_level": "display_only",
            "file": "reports/latest/rainviewer_radar_map.html",
            "meaning": "montre le radar, ne produit pas de preuve machine",
        },
        {
            "id": "opera_ord",
            "label": "OPERA ORD",
            "role": "mosaïque radar européenne exploitable si fichiers disponibles",
            "status": opera_status.get("status") or "optional_connector",
            "evidence_level": "machine_optional",
            "file": "reports/latest/opera_ord_inventory.json",
            "meaning": "voie paneuropéenne unifiée pour ODIM HDF5 ou GeoTIFF",
        },
        {
            "id": "national_radars",
            "label": "Radars nationaux",
            "role": "Espagne, France, Suisse, Pays-Bas",
            "status": status.get("status") or "interfaces_ready_no_machine_data",
            "evidence_level": "country_specific_optional",
            "file": "reports/latest/european_national_radar_map.html",
            "meaning": "interfaces nationales séparées, promotion en preuve seulement si fichier lisible",
        },
        {
            "id": "openmeteo_fallback",
            "label": "Open-Meteo fallback",
            "role": "flux et indices de modèle si radar absent",
            "status": "fallback_available_if_enabled",
            "evidence_level": "model_fallback",
            "file": "api/upstream.json",
            "meaning": "utile pour les flux, pas une preuve radar",
        },
    ]

    simple = {
        "headline": "Europe amont aussi lisible que la Belgique",
        "status": status.get("status") or "interfaces_ready_no_machine_data",
        "synthesis": (
            f"{len(countries)} pays suivis, {source_count} sources référencées, "
            f"{configured_count} interfaces prêtes, {machine_count} pays avec métriques machine."
        ),
        "readiness_score": readiness_mean,
        "country_count": len(countries),
        "source_count": source_count,
        "configured_source_count": configured_count,
        "machine_country_count": machine_count,
        "missing_api_key_count": missing_keys,
        "corridor_count": corridor_count,
        "non_official": True,
        "data_honesty": "Une carte ou une interface prête ne devient pas une preuve radar machine sans fichier lu et métriques calculées.",
    }

    operational = {
        "chain": [
            {
                "step": "Source",
                "text": "registre national et paneuropéen",
                "score": min(1.0, source_count / 20.0),
            },
            {
                "step": "Accès",
                "text": "clé API, STAC, WMS, OPERA ou affichage",
                "score": min(1.0, configured_count / max(1, source_count)),
            },
            {
                "step": "Fichier",
                "text": "trame locale téléchargée ou fournie",
                "score": min(1.0, machine_count / max(1, len(countries))),
            },
            {
                "step": "Décodage",
                "text": "GeoTIFF, HDF5, ODIM ou tableau numérique",
                "score": min(1.0, machine_count / max(1, len(countries))),
            },
            {
                "step": "Métriques",
                "text": "activité radar et couverture par pays",
                "score": min(1.0, machine_count / max(1, len(countries))),
            },
            {
                "step": "Corridor",
                "text": "rattachement aux trajectoires vers Belgique",
                "score": min(1.0, corridor_count / max(1, len(countries))),
            },
            {
                "step": "Lecture",
                "text": "signal amont, confirmation et limites",
                "score": readiness_mean,
            },
        ],
        "why_it_matters": [
            "France et Pays-Bas sont les couloirs les plus directs vers la Belgique.",
            "Espagne aide à lire les remontées chaudes et humides qui préparent l'instabilité en France.",
            "Suisse aide à suivre la dynamique alpine et l'est de la France.",
            "OPERA ORD reste la voie radar paneuropéenne la plus cohérente lorsque les fichiers sont disponibles.",
        ],
        "limits": status.get("limits") or [],
    }

    exports = [
        {"label": "API Europe", "href": "api/europe.json"},
        {"label": "API radar", "href": "api/radar.json"},
        {
            "label": "Carte radars nationaux",
            "href": "reports/latest/european_national_radar_map.html",
        },
        {
            "label": "Rapport radars nationaux",
            "href": "reports/latest/european_national_radar_report.md",
        },
        {
            "label": "Sources radars CSV",
            "href": "reports/latest/european_national_radar_sources.csv",
        },
        {
            "label": "Statut radars JSON",
            "href": "reports/latest/european_national_radar_status.json",
        },
        {
            "label": "Métriques radars JSON",
            "href": "reports/latest/european_national_radar_metrics.json",
        },
        {"label": "Carte Europe amont", "href": "reports/latest/european_upstream_map.html"},
        {"label": "Rapport Europe amont", "href": "reports/latest/upstream_watch_report.md"},
        {"label": "RainViewer", "href": "reports/latest/rainviewer_radar_map.html"},
        {"label": "OPERA inventory", "href": "reports/latest/opera_ord_inventory.json"},
        {"label": "Métriques OPERA", "href": "reports/latest/opera_radar_metrics.json"},
    ]

    return {
        "page_contract": "meteovoid_europe_page_full_v3_same_design",
        "generated_at": vm.get("meta", {}).get("generated_at"),
        "run_id": vm.get("meta", {}).get("run_id"),
        "data_mode": vm.get("meta", {}).get("data_mode"),
        "disclaimer": vm.get("meta", {}).get("disclaimer"),
        "simple": simple,
        "summary": simple,
        "operational": operational,
        "countries": countries,
        "sources": flat_sources,
        "source_families": source_families,
        "radar_layers": radar_layers,
        "pan_european_layers": [layer for layer in pan_layers if isinstance(layer, dict)],
        "corridors": [
            {
                "id": c.get("corridor_id"),
                "name": c.get("name"),
                "score": _round(c.get("corridor_score"), 3),
                "confidence": c.get("confidence"),
                "source_region": c.get("source_region"),
                "target_region": c.get("target_region"),
                "target_zones": (
                    c.get("target_zones") if isinstance(c.get("target_zones"), list) else []
                ),
                "estimated_arrival_hours": c.get("estimated_arrival_hours"),
                "interpretation": c.get("interpretation"),
            }
            for c in corridors
        ],
        "linked_outputs": {
            "belgium": "index.html",
            "methodology": "methodology.html",
            "radar_api": "api/radar.json",
            "upstream_api": "api/upstream.json",
            "europe_api": "api/europe.json",
            "national_map": "reports/latest/european_national_radar_map.html",
            "rainviewer": "reports/latest/rainviewer_radar_map.html",
            "upstream_map": "reports/latest/european_upstream_map.html",
        },
        "raw": {
            "national_status": status,
            "national_metrics": metrics,
            "radar_stack": radar_stack,
            "rainviewer": rainviewer,
            "opera_status": opera_status,
            "opera_inventory": opera_inventory,
            "opera_files": opera_files,
            "opera_metrics": opera_metrics,
        },
        "exports": exports,
        "links": {"belgium": "index.html", "methodology": "methodology.html"},
    }


EUROPE_MAX_TEMPLATE = r"""<!doctype html>
<html lang="fr" data-theme="light">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>MeteoVoid Europe · Veille radar amont</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#e9edf3;--bg-2:#eef2f7;--panel:#ffffff;--panel-2:#f4f7fb;--inset:#eef3f9;--ink:#0a1322;--ink-2:#43546b;--muted:#82909f;--line:#e1e8f0;--accent:#2f49d8;--accent-soft:#eaedfb;--shadow:0 2px 4px rgba(13,28,55,.05),0 12px 30px rgba(13,28,55,.07);--r:14px;--r-lg:20px;--f-display:'Space Grotesk',ui-sans-serif,system-ui,Segoe UI,sans-serif;--f-body:'Inter',ui-sans-serif,system-ui,Segoe UI,Roboto,Arial,sans-serif;--f-mono:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,monospace;--c-calm:#16a075;--c-info:#3a7ec4;--c-watch:#cf9a1f;--c-elevated:#dd7634;--c-high:#d65238;--c-danger:#cf2e39}
[data-theme="dark"]{--bg:#070b13;--bg-2:#0a101b;--panel:#111826;--panel-2:#0d141f;--inset:#0c121d;--ink:#e9f0fa;--ink-2:#9fb1c8;--muted:#697a92;--line:#1e293b;--accent:#6f84ff;--accent-soft:#1a2240;--shadow:0 2px 6px rgba(0,0,0,.45),0 18px 40px rgba(0,0,0,.5);--c-calm:#1cb98a;--c-info:#5298e0;--c-watch:#e3b13b;--c-elevated:#ef8a4c;--c-high:#ec6a50;--c-danger:#e74752}
*{box-sizing:border-box}html,body{margin:0}body{font-family:var(--f-body);color:var(--ink);line-height:1.5;background:var(--bg);background-image:radial-gradient(1200px 480px at 84% -10%,color-mix(in srgb,var(--accent) 7%,transparent),transparent),linear-gradient(rgba(20,40,80,.035) 1px,transparent 1px),linear-gradient(90deg,rgba(20,40,80,.035) 1px,transparent 1px);background-size:auto,34px 34px,34px 34px;background-attachment:fixed}a{color:var(--accent);text-decoration:none;font-weight:700}a:hover{text-decoration:underline}.cmd{position:sticky;top:0;z-index:20;background:color-mix(in srgb,var(--panel) 86%,transparent);backdrop-filter:blur(14px) saturate(1.3);border-bottom:1px solid var(--line)}.cmd-wrap{max-width:1240px;margin:0 auto;display:flex;align-items:center;gap:18px;padding:12px 24px}.brand{display:flex;align-items:center;gap:12px;min-width:0}.mark{width:40px;height:40px;border-radius:12px;background:linear-gradient(140deg,#1c9f9c,#2f49d8);display:grid;place-items:center;color:#fff;box-shadow:0 6px 18px color-mix(in srgb,var(--accent) 40%,transparent)}.brand h1{font-family:var(--f-display);font-size:17px;font-weight:600;margin:0;letter-spacing:-.02em;line-height:1.1}.brand p{margin:1px 0 0;font-size:11.5px;color:var(--muted)}.cmd-right{margin-left:auto;display:flex;align-items:center;gap:14px}.status-chip{display:flex;align-items:center;gap:9px;border:1px solid var(--line);border-radius:999px;padding:6px 12px;background:var(--panel-2)}.live-dot{width:8px;height:8px;border-radius:50%;background:var(--c-calm)}.st-k{font-family:var(--f-mono);font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}.st-v{font-family:var(--f-mono);font-size:12px;font-weight:700}.tgl{width:38px;height:38px;border-radius:11px;border:1px solid var(--line);background:var(--panel-2);color:var(--ink-2);cursor:pointer}.tabs{max-width:1240px;margin:0 auto;display:flex;gap:2px;padding:0 24px;overflow-x:auto}.tab{position:relative;border:0;background:transparent;color:var(--muted);padding:12px 15px 13px;font-weight:700;cursor:pointer;font-size:13.5px;white-space:nowrap}.tab:after{content:"";position:absolute;left:12px;right:12px;bottom:0;height:2px;background:var(--accent);transform:scaleX(0);transition:.2s}.tab:hover,.tab.active{color:var(--ink)}.tab.active:after{transform:scaleX(1)}main{max-width:1240px;margin:0 auto;padding:26px 24px 16px}.disclaimer{display:flex;gap:10px;border:1px solid color-mix(in srgb,var(--c-watch) 32%,var(--line));border-left:3px solid var(--c-watch);border-radius:10px;padding:11px 14px;font-size:12.5px;color:var(--ink-2);margin-bottom:22px;background:color-mix(in srgb,var(--c-watch) 8%,var(--panel))}.view{display:none}.view.active{display:block}.hero{position:relative;border:1px solid var(--line);border-radius:var(--r-lg);background:var(--panel);box-shadow:var(--shadow);overflow:hidden;padding:28px}.hero:before{content:"";position:absolute;inset:0;background:radial-gradient(620px 280px at 90% -40%,color-mix(in srgb,var(--accent) 12%,transparent),transparent);pointer-events:none}.hero>*{position:relative}.hero-grid{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(290px,.6fr);gap:26px;align-items:center}.eyebrow{font-family:var(--f-mono);font-size:10.5px;text-transform:uppercase;letter-spacing:.14em;color:var(--muted);font-weight:700}.hero h2{font-family:var(--f-display);font-size:clamp(32px,5vw,52px);line-height:1;margin:7px 0 10px;letter-spacing:-.04em}.lead{font-size:15px;color:var(--ink-2);margin:0;max-width:70ch}.hero-tags,.links{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}.pill,.links a{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);border-radius:999px;background:var(--panel-2);padding:7px 11px;font-size:12.5px;color:var(--ink-2)}.links a{color:var(--accent)}.grid{display:grid;gap:14px}.cards2{grid-template-columns:repeat(2,minmax(0,1fr))}.cards3{grid-template-columns:repeat(3,minmax(0,1fr))}.cards4{grid-template-columns:repeat(4,minmax(0,1fr))}.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);box-shadow:var(--shadow);padding:18px}.card h3,.card h2{font-family:var(--f-display);margin:4px 0 8px}.kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px;margin:18px 0}.kpi{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px;box-shadow:var(--shadow)}.kpi .v{font-family:var(--f-display);font-size:30px;font-weight:700;letter-spacing:-.03em}.kpi .k{font-family:var(--f-mono);font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.12em}.section-title{font-family:var(--f-mono);font-size:11px;text-transform:uppercase;letter-spacing:.13em;color:var(--muted);font-weight:700;margin:30px 0 13px;display:flex;align-items:center;gap:10px}.section-title:before{content:"";width:5px;height:5px;border-radius:50%;background:var(--accent)}.muted{color:var(--muted);font-size:13px}.small{font-size:12px}.score{font-family:var(--f-display);font-size:42px;font-weight:700;letter-spacing:-.04em}.ok{color:var(--c-calm)}.watch{color:var(--c-watch)}.danger{color:var(--c-danger)}.bar{height:8px;background:var(--inset);border-radius:999px;overflow:hidden}.bar span{display:block;height:100%;background:linear-gradient(90deg,var(--c-info),var(--c-calm));border-radius:999px}.chain{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:10px}.step{position:relative}.step:after{content:"";position:absolute;top:24px;right:-10px;width:10px;height:1px;background:var(--line)}.step:last-child:after{display:none}.step .n{width:46px;height:46px;border-radius:14px;background:var(--panel-2);border:1px solid var(--line);display:grid;place-items:center;font-family:var(--f-display);font-weight:700}.step h3{font-size:14px}.country-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.country-card{padding:0;overflow:hidden}.country-head{padding:18px;border-bottom:1px solid var(--line);background:linear-gradient(135deg,color-mix(in srgb,var(--accent) 10%,var(--panel)),var(--panel))}.country-body{padding:18px}.country-title{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.badge{font-family:var(--f-mono);font-size:10px;text-transform:uppercase;letter-spacing:.08em;border:1px solid var(--line);border-radius:999px;padding:5px 8px;background:var(--panel-2);color:var(--ink-2)}.badge.ok{border-color:color-mix(in srgb,var(--c-calm) 35%,var(--line));background:color-mix(in srgb,var(--c-calm) 10%,var(--panel));color:var(--c-calm)}.badge.watch{border-color:color-mix(in srgb,var(--c-watch) 35%,var(--line));background:color-mix(in srgb,var(--c-watch) 10%,var(--panel));color:var(--c-watch)}.badge.info{border-color:color-mix(in srgb,var(--c-info) 35%,var(--line));background:color-mix(in srgb,var(--c-info) 10%,var(--panel));color:var(--c-info)}.dl{display:grid;grid-template-columns:1fr auto;gap:12px;border-top:1px solid var(--line);padding:8px 0;font-size:13px}.dl:first-child{border-top:0}.src-list{display:grid;gap:8px;margin-top:10px}.src{border:1px solid var(--line);border-radius:12px;padding:10px;background:var(--panel-2)}.src-top{display:flex;justify-content:space-between;gap:8px}.src b{font-size:13px}.iframe-card{padding:0;overflow:hidden}.iframe-card iframe,.frame{width:100%;height:540px;border:0;background:var(--inset)}table{width:100%;border-collapse:collapse;font-size:13px}th,td{border-bottom:1px solid var(--line);padding:10px;text-align:left;vertical-align:top}th{font-family:var(--f-mono);font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.1em;background:var(--panel-2)}pre{max-height:520px;overflow:auto;background:var(--panel-2);border:1px solid var(--line);border-radius:14px;padding:14px;font-size:12px;color:var(--ink-2)}footer{max-width:1240px;margin:0 auto 20px;padding:0 24px;color:var(--muted);font-size:12px}@media(max-width:980px){.hero-grid,.cards2,.cards3,.cards4,.country-grid,.chain,.kpis{grid-template-columns:1fr}.cmd-wrap{padding:10px 14px}.tabs{padding:0 14px}main{padding:18px 14px}.iframe-card iframe,.frame{height:420px}}
</style>
</head>
<body>
<header class="cmd"><div class="cmd-wrap"><div class="brand"><div class="mark">EU</div><div><h1>MeteoVoid Europe</h1><p>Page Europe complète · Espagne · France · Suisse · Pays-Bas · même design que Belgique</p></div></div><div class="cmd-right"><div class="status-chip"><span class="live-dot"></span><div><div class="st-k">run</div><div class="st-v" id="stamp"></div></div></div><button class="tgl" id="theme">◐</button></div></div><nav class="tabs"><button class="tab active" data-view="simple">Vue simple</button><button class="tab" data-view="operational">Opérationnel</button><button class="tab" data-view="radar">Carte Europe</button><button class="tab" data-view="countries">Pays</button><button class="tab" data-view="corridors">Corridors</button><button class="tab" data-view="sources">Sources</button><button class="tab" data-view="expert">Expert</button><a class="tab" href="index.html">Belgique</a><a class="tab" href="methodology.html">Méthodologie</a></nav></header>
<main><div class="disclaimer"><b>Prototype non officiel.</b> Page Europe amont. Les cartes et interfaces ne remplacent pas les services météorologiques nationaux.</div><section class="view active" id="view-simple"></section><section class="view" id="view-operational"></section><section class="view" id="view-radar"></section><section class="view" id="view-countries"></section><section class="view" id="view-corridors"></section><section class="view" id="view-sources"></section><section class="view" id="view-expert"></section></main><footer id="foot"></footer>
<script id="europe-bootstrap" type="application/json">__EUROPE_BOOTSTRAP__</script>
<script>
const M=JSON.parse(document.getElementById('europe-bootstrap').textContent);const esc=s=>String(s==null?'':s).replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));const pct=v=>v==null?'n/a':Math.round(Math.max(0,Math.min(1,Number(v)||0))*100)+'%';const num=v=>v==null?'n/a':(typeof v==='number'?v.toFixed(2):v);const bar=v=>`<div class="bar"><span style="width:${Math.round(Math.max(0,Math.min(1,Number(v)||0))*100)}%"></span></div>`;function badge(txt,kind){return `<span class="badge ${kind||'info'}">${esc(txt)}</span>`}
function kpis(){const s=M.summary||{};return `<div class="kpis"><div class="kpi"><div class="k">Pays suivis</div><div class="v">${esc(s.country_count||0)}</div></div><div class="kpi"><div class="k">Sources radar</div><div class="v">${esc(s.source_count||0)}</div></div><div class="kpi"><div class="k">Interfaces prêtes</div><div class="v">${esc(s.configured_source_count||0)}</div></div><div class="kpi"><div class="k">Preuve machine</div><div class="v">${esc(s.machine_country_count||0)}</div></div><div class="kpi"><div class="k">Clés manquantes</div><div class="v">${esc(s.missing_api_key_count||0)}</div></div></div>`}
function renderSimple(){const s=M.simple||{};return `<div class="hero"><div class="hero-grid"><div><div class="eyebrow">Vue simple Europe</div><h2>Europe amont</h2><p class="eyebrow">Source → radar → métrique → corridor</p><p class="lead">${esc(s.synthesis)}</p><div class="hero-tags"><span class="pill">Espagne</span><span class="pill">France</span><span class="pill">Suisse</span><span class="pill">Pays-Bas</span><span class="pill">RainViewer</span><span class="pill">OPERA ORD</span></div></div><div class="card"><div class="eyebrow">Disponibilité radar</div><div class="score ${s.machine_country_count?'ok':'watch'}">${esc(s.machine_country_count||0)}/${esc(s.country_count||0)}</div><p class="muted">Pays avec métriques machine. Les autres restent en interface prête ou affichage.</p>${bar(s.readiness_score)}</div></div></div>${kpis()}<div class="grid cards3"><div class="card"><h3>Ce que la page Europe ajoute</h3><p class="muted">Une lecture amont par pays, par source radar, par corridor, et par niveau de preuve.</p></div><div class="card"><h3>Ce que cela ne dit pas</h3><p class="muted">Une carte affichée ou un endpoint référencé ne suffit pas. Il faut une trame radar lue pour obtenir une preuve machine.</p></div><div class="card"><h3>Lien Belgique</h3><p class="muted">France et Pays-Bas sont les couloirs les plus directs. Espagne et Suisse enrichissent la lecture dynamique.</p></div></div>`}
function renderOperational(){const chain=(M.operational&&M.operational.chain)||[];return `<div class="section-title">Chaîne de preuve radar</div><div class="chain">${chain.map((x,i)=>`<div class="card step"><div class="n">${i+1}</div><h3>${esc(x.step)}</h3><p class="muted">${esc(x.text)}</p>${bar(x.score)}</div>`).join('')}</div><div class="section-title">Pourquoi ces pays</div><div class="grid cards2">${((M.operational&&M.operational.why_it_matters)||[]).map(x=>`<div class="card"><p>${esc(x)}</p></div>`).join('')}</div>`}
function layerCard(x){return `<div class="card"><div class="eyebrow">${esc(x.evidence_level)}</div><h3>${esc(x.label)}</h3><p class="muted">${esc(x.role)}</p><div class="dl"><span>Statut</span><b>${esc(x.status)}</b></div><div class="dl"><span>Lecture</span><b>${esc(x.meaning)}</b></div><div class="links"><a href="${esc(x.file)}">Ouvrir</a></div></div>`}
function renderRadar(){return `<div class="section-title">Carte Europe</div><div class="grid cards2"><div class="card iframe-card"><iframe src="reports/latest/european_national_radar_map.html" title="Carte radars nationaux Europe"></iframe></div><div class="card"><div class="eyebrow">Carte Europe</div><h2>Radars et couches amont</h2><p class="muted">Cette carte affiche les pays et zones radar surveillés. Elle est liée aux sources et aux corridors, pas seulement posée comme image isolée.</p><div class="links"><a href="reports/latest/european_national_radar_map.html">Carte nationale Europe</a><a href="reports/latest/rainviewer_radar_map.html">RainViewer</a><a href="reports/latest/european_upstream_map.html">Europe amont</a><a href="reports/latest/european_national_radar_report.md">Rapport</a></div></div></div><div class="section-title">Couches radar et fallback</div><div class="grid cards4">${(M.radar_layers||[]).map(layerCard).join('')}</div>`}
function countryCard(c){const status=c.machine_radar_available?badge('preuve machine','ok'):badge('interface prête','watch');return `<article class="card country-card"><div class="country-head"><div class="country-title"><div><div class="eyebrow">${esc(c.iso2||'')}</div><h2>${esc(c.label)}</h2></div>${status}</div><p class="muted">${esc(c.belgium_relevance||c.upstream_role||'')}</p></div><div class="country-body"><div class="grid cards2"><div>${bar(c.completeness_score)}<p class="muted">Complétude ${pct(c.completeness_score)}</p></div><div>${bar(c.readiness_score)}<p class="muted">Préparation ${pct(c.readiness_score)}</p></div></div><div class="dl"><span>Sources</span><b>${esc(c.source_count)} dont ${esc(c.configured_source_count)} prêtes</b></div><div class="dl"><span>National / display / nowcast / OPERA</span><b>${esc(c.national_source_count)} / ${esc(c.display_source_count)} / ${esc(c.nowcast_source_count)} / ${esc(c.opera_fallback_count)}</b></div><div class="dl"><span>Fichiers lisibles</span><b>${esc(c.readable_file_count)} / ${esc(c.file_count)}</b></div><div class="dl"><span>Corridor</span><b>${esc(c.corridor_family||'')}</b></div><div class="section-title">Zones à suivre</div><div class="hero-tags">${(c.watch_zones||[]).map(z=>`<span class="pill">${esc(z)}</span>`).join('')}</div><div class="section-title">Sources</div><div class="src-list">${(c.sources||[]).map(s=>`<div class="src"><div class="src-top"><b>${esc(s.provider)}</b>${badge(s.bucket||s.evidence_level,s.bucket==='machine'?'ok':(s.bucket==='blocked'?'watch':'info'))}</div><p class="muted small">${esc(s.role)} · ${esc(s.status)} · ${esc(s.expected_format||'')}</p>${s.api_key_env?`<p class="muted small">Clé : ${esc(s.api_key_env)} ${s.api_key_configured?'configurée':'manquante'}</p>`:''}</div>`).join('')}</div><div class="section-title">Blocages</div><ul>${(c.blockers||[]).map(b=>`<li>${esc(b)}</li>`).join('')}</ul></div></article>`}
function renderCountries(){return `<div class="section-title">Pays au même niveau de lecture</div><div class="country-grid">${(M.countries||[]).map(countryCard).join('')}</div>`}
function renderCorridors(){const rows=M.corridors||[];return `<div class="card"><h2>Corridors amont vers la Belgique</h2><p class="muted">Le but n'est pas de surveiller l'Europe pour elle-même, mais de relier les zones radar aux trajectoires possibles vers la Belgique.</p></div><div class="card" style="overflow:auto;margin-top:14px"><table><thead><tr><th>Corridor</th><th>Score</th><th>Source</th><th>Cibles</th><th>Fenêtre</th><th>Lecture</th></tr></thead><tbody>${rows.map(c=>`<tr><td><b>${esc(c.name||c.id)}</b><p class="muted small">${esc(c.id||'')}</p></td><td>${num(c.score)}</td><td>${esc(c.source_region||'')}</td><td>${esc((c.target_zones||[]).join(', '))}</td><td>${esc((c.estimated_arrival_hours||[]).join(' à '))}</td><td>${esc(c.interpretation||'')}</td></tr>`).join('')}</tbody></table></div>`}
function renderSources(){const rows=M.sources||[];return `<div class="section-title">Registre radar complet</div><div class="card" style="overflow:auto"><table><thead><tr><th>Pays</th><th>Fournisseur</th><th>Rôle</th><th>Statut</th><th>Preuve</th><th>Format</th><th>Clé</th><th>Référence</th></tr></thead><tbody>${rows.map(s=>`<tr><td><b>${esc(s.country)}</b></td><td>${esc(s.provider)}</td><td>${esc(s.role||'')}</td><td>${esc(s.status||'')}</td><td>${esc(s.evidence_level||'')}</td><td>${esc(s.expected_format||'')}</td><td>${s.api_key_env?esc(s.api_key_env)+(s.api_key_configured?' configurée':' manquante'):'aucune'}</td><td>${s.public_reference?`<a href="${esc(s.public_reference)}">source</a>`:'-'}</td></tr>`).join('')}</tbody></table></div>`}
function renderExpert(){return `<div class="grid cards2"><div class="card"><h2>Exports Europe</h2><div class="links">${(M.exports||[]).map(x=>`<a href="${esc(x.href)}">${esc(x.label)}</a>`).join('')}</div></div><div class="card"><h2>Contrat</h2><p class="muted">${esc(M.page_contract)}</p><p class="muted">Run ${esc(M.run_id)} · ${esc(M.generated_at)} · mode ${esc(M.data_mode)}</p></div></div><div class="section-title">JSON brut</div><pre>${esc(JSON.stringify(M,null,2))}</pre>`}
function paint(){document.getElementById('stamp').textContent=M.generated_at||'n/a';document.getElementById('view-simple').innerHTML=renderSimple();document.getElementById('view-operational').innerHTML=renderOperational();document.getElementById('view-radar').innerHTML=renderRadar();document.getElementById('view-countries').innerHTML=renderCountries();document.getElementById('view-corridors').innerHTML=renderCorridors();document.getElementById('view-sources').innerHTML=renderSources();document.getElementById('view-expert').innerHTML=renderExpert();document.getElementById('foot').innerHTML=`MeteoVoid Europe · ${esc(M.generated_at||'')} · <a href="index.html">Belgique</a> · <a href="api/europe.json">API Europe</a>`}
document.querySelectorAll('.tab[data-view]').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));b.classList.add('active');document.querySelectorAll('.view').forEach(v=>v.classList.toggle('active',v.id==='view-'+b.dataset.view));scrollTo({top:0,behavior:'smooth'})}));document.getElementById('theme').onclick=()=>{document.documentElement.dataset.theme=document.documentElement.dataset.theme==='dark'?'light':'dark'};paint();
</script>
</body>
</html>"""


def _write_europe_page_legacy(site_dir: Path, model: dict[str, Any]) -> None:
    bootstrap = json.dumps(model, ensure_ascii=False).replace("</", "<\\/")
    page = EUROPE_MAX_TEMPLATE.replace("__EUROPE_BOOTSTRAP__", bootstrap)
    (site_dir / "europe.html").write_text(page, encoding="utf-8")


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
