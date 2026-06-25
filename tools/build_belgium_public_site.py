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
import csv
import hashlib
import json
import math
import os
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SRC = Path(__file__).resolve().parents[1] / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
from meteovoid.deep_platform import build_deep_platform_api  # noqa: E402
from meteovoid.europe_country import build_all_countries  # noqa: E402
from meteovoid.europe_sources import (  # noqa: E402
    build_europe_sources_api,
    public_profile_for_country,
)
from meteovoid.model_compare import build_model_compare_api  # noqa: E402
from meteovoid.radar_sources import build_source_registry  # noqa: E402

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
    "validation_history.json",
    "forecast_history.csv",
    "weather_5days.json",
    "weather_5days.md",
    "official_geodata_status.json",
    "belgium_boundaries_provinces.geojson",
    "belgium_boundaries_municipalities.geojson",
    "self_watchdog.json",
    "observation_gap_status.json",
    "nowcast_status.json",
    "belgium_alert_map.html",
    "belgium_weather_layers.html",
    "belgium_radar_map.html",
    "belgium_native_convective_map.html",
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
    "native_convective_parameters.json",
    "native_convective_grid.csv",
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
    "live_smoke_latest.json",
    "live_smoke_latest_enriched.json",
    "live_smoke_bulletin.json",
    "live_smoke_bulletin.md",
    "live_smoke_history.csv",
    "live_smoke_history.jsonl",
    "live_smoke_compose.log",
    "live_smoke_ps.txt",
    "live_smoke_fig_score.png",
    "live_smoke_fig_incoherence.png",
    "live_smoke_fig_contributions.png",
]

# Expert deep-dive frames, grouped "by usage" (point 3 of the redesign).
EXPERT_FRAMES = [
    ("Cartes", "Risque par station", "belgium_alert_map.html"),
    ("Cartes", "Provinces", "belgium_province_map.html"),
    ("Cartes", "Atmosphère lourde", "belgium_humidity_map.html"),
    ("Cartes", "Point de rosée", "belgium_dewpoint_map.html"),
    ("Cartes", "Formation orageuse", "belgium_storm_formation_map.html"),
    ("Cartes", "Convectif natif", "belgium_native_convective_map.html"),
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
    ("Grille convective native CSV", "native_convective_grid.csv"),
    ("Paramètres convectifs natifs", "native_convective_parameters.json"),
    ("Transition par station CSV", "convective_transition_by_station.csv"),
    ("API latest JSON", "../api/latest.json"),
    ("API stations JSON", "../api/stations.json"),
    ("API timeline JSON", "../api/timeline.json"),
    ("API transition JSON", "../api/transition.json"),
    ("API sources JSON", "../api/sources.json"),
    ("API validation JSON", "../api/validation.json"),
    ("API bulletin 5 jours", "../api/weather_5days.json"),
    ("Bulletin 5 jours Markdown", "weather_5days.md"),
    ("Validation historique", "validation_history.json"),
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
    """Return normalized severity metadata.

    Public view-model fragments can carry either a raw severity key
    (``"alert"``, ``"high"``, ``"watch_reinforced"``) or an already
    normalized severity object. Accept both forms so the bulletin never leaks
    a Python dictionary representation into user-facing text.
    """
    if isinstance(key, dict):
        lowered = {str(k).lower(): v for k, v in key.items()}
        raw_key = str(lowered.get("key") or lowered.get("level") or "normal").lower()
        raw_cls = str(lowered.get("class") or _KEY_TO_CLASS.get(raw_key, "calm")).lower()
        cls = raw_cls if raw_cls in _CLASS_RANK else _KEY_TO_CLASS.get(raw_key, "calm")
        raw_label = lowered.get("label")
        label = (
            str(raw_label)
            if raw_label not in (None, "")
            else _KEY_TO_LABEL.get(raw_key, raw_key.replace("_", " ").title())
        )
        raw_rank = lowered.get("rank")
        try:
            rank = int(raw_rank) if raw_rank is not None else _CLASS_RANK.get(cls, 0)
        except (TypeError, ValueError):
            rank = _CLASS_RANK.get(cls, 0)
        return {"key": raw_key, "label": label, "class": cls, "rank": rank}

    key = str(key or "normal").lower()
    cls = _KEY_TO_CLASS.get(key, "calm")
    return {
        "key": key,
        "label": _KEY_TO_LABEL.get(key, key.replace("_", " ").title()),
        "class": cls,
        "rank": _CLASS_RANK.get(cls, 0),
    }


def _is_upstream_zone_name(name: Any) -> bool:
    return str(name or "").strip().lower().startswith("approche ")


def _score_label(value: Any) -> str:
    out = _round(value, 3)
    return "—" if out is None else f"{out:.3f}"


def _bulletin_zone_item(row: dict[str, Any], name_key: str = "province") -> str:
    name = str(row.get(name_key) or row.get("name") or row.get("id") or "—")
    label = _meta(row.get("severity") or row.get("level")).get("label")
    score = _score_label(row.get("max_score") if "max_score" in row else row.get("score"))
    return f"{name} · {label} ({score})"


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
    real_provinces = [p for p in usable if not _is_upstream_zone_name(p.get("province"))]
    candidate_pool = real_provinces or usable
    if candidate_pool:
        top = max(candidate_pool, key=lambda p: _num(p.get("max_score"), 0.0) or 0.0)
        return {
            "name": str(top.get("province") or "—"),
            "score": _round(top.get("max_score")),
            "severity": _meta(top.get("severity")),
            "top_station": str(top.get("top_station") or ""),
            "scope": "belgium" if top in real_provinces else "upstream",
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
        "live_convective_inputs": s.get("live_convective_inputs") or {},
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
        "regional_weather": _weather_region_summary(report),
        "advice": _heat_advice(rank),
        "notable": rank >= 3,
        "note": (
            "La chaleur (lourdeur thermique) est mesurée séparément du risque "
            "convectif. Une atmosphère chaude et humide n’implique pas un orage "
            "imminent ; les deux couches sont suivies indépendamment."
        ),
    }


_REGION_LABELS = {
    "belgium_coast": "Côte belge",
    "belgium_north": "Nord / Anvers",
    "belgium_northeast": "Nord-Est / Limbourg",
    "belgium_northwest": "Nord-Ouest / Flandre orientale",
    "belgium_center": "Centre / Bruxelles - Brabant",
    "belgium_west": "Ouest / Hainaut occidental",
    "belgium_southwest": "Sud-Ouest / Hainaut",
    "belgium_south": "Sud / Namur",
    "belgium_east": "Est / Liège",
    "belgium_southeast": "Sud-Est / Luxembourg",
}


def _is_belgian_region(region: Any) -> bool:
    return str(region or "").startswith("belgium_")


def _region_label(region: Any) -> str:
    key = str(region or "").strip()
    if key in _REGION_LABELS:
        return _REGION_LABELS[key]
    if key.startswith("belgium_"):
        return key.replace("belgium_", "").replace("_", " ").title()
    return key.replace("_", " ").title() or "Région non précisée"


def _weather_region_summary(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Summarise current/forecast weather by Belgian region from station maxima.

    The public bulletin needs a real weather reading, not only a risk score.  This
    is still derived from the same Open-Meteo station grid used by the alert
    engine, and upstream approach points are deliberately excluded.
    """
    grouped: dict[str, list[dict[str, Any]]] = {}
    for station in _stations(report):
        region = str(station.get("region") or "").strip()
        if not _is_belgian_region(region):
            continue
        grouped.setdefault(region, []).append(station)

    rows: list[dict[str, Any]] = []
    for region, stations in grouped.items():
        top_temp = max(stations, key=lambda s: _num(s.get("max_temperature_c"), -99.0) or -99.0)
        top_risk = max(stations, key=lambda s: _num(s.get("score"), -1.0) or -1.0)
        temp = _num(top_temp.get("max_temperature_c"))
        dew = _num(top_temp.get("max_dew_point_c"))
        humidex = _humidex(temp, dew)
        rows.append(
            {
                "region": region,
                "label": _region_label(region),
                "station_count": len(stations),
                "representative_station": top_temp.get("name") or top_temp.get("station_id"),
                "top_risk_station": top_risk.get("name") or top_risk.get("station_id"),
                "temperature_c": _round(temp, 1),
                "dew_point_c": _round(dew, 1),
                "humidex": humidex,
                "humidity_pct": _round(top_temp.get("max_relative_humidity_pct"), 0),
                "precip_prob_pct": _round(
                    max(_num(s.get("max_precip_probability_pct"), 0.0) or 0.0 for s in stations),
                    0,
                ),
                "wind_gust_ms": _round(
                    max(_num(s.get("max_wind_gust_ms"), 0.0) or 0.0 for s in stations),
                    1,
                ),
                "score": _round(top_risk.get("score"), 3),
                "severity": _meta(top_risk.get("severity")),
            }
        )
    rows.sort(key=lambda r: _num(r.get("temperature_c"), -99.0) or -99.0, reverse=True)
    return rows


def _data_quality_summary(report: dict[str, Any]) -> dict[str, Any]:
    """Expose data-quality signals already present in Belgium Alert Watch."""
    stations = _stations(report)
    rows: list[dict[str, Any]] = []
    flatline_count = 0
    spatial_count = 0
    source_error_count = 0
    missing_native_count = 0

    for station in stations:
        signals = [str(x).lower() for x in (station.get("signals") or [])]
        joined = " ".join(signals)
        source_ok = bool(station.get("source_ok", True))
        native = bool(station.get("native_convective_available", False))
        flatline = any(word in joined for word in ("flatline", "plateau", "stagne", "bloqué"))
        spatial = any(word in joined for word in ("spatial", "voisine", "cohérence"))
        if flatline:
            flatline_count += 1
        if spatial:
            spatial_count += 1
        if not source_ok:
            source_error_count += 1
        if not native:
            missing_native_count += 1
        if flatline or spatial or not source_ok or not native:
            rows.append(
                {
                    "station_id": station.get("station_id"),
                    "name": station.get("name"),
                    "region": station.get("region"),
                    "score": _round(station.get("score"), 3),
                    "flatline_suspected": flatline,
                    "spatial_incoherence_suspected": spatial,
                    "source_ok": source_ok,
                    "native_convective_available": native,
                    "signals": station.get("signals") or [],
                }
            )

    return {
        "contract": "meteovoid_data_quality_summary_v1",
        "station_count": len(stations),
        "flatline_station_count": flatline_count,
        "spatial_incoherence_station_count": spatial_count,
        "source_error_station_count": source_error_count,
        "missing_native_convective_station_count": missing_native_count,
        "flagged_stations": rows[:30],
        "implemented_checks": [
            "void_gap_detection",
            "flatline_detection_core_and_live_signal",
            "interstation_spatial_std_context_live",
            "source_status_consistency",
            "native_convective_availability",
        ],
        "note": (
            "Flatline/spatial counts are exact when live reports expose those signals; "
            "for static Belgium Alert Watch runs, they are derived from station signal text "
            "and source availability rather than invented measurements."
        ),
    }


def _build_bulletin(vm: dict[str, Any]) -> dict[str, Any]:
    """Assemble a public, prose weather bulletin from the Belgium view-model.

    Pure synthesis of fields already computed for the page: operational level,
    sensitive window, leading zone, heat layer and key signals. It stays in the
    prudent MeteoVoid wording and never invents an official alert.
    """
    meta = vm.get("meta", {}) if isinstance(vm.get("meta"), dict) else {}
    simple = vm.get("simple", {}) if isinstance(vm.get("simple"), dict) else {}
    heat = vm.get("heat", {}) if isinstance(vm.get("heat"), dict) else {}
    expert = vm.get("expert", {}) if isinstance(vm.get("expert"), dict) else {}

    level = (
        simple.get("operational_level", {})
        if isinstance(simple.get("operational_level"), dict)
        else {}
    )
    window = (
        simple.get("critical_window", {}) if isinstance(simple.get("critical_window"), dict) else {}
    )
    zone = simple.get("main_zone", {}) if isinstance(simple.get("main_zone"), dict) else {}
    layers = simple.get("score_layers", {}) if isinstance(simple.get("score_layers"), dict) else {}
    window_phrase = _window_phrase(window)

    level_label = str(level.get("label") or "Veille")
    level_key = str(level.get("key") or "calm")
    headline = f"Veille MeteoVoid : niveau {level_label.lower()}"
    if level_key in {"calm", "normal", "stable"}:
        headline = "Veille MeteoVoid : situation calme, pas de bascule imminente"

    sections: list[dict[str, Any]] = []
    sections.append(
        {
            "title": "Situation générale",
            "body": str(simple.get("synthesis") or simple.get("public_wording") or "")
            or "Pas de dynamique de bascule notable sur la fenêtre surveillée.",
        }
    )
    zone_name = str(zone.get("name") or "—")
    sections.append(
        {
            "title": "Fenêtre sensible et zone principale",
            "body": (
                f"Fenêtre la plus sensible {window_phrase}. "
                f"Zone à suivre en priorité : {zone_name}. "
                f"Score interne {layers.get('convective_risk_score') if layers else '—'} "
                "(risque convectif), distinct de la lourdeur thermique."
            ),
        }
    )

    heat_level = heat.get("level", {}) if isinstance(heat.get("level"), dict) else {}
    heat_advice = [str(a) for a in (heat.get("advice") or [])][:3]
    sections.append(
        {
            "title": "Chaleur et humidité",
            "body": (
                f"Charge thermique : {heat_level.get('label') or 'non notable'}. "
                f"Température max {heat.get('max_temperature_c')} °C, "
                f"humidex {heat.get('max_humidex')} vers {heat.get('peak_hour') or '—'}."
            ),
            "advice": heat_advice,
        }
    )

    regional_weather = (
        heat.get("regional_weather") if isinstance(heat.get("regional_weather"), list) else []
    )
    convective_inputs = (
        expert.get("convective_live_inputs")
        if isinstance(expert.get("convective_live_inputs"), dict)
        else {}
    )
    convective_fields = (
        convective_inputs.get("fields") if isinstance(convective_inputs.get("fields"), dict) else {}
    )

    def _live_field_value(key: str) -> float | None:
        field = convective_fields.get(key)
        if not isinstance(field, dict) or field.get("available") is not True:
            return None
        return _num(field.get("value"))

    temperatures = [
        _num(row.get("temperature_c"))
        for row in regional_weather
        if isinstance(row, dict) and _num(row.get("temperature_c")) is not None
    ]
    dew_points = [
        _num(row.get("dew_point_c"))
        for row in regional_weather
        if isinstance(row, dict) and _num(row.get("dew_point_c")) is not None
    ]
    humidex_values = [
        _num(row.get("humidex"))
        for row in regional_weather
        if isinstance(row, dict) and _num(row.get("humidex")) is not None
    ]
    precip_probs = [
        _num(row.get("precip_prob_pct"))
        for row in regional_weather
        if isinstance(row, dict) and _num(row.get("precip_prob_pct")) is not None
    ]
    gust_values = [
        _num(row.get("wind_gust_ms"))
        for row in regional_weather
        if isinstance(row, dict) and _num(row.get("wind_gust_ms")) is not None
    ]
    pressure = _live_field_value("pressure_hpa")
    cape = _live_field_value("cape_jkg")
    cin = _live_field_value("cin_jkg")
    shear = _live_field_value("shear_0_6km_ms")
    pwat = _live_field_value("pwat_mm")
    classic_bits = []
    if temperatures:
        classic_bits.append(
            f"températures régionales de {_round(min(temperatures), 1)} à "
            f"{_round(max(temperatures), 1)} °C"
        )
    if humidex_values:
        classic_bits.append(f"humidex max {_round(max(humidex_values), 1)}")
    if dew_points:
        classic_bits.append(f"point de rosée max {_round(max(dew_points), 1)} °C")
    if precip_probs:
        classic_bits.append(f"probabilité de pluie max {_round(max(precip_probs), 0)} %")
    if gust_values:
        classic_bits.append(f"rafales max {_round(max(gust_values), 1)} m/s")
    if pressure is not None:
        classic_bits.append(f"pression {_round(pressure, 1)} hPa")
    if classic_bits:
        convective_bits = []
        if cape is not None:
            convective_bits.append(f"CAPE {_round(cape, 0)} J/kg")
        if cin is not None:
            convective_bits.append(f"CIN {_round(cin, 0)} J/kg")
        if shear is not None:
            convective_bits.append(f"cisaillement 0–6 km {_round(shear, 1)} m/s")
        if pwat is not None:
            convective_bits.append(f"PWAT {_round(pwat, 1)} mm")
        body = "Bulletin classique du dernier run : " + "; ".join(classic_bits) + "."
        if convective_bits:
            body += (
                " Ingrédients convectifs réels disponibles : " + "; ".join(convective_bits) + "."
            )
        sections.append(
            {
                "title": "Bulletin météo classique Belgique",
                "body": body,
                "note": (
                    "Lecture classique issue des stations et champs réellement disponibles dans le "
                    "dernier run. Les ingrédients convectifs absents restent marqués manquants "
                    "dans l’onglet expert, sans simulation."
                ),
            }
        )

    regional_items = []
    for row in regional_weather[:12]:
        if not isinstance(row, dict):
            continue
        temp = _score_label(row.get("temperature_c")).replace(".", ",")
        humidex = _score_label(row.get("humidex")).replace(".", ",")
        dew = _score_label(row.get("dew_point_c")).replace(".", ",")
        precip = _score_label(row.get("precip_prob_pct")).replace(".", ",")
        gust = _score_label(row.get("wind_gust_ms")).replace(".", ",")
        station = str(row.get("representative_station") or "—")
        regional_items.append(
            f"{row.get('label') or 'Région'} · {temp} °C, "
            f"humidex {humidex}, rosée {dew} °C, pluie {precip} %, "
            f"rafales {gust} m/s · station : {station}"
        )
    if regional_items:
        sections.append(
            {
                "title": "Températures par région belge",
                "items": regional_items,
                "note": (
                    "Ces valeurs proviennent du maillage de stations MeteoVoid/Open‑Meteo "
                    "utilisé pour le run courant. Les points d’approche hors Belgique sont exclus."
                ),
            }
        )

    weather_5days = vm.get("weather_5days") if isinstance(vm.get("weather_5days"), dict) else {}
    national_days = (
        weather_5days.get("national_days")
        if isinstance(weather_5days.get("national_days"), list)
        else []
    )
    if national_days:
        day_items = []
        for day in national_days[:5]:
            if not isinstance(day, dict):
                continue
            day_items.append(
                f"{day.get('date') or '—'} · {day.get('weather_label') or 'temps variable'} · "
                f"{day.get('temperature_min_c')} / {day.get('temperature_max_c')} °C · "
                f"pluie max {day.get('precipitation_probability_max_pct')} % · "
                f"rafales {day.get('wind_gust_max_kmh')} km/h · {day.get('risk_note') or ''}"
            )
        sections.append(
            {
                "title": "Prévision classique à 5 jours",
                "body": str(weather_5days.get("summary") or ""),
                "items": day_items,
                "note": str(
                    weather_5days.get("disclaimer") or "Bulletin automatique non officiel."
                ),
            }
        )

    zone_forecasts = (
        weather_5days.get("zones") if isinstance(weather_5days.get("zones"), list) else []
    )
    if zone_forecasts:
        zone_items = []
        for zone_item in zone_forecasts[:8]:
            if not isinstance(zone_item, dict):
                continue
            days = zone_item.get("days") if isinstance(zone_item.get("days"), list) else []
            first = days[0] if days and isinstance(days[0], dict) else {}
            zone_items.append(
                f"{zone_item.get('label') or zone_item.get('key') or 'Zone'} · "
                f"{first.get('weather_label') or 'temps variable'} · "
                f"max {first.get('temperature_2m_max', '—')} °C · "
                f"pluie {first.get('precipitation_probability_max', '—')} % · "
                f"rafales {first.get('wind_gusts_10m_max', '—')} km/h"
            )
        sections.append(
            {
                "title": "Bulletin 5 jours par zone",
                "items": zone_items,
                "note": "Zones représentatives : elles ne remplacent pas les zones d’avertissement officielles IRM/KMI.",
            }
        )

    validation_history = (
        vm.get("validation_history") if isinstance(vm.get("validation_history"), dict) else {}
    )
    if validation_history:
        scores = (
            validation_history.get("scores")
            if isinstance(validation_history.get("scores"), dict)
            else {}
        )
        sections.append(
            {
                "title": "Validation historique",
                "body": (
                    f"Statut : {validation_history.get('status') or 'non renseigné'}. "
                    f"Runs stockés : {validation_history.get('stored_run_count', 0)} ; "
                    f"runs évalués : {validation_history.get('evaluated_run_count', 0)}. "
                    f"Brier : {scores.get('brier_score') if scores else 'n/a'}, "
                    f"CSI : {scores.get('csi') if scores else 'n/a'}."
                ),
                "note": str(
                    validation_history.get("note") or "Les scores exigent des événements vérifiés."
                ),
            }
        )

    provinces = expert.get("provinces") if isinstance(expert.get("provinces"), list) else []
    real_zones = [
        p
        for p in provinces
        if isinstance(p, dict) and not _is_upstream_zone_name(p.get("province"))
    ]
    upstream_zones = [
        p for p in provinces if isinstance(p, dict) and _is_upstream_zone_name(p.get("province"))
    ]

    zone_items = [_bulletin_zone_item(p) for p in real_zones[:6]]
    if zone_items:
        sections.append({"title": "Zones belges à surveiller", "items": zone_items})

    upstream_items = [_bulletin_zone_item(p) for p in upstream_zones[:4]]
    if upstream_items:
        sections.append(
            {
                "title": "Couloirs amont à surveiller",
                "items": upstream_items,
                "note": (
                    "Ces zones d’approche ne sont pas des provinces belges : "
                    "elles servent à lire ce qui arrive depuis les pays voisins."
                ),
            }
        )

    signals = [str(s) for s in (simple.get("headline_signals") or [])][:4]
    if signals:
        sections.append({"title": "Signaux clés", "items": signals})

    return {
        "contract": "meteovoid_belgium_bulletin_v1",
        "title": "Bulletin de veille MeteoVoid Belgique",
        "headline": headline,
        "level": level,
        "issued_at": meta.get("generated_at"),
        "timezone": meta.get("timezone"),
        "validity": window_phrase,
        "summary": str(simple.get("synthesis") or ""),
        "public_wording": simple.get("public_wording") or meta.get("public_wording"),
        "sections": sections,
        "confidence": simple.get("confidence"),
        "advice": heat_advice,
        "non_official": True,
        "disclaimer": meta.get("disclaimer"),
    }


def _copy_if_exists(src: Path, dst: Path) -> None:
    if src.exists() and src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _ingest_optional_artifacts(
    report_dir: Path,
    live_smoke_dir: Path | None = None,
    opera_ord_dir: Path | None = None,
) -> None:
    """Merge optional workflow artifacts into the public report directory.

    Belgium Pages can be built from the Belgium Alert Watch artifact alone.  When
    Live Smoke or OPERA ORD artifacts are available, this helper imports their
    compact JSON/Markdown/log outputs with stable names so the public API and UI
    can expose them without guessing GitHub artifact layouts.
    """
    if live_smoke_dir and live_smoke_dir.exists():
        mapping = {
            "latest.json": "live_smoke_latest.json",
            "latest_enriched.json": "live_smoke_latest_enriched.json",
            "bulletin.json": "live_smoke_bulletin.json",
            "bulletin.md": "live_smoke_bulletin.md",
            "history.csv": "live_smoke_history.csv",
            "history.jsonl": "live_smoke_history.jsonl",
            "compose.log": "live_smoke_compose.log",
            "ps.txt": "live_smoke_ps.txt",
            "fig_score.png": "live_smoke_fig_score.png",
            "fig_incoherence.png": "live_smoke_fig_incoherence.png",
            "fig_contributions.png": "live_smoke_fig_contributions.png",
        }
        for src_name, dst_name in mapping.items():
            _copy_if_exists(live_smoke_dir / src_name, report_dir / dst_name)

    if opera_ord_dir and opera_ord_dir.exists():
        for name in (
            "opera_ord_status.json",
            "opera_ord_inventory.json",
            "opera_ord_files_manifest.json",
            "opera_radar_metrics.json",
        ):
            _copy_if_exists(opera_ord_dir / name, report_dir / name)


def _load_live_smoke(report_dir: Path) -> dict[str, Any]:
    latest = _load_json(report_dir / "live_smoke_latest.json") or _load_json(
        report_dir / "latest.json"
    )
    enriched = _load_json(report_dir / "live_smoke_latest_enriched.json") or _load_json(
        report_dir / "latest_enriched.json"
    )
    bulletin = _load_json(report_dir / "live_smoke_bulletin.json") or _load_json(
        report_dir / "bulletin.json"
    )
    source = enriched or latest or bulletin
    if not source:
        return {
            "contract": "meteovoid_live_smoke_public_v1",
            "available": False,
            "status": "missing",
            "summary": "Aucun artefact Live Smoke n'est disponible dans le run publié.",
            "artefacts": [],
        }

    signals = source.get("signals") if isinstance(source.get("signals"), dict) else {}
    contributions = (
        source.get("contributions") if isinstance(source.get("contributions"), dict) else {}
    )
    stats = source.get("stats") if isinstance(source.get("stats"), dict) else {}
    meteo = source.get("meteo") if isinstance(source.get("meteo"), dict) else {}
    incoherence = source.get("incoherence") if isinstance(source.get("incoherence"), dict) else {}
    generated_at = (
        source.get("ts_ingest_iso")
        or source.get("ts_iso")
        or bulletin.get("generated_at")
        or source.get("generated_at")
    )
    artefacts = []
    for label, file_name in (
        ("Live Smoke latest", "live_smoke_latest.json"),
        ("Live Smoke enrichi", "live_smoke_latest_enriched.json"),
        ("Bulletin Live Smoke", "live_smoke_bulletin.md"),
        ("Historique Live Smoke", "live_smoke_history.csv"),
        ("Log Compose", "live_smoke_compose.log"),
        ("Figure score", "live_smoke_fig_score.png"),
        ("Figure incohérence", "live_smoke_fig_incoherence.png"),
        ("Figure contributions", "live_smoke_fig_contributions.png"),
    ):
        if (report_dir / file_name).exists():
            artefacts.append({"label": label, "href": "reports/latest/" + file_name})

    return {
        "contract": "meteovoid_live_smoke_public_v1",
        "available": True,
        "status": source.get("state") or meteo.get("severity") or "available",
        "generated_at": generated_at,
        "station_id": source.get("station_id"),
        "variable": source.get("variable"),
        "stream_id": source.get("stream_id"),
        "score": _round(source.get("score"), 3),
        "incoherence_score": _round(source.get("incoherence_score") or incoherence.get("total"), 3),
        "severity": meteo.get("severity") or bulletin.get("severity"),
        "state": source.get("state") or bulletin.get("state"),
        "flags": meteo.get("flags") or bulletin.get("flags") or [],
        "interpretation": meteo.get("interpretation") or bulletin.get("interpretation"),
        "signals": {
            "flatline": _round(signals.get("flatline"), 3),
            "gap": _round(signals.get("gap"), 3),
            "spatial": _round(signals.get("spatial"), 3),
            "volatility": _round(signals.get("volatility"), 3),
            "drift": _round(signals.get("drift"), 3),
            "outlier": _round(signals.get("outlier"), 3),
        },
        "contributions": {
            "flatline": _round(contributions.get("flatline"), 3),
            "gap": _round(contributions.get("gap"), 3),
            "spatial": _round(contributions.get("spatial"), 3),
            "volatility": _round(contributions.get("volatility"), 3),
            "drift": _round(contributions.get("drift"), 3),
            "outlier": _round(contributions.get("outlier"), 3),
        },
        "stats": {
            "n_points": stats.get("n_points"),
            "window_s": stats.get("window_s"),
            "gap_count": stats.get("gap_count"),
            "gap_max_s": _round(stats.get("gap_max_s"), 3),
            "missing_time_frac": _round(stats.get("missing_time_frac"), 3),
            "imputed_frac": _round(stats.get("imputed_frac"), 3),
            "spatial_context": stats.get("spatial_context"),
        },
        "artefacts": artefacts,
    }


def build_view_model(report_dir: Path) -> dict[str, Any]:
    report = _load_json(report_dir / "belgium_alert_report.json")
    alert_state = _load_json(report_dir / "alert_state.json")
    transition = _load_json(report_dir / "convective_transition_report.json")
    timeseries = _load_json(report_dir / "risk_timeseries.json")
    early_warning = _load_json(report_dir / "early_warning_signals.json")
    info_graph = _load_json(report_dir / "information_graph_summary.json")
    validation = _load_json(report_dir / "validation_metrics.json")
    validation_history = _load_json(report_dir / "validation_history.json")
    weather_5days = _load_json(report_dir / "weather_5days.json")
    geodata_status = _load_json(report_dir / "official_geodata_status.json")
    watchdog = _load_json(report_dir / "self_watchdog.json")
    source_status = _load_json(report_dir / "source_status.json")
    obs_gap = _load_json(report_dir / "observation_gap_status.json")
    nowcast = _load_json(report_dir / "nowcast_status.json")
    upstream = _load_json(report_dir / "upstream_watch.json")
    radar_stack = _load_json(report_dir / "radar_stack.json")
    opera_metrics = _load_json(report_dir / "opera_radar_metrics.json")
    opera_inventory = _load_json(report_dir / "opera_ord_inventory.json")
    opera_status = _load_json(report_dir / "opera_ord_status.json")
    live_smoke = _load_live_smoke(report_dir)
    national_radar = _load_json(report_dir / "european_national_radar_status.json")
    national_radar_metrics = _load_json(report_dir / "european_national_radar_metrics.json")
    convective_live = _load_json(report_dir / "convective_live_inputs.json")
    if not convective_live:
        convective_live = (
            report.get("convective_live_inputs")
            if isinstance(report.get("convective_live_inputs"), dict)
            else {}
        )
    data_quality = _data_quality_summary(report)

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
            "convective_live": "api/convective_live.json",
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
        "validation_history": validation_history,
        "data_quality": data_quality,
        "live_smoke": live_smoke,
        "weather_5days": weather_5days,
        "official_geodata": geodata_status,
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
        "opera_ord_status": opera_status,
        "european_national_radar": (
            national_radar.get("summary") if isinstance(national_radar.get("summary"), dict) else {}
        ),
        "european_national_radar_metrics": national_radar_metrics,
        "convective_live_inputs": convective_live,
        "opera_ord_inventory": {
            "status": opera_status.get("status") or opera_inventory.get("status"),
            "enabled": opera_status.get("enabled", opera_inventory.get("enabled")),
            "machine_radar_confirmation": opera_status.get("machine_radar_confirmation"),
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
        "bulletin": _build_bulletin(
            {
                "meta": meta,
                "simple": simple,
                "operational": operational_view,
                "heat": _build_heat(report),
                "expert": expert,
                "weather_5days": weather_5days,
                "validation_history": validation_history,
            }
        ),
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


def _write_public_manifest(api_dir: Path) -> None:
    items: list[dict[str, Any]] = []
    for path in sorted(api_dir.rglob("*.json")):
        if path.name == "public_manifest.json":
            continue
        rel = path.relative_to(api_dir.parent).as_posix()
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        items.append(
            {
                "path": rel,
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    _write_json(
        api_dir / "public_manifest.json",
        {
            "contract": "meteovoid_public_api_manifest_v1",
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "file_count": len(items),
            "files": items,
            "policy": "Every public JSON endpoint is hashed after build for auditability.",
        },
    )


def _build_alert_watch_api(vm: dict[str, Any]) -> dict[str, Any]:
    """Build a compact public API exposing the whole Belgium Alert Watch state.

    Storm-scope is intentionally a public page, not only a visual shell.  This
    payload gathers the status blocks that Belgium Alert Watch already produces
    so the interface can display them without scraping the raw reports.
    """
    meta = vm.get("meta", {}) if isinstance(vm.get("meta"), dict) else {}
    simple = vm.get("simple", {}) if isinstance(vm.get("simple"), dict) else {}
    operational = vm.get("operational", {}) if isinstance(vm.get("operational"), dict) else {}
    heat = vm.get("heat", {}) if isinstance(vm.get("heat"), dict) else {}
    expert = vm.get("expert", {}) if isinstance(vm.get("expert"), dict) else {}
    validation_history = (
        expert.get("validation_history")
        if isinstance(expert.get("validation_history"), dict)
        else {}
    )
    weather_5days = (
        expert.get("weather_5days") if isinstance(expert.get("weather_5days"), dict) else {}
    )
    convective_live = (
        expert.get("convective_live_inputs")
        if isinstance(expert.get("convective_live_inputs"), dict)
        else {}
    )
    sources = expert.get("sources") if isinstance(expert.get("sources"), dict) else {}
    radar_stack = expert.get("radar_stack") if isinstance(expert.get("radar_stack"), dict) else {}
    upstream_watch = (
        expert.get("upstream_watch") if isinstance(expert.get("upstream_watch"), dict) else {}
    )
    validation = expert.get("validation") if isinstance(expert.get("validation"), dict) else {}
    live_smoke = expert.get("live_smoke") if isinstance(expert.get("live_smoke"), dict) else {}
    opera_status = (
        expert.get("opera_ord_status") if isinstance(expert.get("opera_ord_status"), dict) else {}
    )

    artefacts: list[dict[str, str]] = []
    for frame in expert.get("frames", []):
        if isinstance(frame, dict) and frame.get("file"):
            artefacts.append(
                {
                    "group": str(frame.get("group") or "Analyse"),
                    "label": str(frame.get("label") or frame.get("file")),
                    "href": str(frame.get("file")),
                }
            )
    for export in expert.get("exports", []):
        if isinstance(export, dict) and export.get("file"):
            artefacts.append(
                {
                    "group": "Exports",
                    "label": str(export.get("label") or export.get("file")),
                    "href": str(export.get("file")),
                }
            )
    live_smoke_artefacts = (
        live_smoke.get("artefacts") if isinstance(live_smoke.get("artefacts"), list) else []
    )
    for item in live_smoke_artefacts:
        if isinstance(item, dict) and item.get("href"):
            artefacts.append(
                {
                    "group": "Live Smoke",
                    "label": str(item.get("label") or item.get("href")),
                    "href": str(item.get("href")),
                }
            )

    for label, href in (
        ("Statut OPERA ORD", "reports/latest/opera_ord_status.json"),
        ("Pile radar complète", "reports/latest/radar_stack.json"),
        ("Statut pySTEPS / nowcast", "reports/latest/pysteps_nowcast_status.json"),
        ("Statut RainViewer", "reports/latest/rainviewer_status.json"),
        ("Rapport radars nationaux", "reports/latest/european_national_radar_report.md"),
    ):
        artefacts.append({"group": "Radar", "label": label, "href": href})

    return {
        "contract": "meteovoid_belgium_alert_watch_public_v1",
        "generated_at": meta.get("generated_at"),
        "run_id": meta.get("run_id"),
        "timezone": meta.get("timezone"),
        "data_mode": meta.get("data_mode"),
        "disclaimer": meta.get("disclaimer"),
        "latest": {
            "operational_level": simple.get("operational_level"),
            "severity": simple.get("severity"),
            "model_score": simple.get("model_score"),
            "score_layers": simple.get("score_layers"),
            "confidence": simple.get("confidence"),
            "critical_window": simple.get("critical_window"),
            "main_zone": simple.get("main_zone"),
            "synthesis": simple.get("synthesis"),
            "public_wording": simple.get("public_wording"),
            "official_alert": simple.get("official_alert"),
            "public_alert_allowed": simple.get("public_alert_allowed"),
            "strong_external_confirmation": simple.get("strong_external_confirmation"),
            "transition_level": operational.get("transition_level"),
            "void_collapse_signal": operational.get("void_collapse_signal"),
            "alert_explanation": operational.get("alert_explanation"),
        },
        "heat": heat,
        "convective_live_inputs": convective_live,
        "sources": sources,
        "observation": expert.get("observation"),
        "watchdog": expert.get("watchdog"),
        "early_warning": expert.get("early_warning"),
        "information_graph": expert.get("information_graph"),
        "upstream_watch": upstream_watch,
        "radar_stack": radar_stack,
        "radar": {
            "radar_stack": radar_stack,
            "opera_ord_status": opera_status,
            "opera_radar_metrics": expert.get("opera_radar_metrics"),
            "opera_ord_inventory": expert.get("opera_ord_inventory"),
            "european_national_radar": expert.get("european_national_radar"),
            "european_national_radar_metrics": expert.get("european_national_radar_metrics"),
        },
        "live_smoke": live_smoke,
        "validation": validation,
        "validation_history": validation_history,
        "data_quality": expert.get("data_quality"),
        "weather_5days": {
            "summary": weather_5days.get("summary"),
            "model": weather_5days.get("model"),
            "source": weather_5days.get("source"),
            "national_days": weather_5days.get("national_days"),
            "zones_count": weather_5days.get("zones_count"),
            "errors": weather_5days.get("errors"),
        },
        "official_geodata": expert.get("official_geodata"),
        "artefacts": artefacts,
    }


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
            "scope": "Espagne, France, Suisse, Pays-Bas, Allemagne, Danemark + OPERA ORD + RainViewer",
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


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    """Read an optional CSV artifact without making the public build fragile."""
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except (OSError, csv.Error, UnicodeDecodeError):
        return []


def _series_from_base(base: Any, hours: list[dict[str, Any]]) -> list[float]:
    """Project a static point score on the current Alert Watch hourly envelope.

    This remains only a last-resort fallback. The normal map contract now uses
    station ``hourly_risk`` from ``belgium_alert_report.json`` whenever it is
    available, so the browser play button animates real hourly model values.
    """
    b = _clamp01(base)
    if not hours:
        return [round(b, 3)]
    drivers = []
    for row in hours:
        if not isinstance(row, dict):
            continue
        drivers.append(_clamp01(row.get("max_score") or row.get("score") or row.get("mean_score")))
    peak = max(drivers) if drivers else 0.0
    if peak <= 0:
        return [round(b, 3) for _ in hours]
    out = []
    for driver in drivers:
        factor = 0.5 + 0.5 * (driver / peak)
        out.append(round(_clamp01(b * factor), 3))
    return out


def _norm_key(value: Any) -> str:
    return str(value or "").strip().casefold().replace(" / ", " ").replace("-", " ")


def _station_catalog_by_key() -> dict[str, dict[str, Any]]:
    """Return known station metadata keyed by id and normalized names.

    Some GitHub Pages builds are created from HTML/CSV artifacts only. In that
    case ``belgium_alert_report.json`` is absent, but ``risk_by_station.csv``
    still contains scores. This catalog restores coordinates so the public
    ``api/map_live.json`` can remain linked to the same stations as the UI.
    """
    candidates = [
        Path("config/stations_belgium.yaml"),
        Path(__file__).resolve().parents[1] / "config" / "stations_belgium.yaml",
    ]
    payload: dict[str, Any] = {}
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            import yaml  # type: ignore[import-untyped]

            loaded = yaml.safe_load(candidate.read_text(encoding="utf-8"))
        except Exception:
            loaded = None
        if isinstance(loaded, dict):
            payload = loaded
            break
    by_key: dict[str, dict[str, Any]] = {}
    for station in payload.get("stations", []) if isinstance(payload, dict) else []:
        if not isinstance(station, dict):
            continue
        item = dict(station)
        keys = {
            _norm_key(item.get("id")),
            _norm_key(item.get("name")),
            _norm_key(str(item.get("name") or "").split("/")[0]),
        }
        for key in keys:
            if key:
                by_key[key] = item
    return by_key


def _station_catalog_match(
    row: dict[str, Any], catalog: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    keys = [
        _norm_key(row.get("station_id")),
        _norm_key(row.get("name")),
        _norm_key(str(row.get("name") or "").split("/")[0]),
    ]
    for key in keys:
        if key in catalog:
            return catalog[key]
    for key in keys:
        if not key:
            continue
        for cat_key, item in catalog.items():
            if key in cat_key or cat_key in key:
                return item
    return {}


def _station_rows_from_csv(report_dir: Path) -> list[dict[str, Any]]:
    """Build station rows from ``risk_by_station.csv`` when JSON is missing."""
    rows = _read_csv_rows(report_dir / "risk_by_station.csv")
    if not rows:
        return []
    catalog = _station_catalog_by_key()
    out: list[dict[str, Any]] = []
    for row in rows:
        match = _station_catalog_match(row, catalog)
        lat = _num(row.get("lat")) or _num(match.get("lat"))
        lon = _num(row.get("lon")) or _num(match.get("lon"))
        if lat is None or lon is None:
            continue
        out.append(
            {
                **row,
                "station_id": row.get("station_id") or match.get("id"),
                "name": row.get("name") or match.get("name"),
                "region": row.get("region") or match.get("region"),
                "lat": lat,
                "lon": lon,
                "severity": {"key": row.get("severity") or "normal"},
                "signals": str(row.get("signals") or "").split("; ") if row.get("signals") else [],
            }
        )
    return out


def _constant_series(value: Any, count: int) -> list[float | None]:
    v = _num(value)
    return [round(float(v), 3) if v is not None else None for _ in range(max(count, 1))]


def _hourly_values(
    rows: list[dict[str, Any]],
    key: str,
    hours: list[dict[str, Any]],
    fallback: Any = None,
    digits: int = 3,
) -> list[float | None]:
    by_time = {str(row.get("time") or ""): row for row in rows if isinstance(row, dict)}
    out: list[float | None] = []
    for hour in hours:
        stamp = str(hour.get("time") or "") if isinstance(hour, dict) else ""
        row = by_time.get(stamp, {})
        value = row.get(key, fallback) if isinstance(row, dict) else fallback
        rounded = _round(value, digits)
        out.append(rounded)
    return out or _constant_series(fallback, max(len(hours), 1))


def _hourly_scores(
    rows: list[dict[str, Any]], hours: list[dict[str, Any]], fallback: Any
) -> list[float]:
    values = _hourly_values(rows, "score", hours, fallback, 3)
    return [round(_clamp01(v), 3) for v in values]


def _nearest_station_series(
    nearest: Any,
    station_hourly_by_name: dict[str, list[dict[str, Any]]],
    station_hourly_by_id: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    key = _norm_key(nearest)
    if key in station_hourly_by_name:
        return station_hourly_by_name[key]
    if key in station_hourly_by_id:
        return station_hourly_by_id[key]
    # Some grid rows only contain the short city name, while stations may contain
    # labels like "Jodoigne / Brabant wallon". Use a conservative contains match.
    for name, rows in station_hourly_by_name.items():
        if key and (key in name or name in key):
            return rows
    return []


def _blend_hourly_scores(
    base_score: Any,
    station_rows: list[dict[str, Any]],
    hours: list[dict[str, Any]],
) -> list[float]:
    """Create a grid series from the nearest station's real hourly curve.

    The grid files are currently spatial snapshots. To avoid the old fake global
    projection, each grid point now follows the hourly curve of its nearest
    station, while preserving part of its own spatial intensity. This is honest:
    the output carries ``hourly_source`` so the UI and reports know it is
    nearest-station driven until native hourly gridded files exist.
    """
    b = _clamp01(base_score)
    if not station_rows:
        return _series_from_base(b, hours)
    station_scores = _hourly_scores(station_rows, hours, b)
    peak = max(station_scores) if station_scores else 0.0
    if peak <= 0:
        return [round(b, 3) for _ in hours]
    out = []
    for score in station_scores:
        # 65% true nearest-station hourly signal, 35% local grid snapshot.
        out.append(round(_clamp01(0.65 * score + 0.35 * b), 3))
    return out


def _build_map_live_api(vm: dict[str, Any], report_dir: Path) -> dict[str, Any]:
    """Build the map-first contract consumed by Storm-scope.

    The browser reads this endpoint as the single live state for Belgium. It now
    contains real hourly station series from ``hourly_risk`` and grid series
    derived from the nearest station hourly curve. Radar frames stay explicitly
    separate from the forecast timeline.
    """
    meta = vm["meta"]
    report = _load_json(report_dir / "belgium_alert_report.json")
    timeline_json = _load_json(report_dir / "risk_timeseries.json")
    timeline = vm["operational"].get("timeline", {})
    raw_hours = timeline.get("hours") if isinstance(timeline.get("hours"), list) else []
    if not raw_hours:
        raw_hours = (
            timeline_json.get("timeline") if isinstance(timeline_json.get("timeline"), list) else []
        )
    if not raw_hours:
        raw_hours = _read_csv_rows(report_dir / "risk_timeline.csv")

    hours = []
    for row in raw_hours[:48]:
        if not isinstance(row, dict):
            continue
        stamp = row.get("time") or row.get("hour")
        score = _round(row.get("max_score") or row.get("score") or row.get("mean_score"), 3)
        hours.append(
            {
                "time": stamp,
                "hour": row.get("hour") or _hour_label(stamp),
                "score": score,
                "mean_score": _round(row.get("mean_score"), 3),
                "max_score": _round(row.get("max_score"), 3),
                "severity": row.get("severity") or "normal",
                "class": row.get("class") or _meta(row.get("severity"))["class"],
                "timeline_type": "forecast_model",
            }
        )
    if not hours:
        generated = str(meta.get("generated_at") or "")[:13]
        severity = vm["simple"].get("severity", {})
        severity = severity if isinstance(severity, dict) else {}
        hours = [
            {
                "time": generated,
                "hour": _hour_label(generated),
                "score": vm["simple"].get("model_score") or 0.0,
                "severity": severity.get("key") or "normal",
                "class": severity.get("class") or "calm",
                "timeline_type": "forecast_model",
            }
        ]

    report_stations = [s for s in (report.get("stations") or []) if isinstance(s, dict)]
    if not report_stations:
        report_stations = _station_rows_from_csv(report_dir)
    station_hourly_by_name: dict[str, list[dict[str, Any]]] = {}
    station_hourly_by_id: dict[str, list[dict[str, Any]]] = {}
    for station in report_stations:
        rows = station.get("hourly_risk") if isinstance(station.get("hourly_risk"), list) else []
        if not rows:
            continue
        station_hourly_by_name[_norm_key(station.get("name"))] = rows
        station_hourly_by_id[_norm_key(station.get("station_id"))] = rows

    grid_rows = _read_csv_rows(report_dir / "native_convective_grid.csv")
    if not grid_rows:
        grid_rows = _read_csv_rows(report_dir / "weather_layers_grid.csv")

    grid: list[dict[str, Any]] = []
    for row in grid_rows:
        lat = _num(row.get("lat"))
        lon = _num(row.get("lon"))
        if lat is None or lon is None:
            continue
        base_score = (
            _num(row.get("storm_formation_score"))
            or _num(row.get("native_convective_score"))
            or vm["simple"].get("model_score")
            or 0.0
        )
        nearest_rows = _nearest_station_series(
            row.get("nearest_station"), station_hourly_by_name, station_hourly_by_id
        )
        grid_scores = _blend_hourly_scores(base_score, nearest_rows, hours)
        grid.append(
            {
                "lat": lat,
                "lon": lon,
                "score": _round(base_score, 3),
                "scores": grid_scores,
                "level": row.get("storm_formation_level") or row.get("native_convective_level"),
                "native_convective_score": _round(row.get("native_convective_score"), 3),
                "storm_formation_score": _round(row.get("storm_formation_score"), 3),
                "cape_jkg": _round(row.get("cape_j_kg"), 1),
                "cin_jkg": _round(row.get("cin_j_kg"), 1),
                "lifted_index_c": _round(row.get("lifted_index_c"), 1),
                "dew_point_c": _round(row.get("dew_point_c"), 1),
                "humidity_pct": _round(row.get("humidity_pct"), 1),
                "nearest_station": row.get("nearest_station"),
                "hourly_source": (
                    "nearest_station_hourly_risk" if nearest_rows else "global_timeline_fallback"
                ),
            }
        )

    stations: list[dict[str, Any]] = []
    for station in report_stations or vm["expert"].get("stations", []):
        if not isinstance(station, dict):
            continue
        lat = _num(station.get("lat"))
        lon = _num(station.get("lon"))
        if lat is None or lon is None:
            continue
        score = _num(station.get("score")) or _num(station.get("convective_risk_score")) or 0.0
        drivers = station.get("drivers") if isinstance(station.get("drivers"), dict) else {}
        hourly_rows = (
            station.get("hourly_risk") if isinstance(station.get("hourly_risk"), list) else []
        )
        stations.append(
            {
                "station_id": station.get("station_id"),
                "name": station.get("name"),
                "region": station.get("region"),
                "lat": lat,
                "lon": lon,
                "score": _round(score, 3),
                "scores": (
                    _hourly_scores(hourly_rows, hours, score)
                    if hourly_rows
                    else _series_from_base(score, hours)
                ),
                "severity": (
                    station.get("severity", {}).get("key")
                    if isinstance(station.get("severity"), dict)
                    else station.get("severity")
                ),
                "worst_time": station.get("worst_time"),
                "heat_stress_score": _round(station.get("heat_stress_score"), 3),
                "convective_risk_score": _round(station.get("convective_risk_score"), 3),
                "temperature_c": station.get("max_temperature_c") or drivers.get("temperature_c"),
                "dew_point_c": station.get("max_dew_point_c") or drivers.get("dew_point_c"),
                "precip_probability_pct": station.get("max_precip_probability_pct")
                or drivers.get("precip_prob_pct"),
                "wind_gust_ms": station.get("max_wind_gust_ms") or drivers.get("wind_gust_ms"),
                "signals": station.get("signals") or [],
                "hourly": {
                    "time": [h.get("time") for h in hours],
                    "scores": (
                        _hourly_scores(hourly_rows, hours, score)
                        if hourly_rows
                        else _series_from_base(score, hours)
                    ),
                    "convective_risk_score": _hourly_values(
                        hourly_rows,
                        "convective_risk_score",
                        hours,
                        station.get("convective_risk_score"),
                        3,
                    ),
                    "heat_stress_score": _hourly_values(
                        hourly_rows,
                        "heat_stress_score",
                        hours,
                        station.get("heat_stress_score"),
                        3,
                    ),
                    "temperature_c": _hourly_values(
                        hourly_rows,
                        "temperature_c",
                        hours,
                        station.get("max_temperature_c"),
                        1,
                    ),
                    "dew_point_c": _hourly_values(
                        hourly_rows,
                        "dew_point_c",
                        hours,
                        station.get("max_dew_point_c"),
                        1,
                    ),
                    "precip_probability_pct": _hourly_values(
                        hourly_rows,
                        "precip_probability_pct",
                        hours,
                        station.get("max_precip_probability_pct"),
                        1,
                    ),
                    "wind_gust_ms": _hourly_values(
                        hourly_rows,
                        "wind_gust_ms",
                        hours,
                        station.get("max_wind_gust_ms"),
                        1,
                    ),
                },
            }
        )

    return {
        "contract": "meteovoid_belgium_map_live_v2",
        "compat_contract": "meteovoid_belgium_map_live_v1",
        "generated_at": meta.get("generated_at"),
        "run_id": meta.get("run_id"),
        "region": "belgium",
        "source": "belgium_alert_watch",
        "mode": "latest_published_run",
        "disclaimer": meta.get("disclaimer"),
        "timeline": {
            "default": "forecast_model",
            "forecast_model": {
                "label": "prévision modèle",
                "hours": hours,
                "description": "Scores horaires du workflow Belgium Alert Watch.",
            },
            "radar_observed": {
                "label": "radar observé",
                "provider": "RainViewer / radars nationaux selon disponibilité",
                "description": (
                    "Frames observées ou nowcast court terme, séparées de la prévision +48h."
                ),
                "max_reasonable_horizon_hours": 2,
            },
            "nowcast_short_term": {
                "label": "nowcast court terme",
                "description": (
                    "Réservé aux produits pySTEPS/OPERA quand des frames machine sont disponibles."
                ),
                "available": bool(vm["expert"].get("radar_stack", {}).get("status") == "available"),
            },
        },
        "hours": hours,
        "grid": grid,
        "stations": stations,
        "summary": {
            "model_score": vm["simple"].get("model_score"),
            "operational_level": vm["simple"].get("operational_level"),
            "main_zone": vm["simple"].get("main_zone"),
            "critical_window": vm["simple"].get("critical_window"),
            "grid_count": len(grid),
            "station_count": len(stations),
            "hour_count": len(hours),
            "station_hourly_source": "belgium_alert_report.stations[].hourly_risk",
            "grid_hourly_source": "native grid snapshot + nearest station hourly_risk",
        },
    }


def build_api(vm: dict[str, Any], site_dir: Path, report_dir: Path | None = None) -> None:
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
        api_dir / "validation_history.json",
        {"generated_at": generated_at, **(vm["expert"].get("validation_history") or {})},
    )
    _write_json(
        api_dir / "weather_5days.json",
        {"generated_at": generated_at, **(vm["expert"].get("weather_5days") or {})},
    )
    _write_json(
        api_dir / "official_geodata.json",
        {"generated_at": generated_at, **(vm["expert"].get("official_geodata") or {})},
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
            "opera_ord_status": vm["expert"].get("opera_ord_status", {}),
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
        api_dir / "weather_belgium.json",
        {
            "generated_at": generated_at,
            "timezone": meta.get("timezone"),
            "data_mode": meta.get("data_mode"),
            "regions": vm["heat"].get("regional_weather", []),
            "stations": vm["expert"].get("stations", []),
            "note": (
                "Bulletin météo régional issu du dernier run MeteoVoid. "
                "Ce n'est pas un bulletin officiel IRM/KMI."
            ),
        },
    )
    _write_json(
        api_dir / "convective_live.json",
        {
            "generated_at": generated_at,
            **(vm["expert"].get("convective_live_inputs") or {}),
        },
    )
    _write_json(api_dir / "live_smoke.json", vm["expert"].get("live_smoke") or {})
    _write_json(api_dir / "watch.json", _build_alert_watch_api(vm))
    map_live_payload: dict[str, Any] | None = None
    if report_dir is not None:
        map_live_payload = _build_map_live_api(vm, report_dir)
        _write_json(api_dir / "map_live.json", map_live_payload)
    _write_json(
        api_dir / "data_quality.json",
        {"generated_at": generated_at, **(vm["expert"].get("data_quality") or {})},
    )
    _write_json(
        api_dir / "europe.json",
        build_europe_model(site_dir / "reports" / "latest", vm),
    )
    _write_json(api_dir / "europe_sources.json", build_europe_sources_api())

    if report_dir is not None:
        deep_api = build_deep_platform_api(report_dir, map_live_payload)
        countries_payload = deep_api.get("countries", {})
        countries_dir = api_dir / "countries"
        countries = countries_payload.get("countries")
        if isinstance(countries, dict):
            for country_key, country_payload in countries.items():
                _write_json(countries_dir / str(country_key) / "map_live.json", country_payload)
        _write_json(countries_dir / "index.json", countries_payload)
        _write_json(api_dir / "validation_summary.json", deep_api.get("validation_summary", {}))
        _write_json(api_dir / "explain.json", deep_api.get("explain", {}))
        _write_json(api_dir / "corridors.json", deep_api.get("corridors", {}))
        _write_json(api_dir / "events.json", deep_api.get("events", {}))
        _write_json(api_dir / "radar_machine.json", deep_api.get("radar_machine", {}))
        _write_json(api_dir / "temporal_layers.json", deep_api.get("temporal_layers", {}))
        _write_json(api_dir / "signal_confidence.json", deep_api.get("signal_confidence", {}))
        _write_json(api_dir / "station_quality_map.json", deep_api.get("station_quality_map", {}))
        _write_json(api_dir / "convergence_matrix.json", deep_api.get("convergence_matrix", {}))
        _write_json(api_dir / "country_comparison.json", deep_api.get("country_comparison", {}))
        _write_json(api_dir / "forecast_ledger.json", deep_api.get("forecast_ledger", {}))
        _write_json(
            api_dir / "operational_readiness.json", deep_api.get("operational_readiness", {})
        )
        _write_json(api_dir / "risk_ontology.json", deep_api.get("risk_ontology", {}))
        _write_json(api_dir / "action_cards.json", deep_api.get("action_cards", {}))
        _write_json(api_dir / "ui_contracts.json", deep_api.get("ui_contracts", {}))
        _write_json(api_dir / "source_health.json", deep_api.get("source_health", {}))
        _write_json(api_dir / "schema_catalog.json", deep_api.get("schema_catalog", {}))
        _write_json(api_dir / "platform.json", deep_api.get("platform", {}))

    model_compare_payload = build_model_compare_api(map_live_payload, generated_at=generated_at)
    _write_json(api_dir / "model_compare.json", model_compare_payload)
    _write_json(api_dir / "models" / "open_meteo_multimodel.json", model_compare_payload)

    _write_json(
        api_dir / "index.json",
        {
            "generated_at": generated_at,
            "description": "MeteoVoid Belgique static API",
            "endpoints": meta.get("endpoints"),
            "extra_endpoints": {
                "radar": "api/radar.json",
                "heat": "api/heat.json",
                "weather_belgium": "api/weather_belgium.json",
                "weather_5days": "api/weather_5days.json",
                "validation_history": "api/validation_history.json",
                "official_geodata": "api/official_geodata.json",
                "convective_live": "api/convective_live.json",
                "live_smoke": "api/live_smoke.json",
                "watch": "api/watch.json",
                "map_live": "api/map_live.json",
                "data_quality": "api/data_quality.json",
                "europe": "api/europe.json",
                "europe_sources": "api/europe_sources.json",
                "country_contracts": "api/countries/index.json",
                "validation_summary": "api/validation_summary.json",
                "explain": "api/explain.json",
                "corridors": "api/corridors.json",
                "events": "api/events.json",
                "radar_machine": "api/radar_machine.json",
                "temporal_layers": "api/temporal_layers.json",
                "signal_confidence": "api/signal_confidence.json",
                "station_quality_map": "api/station_quality_map.json",
                "convergence_matrix": "api/convergence_matrix.json",
                "country_comparison": "api/country_comparison.json",
                "forecast_ledger": "api/forecast_ledger.json",
                "operational_readiness": "api/operational_readiness.json",
                "risk_ontology": "api/risk_ontology.json",
                "action_cards": "api/action_cards.json",
                "ui_contracts": "api/ui_contracts.json",
                "source_health": "api/source_health.json",
                "schema_catalog": "api/schema_catalog.json",
                "public_manifest": "api/public_manifest.json",
                "platform": "api/platform.json",
            },
            "disclaimer": meta.get("disclaimer"),
        },
    )
    _write_public_manifest(api_dir)


def _write_europe_page_legacy_v1(site_dir: Path, model: dict[str, Any]) -> None:
    payload = json.dumps(model, ensure_ascii=False).replace("</", "<\\/")
    page = EUROPE_TEMPLATE.replace("__EUROPE_BOOTSTRAP__", payload)
    (site_dir / "europe.html").write_text(page, encoding="utf-8")


EUROPE_TEMPLATE = r"""<!doctype html>
<html lang="fr" data-theme="dark">
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
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
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
function masterRow(s){const env=s.auth_env?esc(s.auth_env)+(s.requires_key?(s.configured?' ✓':' ✗'):(s.enabled?' ✓':' ✗')):'—';const col=s.machine_evidence_ready?'ok':((s.configured||s.enabled)?'watch':'muted');return `<tr><td><b>#${esc(s.rank)}</b></td><td><b>${esc(s.provider)}</b><p class="muted small">${esc(s.role||'')}</p></td><td>${esc(s.scope)}${s.country?(' · '+esc(s.country)):''}</td><td>${esc(s.auth)}<p class="muted small">${env}</p></td><td class="small">${esc(s.rate_limit||'—')}</td><td class="small">${esc((s.formats||[]).join(', '))}</td><td><span class="${col}">${esc(s.status)}</span></td></tr>`;}
function renderSources(){const ms=MODEL.master_sources||{},msum=ms.summary||{};const mrows=(ms.sources||[]).map(masterRow).join('');const rows=MODEL.sources||[];return `<div class="notice"><b>Registre maître des sources radar européennes.</b> ${esc(ms.security_note||'')}</div><div class="grid cards4"><div class="card kpi"><span>Sources</span><b>${esc(msum.source_count||0)}</b></div><div class="card kpi"><span>Activées</span><b>${esc(msum.enabled_count||0)}</b></div><div class="card kpi"><span>Clés configurées</span><b>${esc(msum.configured_key_count||0)}</b></div><div class="card kpi"><span>Prêtes preuve machine</span><b>${esc(msum.machine_ready_count||0)}</b></div></div><div class="section-title">Sources par priorité opérationnelle</div><div class="card" style="overflow:auto"><table><thead><tr><th>Rang</th><th>Fournisseur</th><th>Portée</th><th>Auth / variable</th><th>Quota</th><th>Formats</th><th>Statut</th></tr></thead><tbody>${mrows||'<tr><td colspan="7" class="muted">Registre indisponible.</td></tr>'}</tbody></table></div>${(ms.excluded_as_machine_evidence&&ms.excluded_as_machine_evidence.length)?`<div class="section-title">Exclu de la preuve machine</div><ul>${ms.excluded_as_machine_evidence.map(x=>`<li class="muted">${esc(x)}</li>`).join('')}</ul>`:''}<div class="section-title">Interfaces nationales par pays (run courant)</div><div class="card" style="overflow:auto"><table><thead><tr><th>Pays</th><th>Fournisseur</th><th>Statut</th><th>Niveau</th><th>Format</th><th>Clé</th></tr></thead><tbody>${rows.map(s=>`<tr><td><b>${esc(s.country)}</b></td><td>${esc(s.provider)}<p class="muted small">${esc(s.role||'')}</p></td><td>${esc(s.status||'')}</td><td>${esc(s.evidence_level||'')}</td><td>${esc(s.expected_format||'—')}</td><td>${s.api_key_env?esc(s.api_key_env)+(s.api_key_configured?' configurée':' manquante'):'—'}</td></tr>`).join('')}</tbody></table></div>`}
function renderExpert(){return `<div class="grid cards2"><div class="card"><div class="eyebrow">Exports</div><h2>Données Europe</h2><div class="links">${(MODEL.exports||[]).map(x=>`<a href="${esc(x.href)}">${esc(x.label)}</a>`).join('')}</div></div><div class="card"><div class="eyebrow">Contrat</div><h2>${esc(MODEL.page_contract||'')}</h2><p class="muted">Run ${esc(MODEL.run_id||'')} · ${esc(MODEL.generated_at||'')}</p></div></div><div class="section-title">Modèle brut</div><pre>${esc(JSON.stringify(MODEL,null,2))}</pre>`}
function paint(){renderKpis();document.getElementById('view-simple').innerHTML=renderSimple();document.getElementById('view-operationnel').innerHTML=renderOperational();document.getElementById('view-carte').innerHTML=renderMap();document.getElementById('view-pays').innerHTML=renderCountries();document.getElementById('view-corridors').innerHTML=renderCorridors();document.getElementById('view-sources').innerHTML=renderSources();document.getElementById('view-expert').innerHTML=renderExpert();document.getElementById('foot').textContent=`MeteoVoid Europe · ${MODEL.generated_at||''} · ${MODEL.run_id||''}`}

document.querySelectorAll('.tab').forEach(btn=>btn.addEventListener('click',()=>{document.querySelectorAll('.tab').forEach(b=>b.classList.remove('active'));btn.classList.add('active');document.querySelectorAll('.view').forEach(v=>v.classList.toggle('active',v.id==='view-'+btn.dataset.view));if(btn.dataset.view==='carte')initEuropeMap();window.scrollTo({top:0,behavior:'smooth'});}));
function euApplyTheme(t){document.documentElement.dataset.theme=t;try{localStorage.setItem('mv-theme',t);}catch(e){}}
(function(){let t='light';try{t=localStorage.getItem('mv-theme')||((matchMedia&&matchMedia('(prefers-color-scheme: dark)').matches)?'dark':'light');}catch(e){}euApplyTheme(t);})();
document.getElementById('theme').onclick=()=>{euApplyTheme(document.documentElement.dataset.theme==='dark'?'light':'dark');};
paint();
</script>
</body>
</html>"""


COUNTRY_TEMPLATE = r"""<!doctype html>
<html lang="fr" data-theme="dark">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>MeteoVoid · suivi pays · détection + réseau radar</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<style>
:root{--bg:#eef3f9;--card:#fff;--ink:#132033;--muted:#65738a;--line:#d9e3f0;--accent:#2f7cc0;--ok:#1d9a63;--watch:#d28a19;--danger:#c74242;--soft:#f7fafc;--shadow:0 14px 34px rgba(18,34,58,.08)}
[data-theme=dark]{--bg:#0d1625;--card:#142237;--ink:#e7eef8;--muted:#a7b5c9;--line:#293b57;--accent:#71b8ff;--soft:#101b2d;--shadow:0 14px 34px rgba(0,0,0,.22)}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,Segoe UI,Arial,sans-serif;line-height:1.5}.top{position:sticky;top:0;z-index:50;background:rgba(255,255,255,.85);backdrop-filter:blur(14px);border-bottom:1px solid var(--line)}[data-theme=dark] .top{background:rgba(13,22,37,.86)}.topin{max-width:1240px;margin:auto;padding:14px 18px;display:flex;align-items:center;justify-content:space-between;gap:16px}.brand h1{margin:0;font-size:22px}.brand p{margin:2px 0 0;color:var(--muted);font-size:13px}.nav{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.nav a,.nav button{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:999px;padding:8px 12px;text-decoration:none;cursor:pointer}.nav a.active{background:var(--accent);color:#fff;border-color:var(--accent)}.hero{max-width:1240px;margin:22px auto 0;padding:0 18px}.hero-card{background:linear-gradient(135deg,rgba(47,124,192,.16),rgba(29,154,99,.09)),var(--card);border:1px solid var(--line);border-radius:28px;padding:26px;box-shadow:var(--shadow)}.eyebrow{text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-size:12px;font-weight:700}.title{font-size:42px;line-height:1.05;margin:8px 0 12px}.lead{max-width:900px;color:var(--muted);font-size:16px}.tabs{max-width:1240px;margin:18px auto 0;padding:0 18px;display:flex;gap:8px;flex-wrap:wrap}.tab{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:14px;padding:10px 13px;cursor:pointer}.tab.active{background:var(--accent);color:#fff;border-color:var(--accent)}main{max-width:1240px;margin:18px auto 56px;padding:0 18px}.view{display:none}.view.active{display:block}.grid{display:grid;gap:14px}.kpis{grid-template-columns:repeat(6,minmax(120px,1fr))}.cards2{grid-template-columns:1.15fr .85fr}.cards3{grid-template-columns:repeat(3,minmax(0,1fr))}.cards4{grid-template-columns:repeat(4,minmax(0,1fr))}.card{background:var(--card);border:1px solid var(--line);border-radius:22px;padding:18px;box-shadow:var(--shadow)}.kpi span{display:block;color:var(--muted);font-size:13px}.kpi b{font-size:26px}.notice{border:1px solid var(--line);background:var(--card);border-radius:18px;padding:14px 16px;margin-bottom:14px;color:var(--muted)}.section-title{margin:26px 0 10px;font-weight:800;font-size:18px}.pill,.badge{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);border-radius:999px;padding:5px 10px;background:var(--soft);font-size:13px}.dot{width:9px;height:9px;border-radius:99px;display:inline-block}.ok{color:var(--ok)}.watch{color:var(--watch)}.danger{color:var(--danger)}.muted{color:var(--muted)}.score{font-size:30px;font-weight:800}.bar{height:9px;background:var(--soft);border:1px solid var(--line);border-radius:99px;overflow:hidden}.bar i{display:block;height:100%;background:var(--accent);width:0}.head{display:flex;justify-content:space-between;gap:12px;align-items:start}.dl{display:flex;justify-content:space-between;gap:14px;border-top:1px solid var(--line);padding:9px 0}.dl span{color:var(--muted)}table{width:100%;border-collapse:collapse}th,td{border-bottom:1px solid var(--line);padding:10px;text-align:left;vertical-align:top}th{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.06em}.links{display:flex;gap:8px;flex-wrap:wrap}.links a{border:1px solid var(--line);border-radius:999px;padding:7px 10px;color:var(--ink);text-decoration:none;background:var(--soft)}pre{white-space:pre-wrap;background:var(--soft);border:1px solid var(--line);border-radius:16px;padding:14px;max-height:420px;overflow:auto}.small{font-size:13px}.footer{max-width:1240px;margin:0 auto 40px;padding:0 18px;color:var(--muted)}
.map-bar{display:flex;flex-wrap:wrap;gap:11px;align-items:center;margin:4px 0 14px}.map-toggle{display:inline-flex;align-items:center;gap:8px;font-size:13px;color:var(--ink);background:var(--card);border:1px solid var(--line);border-radius:12px;padding:8px 12px;box-shadow:var(--shadow);cursor:pointer}.model-select{font-size:13px;color:var(--ink);background:var(--card);border:1px solid var(--line);border-radius:12px;padding:8px 12px;box-shadow:var(--shadow);min-width:160px}.map-frame{font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums;min-width:80px}.map-legend{display:flex;gap:13px;flex-wrap:wrap;margin-left:auto;font-size:12px;color:var(--muted)}.map-legend i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px;vertical-align:middle}
.map-wrap{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:14px}.mvmap{height:66vh;min-height:440px;border-radius:20px;overflow:hidden;border:1px solid var(--line);box-shadow:var(--shadow);z-index:0;background:var(--soft)}.map-detail{background:var(--card);border:1px solid var(--line);border-radius:20px;padding:18px;box-shadow:var(--shadow);max-height:66vh;overflow:auto}.map-fallback{display:grid;place-items:center;height:100%;color:var(--muted);padding:24px;text-align:center}
.md-head{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;border-left:3px solid var(--ac,var(--accent));padding-left:12px;margin-bottom:12px}.md-head h3{margin:2px 0 0;font-size:20px}.md-score{display:flex;justify-content:space-between;align-items:center;gap:10px;margin:4px 0 12px}
.leaflet-container{font:inherit;background:var(--soft)}.leaflet-popup-content-wrapper,.leaflet-popup-tip{background:var(--card);color:var(--ink)}[data-theme=dark] .leaflet-tile{filter:brightness(.78) contrast(1.05) hue-rotate(178deg) invert(.92)}
@media(max-width:900px){.title{font-size:32px}.kpis,.cards2,.cards3,.cards4{grid-template-columns:1fr}.map-wrap{grid-template-columns:1fr}.mvmap{height:52vh}.map-detail{max-height:none}.map-legend{margin-left:0}}
</style>
</head>
<body>
<header class="top"><div class="topin"><div class="brand"><h1 id="brand-title">MeteoVoid</h1><p id="brand-sub">Suivi pays · détection MeteoVoid · réseau radar national · RainViewer</p></div><nav class="nav"><a href="index.html">Belgique</a><a href="europe.html">Europe</a><a class="active" href="#">Pays</a><a href="methodology.html">Méthodologie</a><button id="theme">Thème</button></nav></div></header>
<section class="hero"><div class="hero-card"><div class="eyebrow" id="hero-eyebrow">Suivi national</div><h2 class="title" id="hero-title"></h2><p class="lead" id="hero-lead"></p><div class="grid kpis" id="kpis"></div></div></section>
<div class="tabs"><button class="tab active" data-view="detection">Détection</button><button class="tab" data-view="carte">Carte radar</button><button class="tab" data-view="reseau">Réseau radar</button><button class="tab" data-view="expert">Expert</button></div>
<main>
  <section class="view active" id="view-detection"></section>
  <section class="view" id="view-carte"></section>
  <section class="view" id="view-reseau"></section>
  <section class="view" id="view-expert"></section>
</main>
<footer class="footer" id="foot"></footer>
<script id="country-bootstrap" type="application/json">__COUNTRY_BOOTSTRAP__</script>
<script>
const M=JSON.parse(document.getElementById('country-bootstrap').textContent);
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const num=(v,d=2)=>v==null||v===''?'—':(typeof v==='number'?v.toFixed(d):esc(v));
const pct=v=>v==null?'—':Math.round(Number(v)*100)+' %';
function getCss(v){try{return getComputedStyle(document.documentElement).getPropertyValue(v).trim()||'#2f7cc0';}catch(e){return '#2f7cc0';}}
function sevColor(k){return {calm:'#1d9a63',watch:'#d28a19',elevated:'#e0683a',danger:'#c74242'}[k]||'#2f7cc0';}
function spark(hourly){const v=(hourly||[]).map(x=>x.s).filter(x=>x!=null);if(v.length<2)return '';const W=150,H=38,n=v.length;const pts=v.map((s,i)=>[4+(W-8)*i/(n-1),H-3-(H-8)*Math.max(0,Math.min(1,s))]);const d='M'+pts.map(p=>p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' L ');return `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" style="margin:6px 0" aria-hidden="true"><path d="${d}" fill="none" stroke="var(--accent)" stroke-width="2"/></svg>`;}
function renderKpis(){const s=M.summary||{},lv=M.operational_level||{},rn=M.radar_network||{};
  document.getElementById('hero-title').textContent='Suivi '+(M.label||'');
  document.getElementById('brand-title').textContent='MeteoVoid '+(M.label||'');
  document.getElementById('hero-eyebrow').textContent='Suivi national · '+(M.iso2||'');
  document.getElementById('hero-lead').textContent='Détection MeteoVoid par station, réseau radar national '+(rn.operator||'')+' et radar RainViewer en direct. Même système que la page Belgique. Prototype non officiel.';
  const sc=s.severity_counts||{},alertCount=(sc.elevated||0)+(sc.danger||0);
  document.getElementById('kpis').innerHTML=[['Niveau',lv.label||'—'],['Stations',s.station_count||0],['Sites radar',s.radar_site_count||0],['Score max',pct(s.max_score)],['En alerte',alertCount],['Mode',M.data_mode||'']].map(x=>`<div class="card kpi"><span>${esc(x[0])}</span><b>${esc(x[1])}</b></div>`).join('');}
function convRows(c){if(!c)return '';const tag=c.native_fields_available?'natif':'proxy';return `<div class="dl"><span>CAPE / LI</span><strong>${num(c.cape_jkg,0)} J/kg / ${num(c.lifted_index,1)}</strong></div><div class="dl"><span>CIN / cisaillement</span><strong>${num(c.cin_jkg,0)} / ${num(c.bulk_shear_ms,1)} m/s</strong></div><div class="dl"><span>Base convective</span><strong>${esc(tag)}</strong></div>`;}
function stationCard(s){const k=(s.severity||{}).key,d=s.drivers||{};return `<article class="card"><div class="head"><div><div class="eyebrow">${esc(s.name)}</div><div class="score" style="color:${sevColor(k)}">${pct(s.score)}</div></div><span class="badge" style="border-color:${sevColor(k)}"><span class="dot" style="background:${sevColor(k)}"></span>${esc((s.severity||{}).label)}</span></div>${spark(s.hourly)}<div class="dl"><span>Heure sensible</span><strong>${esc(s.worst_time)}</strong></div><div class="dl"><span>Temp / rosée</span><strong>${num(d.temperature_c,1)} / ${num(d.dew_point_c,1)} °C</strong></div><div class="dl"><span>Proba pluie</span><strong>${num(d.precip_prob_pct,0)} %</strong></div><div class="dl"><span>Chute pression</span><strong>${num(d.pressure_drop_hpa,1)} hPa</strong></div><div class="dl"><span>Rafales</span><strong>${num(d.wind_gust_ms,1)} m/s</strong></div>${convRows(s.convective)}<ul class="small">${(s.signals||[]).map(x=>`<li>${esc(x)}</li>`).join('')}</ul></article>`;}
function renderWeatherBulletin(){const w=M.weather||{},rows=w.stations||[];return `<div class="card"><div class="eyebrow">Bulletin météo pays · dernier run</div><h2>${esc(M.label)} · températures par station</h2><p class="muted">${esc(w.note||'Même maillage que la détection MeteoVoid.')} Maximum : ${num(w.max_temperature_c,1)} °C, humidex ${num(w.max_humidex,1)} · station ${esc(w.top_station||'—')}.</p><div style="overflow:auto"><table><thead><tr><th>Station</th><th style="text-align:right">Temp.</th><th style="text-align:right">Humidex</th><th style="text-align:right">Rosée</th><th style="text-align:right">Pluie</th><th style="text-align:right">Rafales</th></tr></thead><tbody>${rows.slice(0,14).map(r=>`<tr><td><b>${esc(r.name)}</b><p class="muted small">${esc((r.severity||{}).label||'')}</p></td><td style="text-align:right">${num(r.temperature_c,1)} °C</td><td style="text-align:right">${num(r.humidex,1)}</td><td style="text-align:right">${num(r.dew_point_c,1)} °C</td><td style="text-align:right">${num(r.precip_prob_pct,0)} %</td><td style="text-align:right">${num(r.wind_gust_ms,1)} m/s</td></tr>`).join('')}</tbody></table></div></div>`;}
function renderDetection(){const s=M.summary||{},sc=s.severity_counts||{},cv=M.convective||{};const native=cv.native_fields_available;const col=native?'#1d9a63':'#d28a19';const cvBadge=`<span class="badge" style="border-color:${col}"><span class="dot" style="background:${col}"></span>${native?'convectif natif (CAPE/CIN/LI/cisaillement)':'convectif proxy (étiqueté)'}</span>`;return `<div class="notice"><b>Détection MeteoVoid · ${esc(M.label)}.</b> Le même moteur que la Belgique score chaque station (volatilité, à-coups et dérive des rafales via le moteur générique). ${esc(s.station_count||0)} stations suivies, ${esc((sc.elevated||0)+(sc.danger||0))} en signal élevé/critique. ${cvBadge}</div>${renderWeatherBulletin()}${!native?`<div class="notice" style="border-color:${col}"><b>Base convective : proxy.</b> ${esc(cv.note||'')} En mode live (Open-Meteo), MeteoVoid lit les champs natifs CAPE, CIN, Lifted Index et cisaillement ; sinon la couche convective reste un proxy explicite.</div>`:''}<div class="grid cards3">${(M.stations||[]).map(stationCard).join('')}</div>`;}
function srcColor(s){return s.machine_evidence_ready?'#1d9a63':((s.configured||s.enabled)?'#d28a19':'#65738a');}
function sourceCard(s){const col=srcColor(s),env=s.auth_env?esc(s.auth_env)+(s.requires_key?(s.configured?' ✓ configurée':' ✗ manquante'):(s.enabled?' ✓ activé':' ✗ désactivé')):'—';return `<article class="card"><div class="head"><div><div class="eyebrow">#${esc(s.rank)} · ${esc(s.scope)}</div><h3 style="font-size:17px;margin:2px 0">${esc(s.provider)}</h3></div><span class="badge" style="border-color:${col}"><span class="dot" style="background:${col}"></span>${esc(s.status)}</span></div><p class="muted small">${esc(s.role||'')}</p><div class="dl"><span>Auth</span><strong>${esc(s.auth)}</strong></div><div class="dl"><span>Variable</span><strong class="small">${env}</strong></div><div class="dl"><span>Quota</span><strong class="small">${esc(s.rate_limit||'—')}</strong></div><div class="dl"><span>Formats</span><strong class="small">${esc((s.formats||[]).join(', '))}</strong></div><div class="dl"><span>Preuve</span><strong>${esc(s.evidence_level||'')}</strong></div><p class="muted small">${esc(s.status_text||'')}</p>${s.public_reference?`<div class="links"><a href="${esc(s.public_reference)}" target="_blank" rel="noopener">documentation</a></div>`:''}</article>`;}
function machineRadarBlock(){const mr=M.machine_radar||{},v=M.validation||{};const mcol=mr.available?'#1d9a63':'#d28a19';const vcol=(v.status==='available')?'#1d9a63':'#d28a19';return `<div class="grid cards2" style="margin-top:6px"><div class="card"><div class="head"><div class="eyebrow">Preuve radar machine</div><span class="badge" style="border-color:${mcol}"><span class="dot" style="background:${mcol}"></span>${mr.available?'métriques calculées':'aucune métrique machine'}</span></div><p class="muted small">${esc(mr.note||'')}</p>${(mr.blockers&&mr.blockers.length)?'<div class="eyebrow" style="margin-top:8px">Blocages</div><ul class="small">'+mr.blockers.map(b=>`<li>${esc(b)}</li>`).join('')+'</ul>':''}<div class="eyebrow" style="margin-top:8px">Pour activer la preuve machine</div><ul class="small">${(mr.how_to_enable||[]).map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div><div class="card"><div class="head"><div class="eyebrow">Validation historique</div><span class="badge" style="border-color:${vcol}"><span class="dot" style="background:${vcol}"></span>${esc(v.status||'needs_verified_events')}</span></div><p class="muted small">${esc(v.note||'')}</p><div class="dl"><span>Événements vérifiés</span><strong>${esc(v.verified_event_count||0)}</strong></div><div class="dl"><span>Brier / POD</span><strong>${num((v.metrics||{}).brier_score)} / ${num((v.metrics||{}).pod)}</strong></div><div class="dl"><span>FAR / CSI</span><strong>${num((v.metrics||{}).far)} / ${num((v.metrics||{}).csi)}</strong></div></div></div>`;}
function renderReseau(){const r=M.radar_network||{};const rows=(r.sites||[]).map(s=>`<tr><td><b>${esc(s.name)}</b></td><td>${esc(s.band||'')}-band</td><td>${num(s.lat,2)}</td><td>${num(s.lon,2)}</td></tr>`).join('');const srcs=(M.data_sources||[]);return `<div class="grid cards3"><div class="card"><div class="eyebrow">Opérateur</div><div class="phrase" style="font-weight:600">${esc(r.operator||'')}</div><p class="muted small">${esc(r.network||'')}</p></div><div class="card"><div class="eyebrow">Sites radar réels</div><div class="score">${esc(r.site_count||0)}</div></div><div class="card"><div class="eyebrow">Statut clé nationale</div><div class="phrase" style="font-weight:600">${esc(r.status||'')}</div><p class="muted small">${r.api_key_env?esc(r.api_key_env)+(r.api_key_configured?' configurée':' manquante'):'open data, pas de clé'}</p></div></div><div class="notice" style="margin-top:14px">${esc(r.note||'')}</div>${machineRadarBlock()}${srcs.length?`<div class="section-title">Sources de données radar (priorité &amp; accès)</div><p class="muted small" style="margin-bottom:10px">Authentification, quotas et formats par fournisseur. Les clés restent côté secrets : cette page n'affiche que des statuts, jamais une valeur de clé.</p><div class="grid cards3">${srcs.map(sourceCard).join('')}</div>`:''}<div class="section-title">Sites du réseau (${esc(r.site_count||0)})</div><div class="card" style="overflow:auto"><table><thead><tr><th>Site radar</th><th>Bande</th><th>Lat</th><th>Lon</th></tr></thead><tbody>${rows||'<tr><td colspan="4" class="muted">Aucun site radar configuré.</td></tr>'}</tbody></table></div>`;}
function renderExpert(){return `<div class="grid cards2"><div class="card"><div class="eyebrow">Exports</div><h2>Données ${esc(M.label)}</h2><div class="links"><a href="api/country_${esc(M.country)}.json">API pays JSON</a><a href="europe.html">Page Europe</a><a href="index.html">Belgique</a></div></div><div class="card"><div class="eyebrow">Contrat</div><h2>${esc(M.contract||'')}</h2><p class="muted">Run ${esc(M.run_day||'')} · ${esc(M.generated_at||'')} · mode ${esc(M.data_mode||'')}</p></div></div><div class="section-title">Modèle brut</div><pre>${esc(JSON.stringify(M,null,2))}</pre>`;}
function renderCarte(){const rn=M.radar_network||{};const leg=[['calm','faible'],['watch','modéré'],['elevated','élevé'],['danger','critique']];return `<div class="notice"><b>Carte radar ${esc(M.label)}.</b> ${esc(rn.site_count||0)} sites radar ${esc(rn.operator||'')} réels, radar RainViewer animé en direct, et stations de détection MeteoVoid colorées par niveau — comme la carte Belgique. Une carte affichée ne vaut pas preuve machine.</div>
  <div class="map-bar">
    <label class="map-toggle"><input type="checkbox" id="c-radartog" checked> Radar pluie (RainViewer)</label>
    <label class="map-toggle"><input type="checkbox" id="c-sitetog" checked> Sites radar ${esc(rn.operator||'')}</label>
    <button class="map-toggle" id="c-modeltog" type="button" aria-pressed="false">Modèle NWP</button>
    <select class="model-select" id="c-modelsrc" aria-label="Modèle météo"><option value="best">Best match</option><option value="ecmwf">ECMWF IFS</option><option value="icon">DWD ICON</option><option value="arome">Météo-France AROME/ARPEGE</option></select>
    <select class="model-select" id="c-modellayer" aria-label="Couche météo"><option value="precipitation">Précipitation</option><option value="wind_speed_10m">Vent 10 m</option><option value="wind_gusts_10m">Rafales</option><option value="temperature_2m">Température 2 m</option><option value="dew_point_2m">Point de rosée</option><option value="pressure_msl">Pression</option><option value="cape">CAPE</option><option value="convective_inhibition">CIN</option><option value="tcwv">PWAT</option><option value="temperature_850hPa">Température 850 hPa</option><option value="temperature_700hPa">Température 700 hPa</option><option value="temperature_500hPa">Température 500 hPa</option><option value="shear_0_6km">Cisaillement 0–6 km</option></select>
    <span class="map-frame" id="c-model-frame">modèle masqué</span>
    <button class="map-toggle" id="c-playtog" type="button">⏸ Animation</button>
    <span class="map-frame" id="c-frame"></span>
    <div class="map-legend">${leg.map(x=>`<span><i style="background:${sevColor(x[0])}"></i>${x[1]}</span>`).join('')}<span><i style="background:#fff;border:2px solid var(--accent)"></i>radar</span><span><i style="background:#C13A8A"></i>modèle</span></div>
  </div>
  <div class="map-wrap"><div id="cmap" class="mvmap"></div><aside id="c-detail" class="map-detail"><p class="muted">Clique une station pour son détail de détection, ou un point radar pour le site. Active RainViewer pour suivre la pluie en direct.</p></aside></div>`;}
function stationDetail(s){const k=(s.severity||{}).key,d=s.drivers||{};return `<div class="md-head" style="--ac:${sevColor(k)}"><div><div class="eyebrow">${esc(M.label)} · ${esc(s.worst_time)}</div><h3>${esc(s.name)}</h3></div><span class="badge"><span class="dot" style="background:${sevColor(k)}"></span>${esc((s.severity||{}).label)}</span></div><div class="md-score"><div><div class="eyebrow">Score MeteoVoid</div><div class="score" style="color:${sevColor(k)}">${pct(s.score)}</div></div>${spark(s.hourly)}</div><div class="dl"><span>Temp / rosée</span><strong>${num(d.temperature_c,1)} / ${num(d.dew_point_c,1)} °C</strong></div><div class="dl"><span>Proba pluie</span><strong>${num(d.precip_prob_pct,0)} %</strong></div><div class="dl"><span>Chute pression</span><strong>${num(d.pressure_drop_hpa,1)} hPa</strong></div><div class="dl"><span>Rafales</span><strong>${num(d.wind_gust_ms,1)} m/s</strong></div>${convRows(s.convective)}${(s.signals&&s.signals.length)?'<div class="section-title">Signaux</div><ul class="small">'+s.signals.map(x=>`<li>${esc(x)}</li>`).join('')+'</ul>':''}`;}
let CMAP={inst:null,booted:false,radar:null,host:'',frames:[],pastCount:0,idx:0,timer:null,playing:true,markers:{},radarSites:[],modelLayer:null,modelVisible:false,modelBusy:false};
const C_NWP_MODELS={best:{label:'Best match',endpoint:'https://api.open-meteo.com/v1/forecast'},ecmwf:{label:'ECMWF IFS',endpoint:'https://api.open-meteo.com/v1/ecmwf'},icon:{label:'DWD ICON',endpoint:'https://api.open-meteo.com/v1/dwd-icon'},arome:{label:'Météo-France AROME/ARPEGE',endpoint:'https://api.open-meteo.com/v1/meteofrance'}};
const C_NWP_LAYERS={precipitation:{label:'Précipitation',unit:'mm',fields:['precipitation'],range:[0,12]},wind_speed_10m:{label:'Vent 10 m',unit:'km/h',fields:['wind_speed_10m'],range:[0,90]},wind_gusts_10m:{label:'Rafales',unit:'km/h',fields:['wind_gusts_10m'],range:[0,120]},temperature_2m:{label:'Température 2 m',unit:'°C',fields:['temperature_2m'],range:[-5,42]},dew_point_2m:{label:'Point de rosée',unit:'°C',fields:['dew_point_2m'],range:[0,26]},pressure_msl:{label:'Pression',unit:'hPa',fields:['pressure_msl'],range:[990,1030]},cape:{label:'CAPE',unit:'J/kg',fields:['cape'],range:[0,4000]},convective_inhibition:{label:'CIN',unit:'J/kg',fields:['convective_inhibition'],range:[-250,0]},tcwv:{label:'PWAT',unit:'mm',fields:['total_column_integrated_water_vapour'],range:[10,55],alias:'total_column_integrated_water_vapour'},temperature_850hPa:{label:'Température 850 hPa',unit:'°C',fields:['temperature_850hPa'],range:[-10,28]},temperature_700hPa:{label:'Température 700 hPa',unit:'°C',fields:['temperature_700hPa'],range:[-20,18]},temperature_500hPa:{label:'Température 500 hPa',unit:'°C',fields:['temperature_500hPa'],range:[-35,0]},shear_0_6km:{label:'Cisaillement 0–6 km',unit:'m/s',fields:['wind_speed_10m','wind_direction_10m','wind_speed_500hPa','wind_direction_500hPa'],range:[0,35],derived:true}};
function cSelect(id){const s=(M.stations||[]).find(x=>x.station_id===id);if(!s)return;const det=document.getElementById('c-detail');if(det)det.innerHTML=stationDetail(s);if(CMAP.inst&&s.lat!=null&&s.lon!=null)CMAP.inst.flyTo([s.lat,s.lon],8,{duration:.6});const m=CMAP.markers[id];if(m&&m.openTooltip)m.openTooltip();}
function cRadarStop(){if(CMAP.timer){clearInterval(CMAP.timer);CMAP.timer=null;}}
function cRadarShow(idx){if(!CMAP.inst||!window.L||!CMAP.frames.length)return;idx=(idx+CMAP.frames.length)%CMAP.frames.length;CMAP.idx=idx;const f=CMAP.frames[idx],next=L.tileLayer(CMAP.host+f.path+'/256/{z}/{x}/{y}/4/1_1.png',{opacity:.62,attribution:'RainViewer',zIndex:400});next.addTo(CMAP.inst);const prev=CMAP.radar;CMAP.radar=next;if(prev)setTimeout(()=>{try{CMAP.inst.removeLayer(prev);}catch(e){}},230);const fr=document.getElementById('c-frame');if(fr){const dt=new Date((f.time||0)*1000);fr.textContent=dt.toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'})+(idx>=CMAP.pastCount?' · prévision':'');}}
function cRadarPlay(){cRadarStop();if(!CMAP.playing||CMAP.frames.length<2)return;CMAP.timer=setInterval(()=>cRadarShow(CMAP.idx+1),700);}
function cToggleRadar(on){if(!CMAP.inst||!window.L)return;if(!on){cRadarStop();if(CMAP.radar){CMAP.inst.removeLayer(CMAP.radar);CMAP.radar=null;}const fr=document.getElementById('c-frame');if(fr)fr.textContent='';return;}if(CMAP.frames.length){cRadarShow(CMAP.idx);cRadarPlay();return;}fetch('https://api.rainviewer.com/public/weather-maps.json',{cache:'no-store'}).then(r=>r.json()).then(d=>{CMAP.host=d.host||'https://tilecache.rainviewer.com';const past=(d.radar&&d.radar.past)||[],now=(d.radar&&d.radar.nowcast)||[];CMAP.pastCount=past.length;CMAP.frames=past.concat(now);if(!CMAP.frames.length)return;CMAP.idx=Math.max(0,past.length-1);cRadarShow(CMAP.idx);cRadarPlay();}).catch(()=>{const t=document.getElementById('c-radartog');if(t)t.checked=false;const fr=document.getElementById('c-frame');if(fr)fr.textContent='radar indisponible (réseau)';});}
function cNwpPoints(){const seen=new Set(),out=[];function add(name,lat,lon,type){lat=Number(lat);lon=Number(lon);if(!Number.isFinite(lat)||!Number.isFinite(lon))return;const k=lat.toFixed(2)+'-'+lon.toFixed(2);if(seen.has(k))return;seen.add(k);out.push({name,lat,lon,type:type||'station'});} (M.stations||[]).forEach(s=>add(s.name||s.station_id,s.lat,s.lon,'station'));const c=M.center||{};const clat=Number(c.lat),clon=Number(c.lon);if(Number.isFinite(clat)&&Number.isFinite(clon)){[-.9,-.45,0,.45,.9].forEach(dy=>[-1.1,-.55,0,.55,1.1].forEach(dx=>add('Grille modèle',clat+dy,clon+dx,'grid')));}return out.slice(0,48);}
function cNwpField(k){const l=C_NWP_LAYERS[k]||C_NWP_LAYERS.precipitation;return l.alias||k;}
function cNwpVal(hourly,field,idx){const v=hourly&&hourly[field];if(!Array.isArray(v)||idx<0||idx>=v.length)return null;const n=Number(v[idx]);return Number.isFinite(n)?n:null;}
function cNwpIdx(hourly){const t=(hourly&&hourly.time)||[];if(!Array.isArray(t)||!t.length)return 0;const now=Date.now();let bi=0,bd=Infinity;t.forEach((x,i)=>{const d=Math.abs(new Date(x).getTime()-now);if(d<bd){bd=d;bi=i;}});return bi;}
function cWindVec(spd,dir){const s=Number(spd)/3.6,d=Number(dir)*Math.PI/180;if(!Number.isFinite(s)||!Number.isFinite(d))return null;return {u:-s*Math.sin(d),v:-s*Math.cos(d)};}
function cNwpDerived(hourly,k,idx){if(k!=='shear_0_6km')return cNwpVal(hourly,cNwpField(k),idx);const low=cWindVec(cNwpVal(hourly,'wind_speed_10m',idx),cNwpVal(hourly,'wind_direction_10m',idx));const high=cWindVec(cNwpVal(hourly,'wind_speed_500hPa',idx),cNwpVal(hourly,'wind_direction_500hPa',idx));if(!low||!high)return null;return Math.sqrt((high.u-low.u)**2+(high.v-low.v)**2);}
function cNwpColor(v,k){const l=C_NWP_LAYERS[k]||C_NWP_LAYERS.precipitation;let lo=l.range[0],hi=l.range[1],t=(Number(v)-lo)/((hi-lo)||1);if(k==='convective_inhibition')t=1-t;t=Math.max(0,Math.min(1,t));return t<.2?'#5BC8E8':t<.4?'#7FD08C':t<.6?'#E2C84C':t<.8?'#E8943A':'#C13A8A';}
function cNwpFmt(v,k){const l=C_NWP_LAYERS[k]||C_NWP_LAYERS.precipitation;if(v==null)return '—';const a=Math.abs(Number(v)),d=a>=100?0:(a>=10?1:2);return Number(v).toFixed(d)+' '+l.unit;}
function cNwpUrl(points,modelKey,layerKey){const m=C_NWP_MODELS[modelKey]||C_NWP_MODELS.best,l=C_NWP_LAYERS[layerKey]||C_NWP_LAYERS.precipitation,u=new URL(m.endpoint);u.searchParams.set('latitude',points.map(p=>p.lat.toFixed(4)).join(','));u.searchParams.set('longitude',points.map(p=>p.lon.toFixed(4)).join(','));u.searchParams.set('hourly',Array.from(new Set(l.fields)).join(','));u.searchParams.set('forecast_hours','8');u.searchParams.set('past_hours','1');u.searchParams.set('timezone','Europe/Brussels');u.searchParams.set('wind_speed_unit','kmh');u.searchParams.set('precipitation_unit','mm');return u.toString();}
function cClearNwp(){if(CMAP.modelLayer&&CMAP.inst){CMAP.inst.removeLayer(CMAP.modelLayer);}CMAP.modelLayer=null;}
function cRenderNwp(){if(!CMAP.inst||!window.L||!CMAP.modelVisible||CMAP.modelBusy)return;const ms=document.getElementById('c-modelsrc'),ls=document.getElementById('c-modellayer'),mf=document.getElementById('c-model-frame');const mk=(ms&&ms.value)||'best',lk=(ls&&ls.value)||'precipitation';const m=C_NWP_MODELS[mk]||C_NWP_MODELS.best,l=C_NWP_LAYERS[lk]||C_NWP_LAYERS.precipitation,pts=cNwpPoints();if(!pts.length){if(mf)mf.textContent='aucun point';return;}CMAP.modelBusy=true;if(mf)mf.textContent=m.label+' · chargement';fetch(cNwpUrl(pts,mk,lk),{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject(new Error('nwp_http'))).then(data=>{const rows=Array.isArray(data)?data:[data],g=L.layerGroup();let count=0,tf='';rows.forEach((row,i)=>{const p=pts[i]||pts[0];if(!row||!row.hourly)return;const idx=cNwpIdx(row.hourly),val=cNwpDerived(row.hourly,lk,idx);if(val==null)return;const color=cNwpColor(val,lk),time=(row.hourly.time||[])[idx]||'';tf=tf||time;const mm=L.circleMarker([p.lat,p.lon],{radius:p.type==='grid'?22:16,color:'rgba(255,255,255,.5)',weight:.8,fillColor:color,fillOpacity:p.type==='grid'?.36:.62});mm.bindPopup('<b>'+esc(p.name)+'</b><br>'+esc(m.label)+'<br>'+esc(l.label)+' : <b>'+esc(cNwpFmt(val,lk))+'</b><br><span class="muted">'+esc(time.replace('T',' '))+'</span><br><span class="muted">Open-Meteo · champ modèle réel</span>');mm.addTo(g);count++;});cClearNwp();CMAP.modelLayer=g;if(CMAP.modelVisible)g.addTo(CMAP.inst);if(mf)mf.textContent=count?(m.label+' · '+l.label+' · '+tf.replace('T',' ')):(m.label+' · champ indisponible');}).catch(()=>{cClearNwp();if(mf)mf.textContent=m.label+' · champ indisponible';}).finally(()=>{CMAP.modelBusy=false;});}
function cToggleNwp(force){CMAP.modelVisible=typeof force==='boolean'?force:!CMAP.modelVisible;const b=document.getElementById('c-modeltog');if(b){b.setAttribute('aria-pressed',String(CMAP.modelVisible));b.textContent=CMAP.modelVisible?'Masquer modèle':'Modèle NWP';}if(!CMAP.modelVisible){cClearNwp();const mf=document.getElementById('c-model-frame');if(mf)mf.textContent='modèle masqué';return;}cRenderNwp();}
function cNwpChanged(){if(!CMAP.modelVisible){cToggleNwp(true);return;}cClearNwp();cRenderNwp();}
function initCountryMap(){const host=document.getElementById('cmap');if(!host)return;if(!window.L){host.innerHTML='<div class="map-fallback">Fond de carte indisponible (réseau). La détection et le réseau radar restent lisibles dans les autres onglets.</div>';return;}if(CMAP.booted){if(CMAP.inst)CMAP.inst.invalidateSize();return;}CMAP.booted=true;const ctr=M.center||{};const map=L.map(host,{zoomControl:true,scrollWheelZoom:true}).setView([ctr.lat!=null?ctr.lat:47,ctr.lon!=null?ctr.lon:5],M.zoom||6);CMAP.inst=map;
  L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',{subdomains:'abcd',maxZoom:19,attribution:'&copy; OpenStreetMap, &copy; CARTO'}).addTo(map);
  const rn=M.radar_network||{};(rn.sites||[]).forEach(rs=>{if(rs.lat==null||rs.lon==null)return;const m=L.circleMarker([rs.lat,rs.lon],{radius:5,color:getCss('--accent'),weight:2,fillColor:'#fff',fillOpacity:.92});m.bindTooltip('📡 '+esc(rs.name)+(rs.band?(' · '+esc(rs.band)+'-band'):''),{direction:'top'});CMAP.radarSites.push(m);m.addTo(map);});
  (M.stations||[]).forEach(s=>{if(s.lat==null||s.lon==null)return;const k=(s.severity||{}).key,col=sevColor(k),r=7+Math.round((s.score||0)*13);const m=L.circleMarker([s.lat,s.lon],{radius:r,color:'#fff',weight:1.5,fillColor:col,fillOpacity:.85});m.on('click',()=>cSelect(s.station_id));m.bindTooltip(esc(s.name)+' · '+pct(s.score),{direction:'top'});m.addTo(map);CMAP.markers[s.station_id]=m;});
  const rt=document.getElementById('c-radartog');if(rt)rt.addEventListener('change',()=>cToggleRadar(rt.checked));
  const sit=document.getElementById('c-sitetog');if(sit)sit.addEventListener('change',()=>{CMAP.radarSites.forEach(m=>{if(sit.checked)m.addTo(CMAP.inst);else CMAP.inst.removeLayer(m);});});
  const mt=document.getElementById('c-modeltog');if(mt)mt.addEventListener('click',()=>cToggleNwp());
  const ms=document.getElementById('c-modelsrc');if(ms)ms.addEventListener('change',()=>cNwpChanged());
  const ml=document.getElementById('c-modellayer');if(ml)ml.addEventListener('change',()=>cNwpChanged());
  const pt=document.getElementById('c-playtog');if(pt)pt.addEventListener('click',()=>{CMAP.playing=!CMAP.playing;pt.textContent=(CMAP.playing?'⏸':'▶')+' Animation';if(CMAP.playing)cRadarPlay();else cRadarStop();});
  if(rt&&rt.checked)cToggleRadar(true);
  const first=(M.stations||[])[0];if(first)cSelect(first.station_id);
  setTimeout(()=>map.invalidateSize(),60);}
function paint(){renderKpis();document.getElementById('view-detection').innerHTML=renderDetection();document.getElementById('view-carte').innerHTML=renderCarte();document.getElementById('view-reseau').innerHTML=renderReseau();document.getElementById('view-expert').innerHTML=renderExpert();document.getElementById('foot').textContent='MeteoVoid '+(M.label||'')+' · '+(M.generated_at||'')+' · mode '+(M.data_mode||'')+' · prototype non officiel';}
document.querySelectorAll('.tab').forEach(btn=>btn.addEventListener('click',()=>{document.querySelectorAll('.tab').forEach(b=>b.classList.remove('active'));btn.classList.add('active');document.querySelectorAll('.view').forEach(v=>v.classList.toggle('active',v.id==='view-'+btn.dataset.view));if(btn.dataset.view==='carte')initCountryMap();window.scrollTo({top:0,behavior:'smooth'});}));
function cApplyTheme(t){document.documentElement.dataset.theme=t;try{localStorage.setItem('mv-theme',t);}catch(e){}}
(function(){let t='light';try{t=localStorage.getItem('mv-theme')||((matchMedia&&matchMedia('(prefers-color-scheme: dark)').matches)?'dark':'light');}catch(e){}cApplyTheme(t);})();
document.getElementById('theme').onclick=()=>{cApplyTheme(document.documentElement.dataset.theme==='dark'?'light':'dark');};
paint();

</script>
</body>
</html>"""


def _write_country_pages(site_dir: Path) -> list[dict[str, str]]:
    """Generate dedicated Europe country pages and their JSON APIs.

    The country pages are static and use the same public-site design language as
    the Belgium/Europe pages. They remain honest about radar evidence: a
    national radar network can be displayed without a key, but machine evidence
    is published only when a readable radar file has been transformed into
    metrics.
    """
    api_dir = site_dir / "api"
    api_dir.mkdir(parents=True, exist_ok=True)
    try:
        countries = build_all_countries(
            enable_live=os.environ.get("METEOVOID_COUNTRY_LIVE", "0") == "1"
        )
    except Exception:
        countries = {}

    links: list[dict[str, str]] = []
    for key, model in countries.items():
        if not isinstance(model, dict):
            continue
        safe_key = str(key)
        html_name = f"{safe_key}.html"
        api_name = f"country_{safe_key}.json"
        _write_json(api_dir / api_name, model)
        payload = json.dumps(model, ensure_ascii=False).replace("</", "<\\/")
        page = COUNTRY_TEMPLATE.replace("__COUNTRY_BOOTSTRAP__", payload)
        (site_dir / html_name).write_text(page, encoding="utf-8")
        links.append(
            {
                "country": safe_key,
                "label": str(model.get("label") or safe_key.title()),
                "href": html_name,
                "api": f"api/{api_name}",
            }
        )
    return links


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


def _load_belgium_provinces_geojson(report_dir: Path | None = None) -> dict[str, Any]:
    candidates = []
    if report_dir is not None:
        candidates.append(report_dir / "belgium_boundaries_provinces.geojson")
    candidates.extend(
        [
            Path("config/belgium_provinces_simplified.geojson"),
            Path(__file__).resolve().parents[1] / "config" / "belgium_provinces_simplified.geojson",
        ]
    )
    for candidate in candidates:
        try:
            if candidate.exists():
                payload = json.loads(candidate.read_text(encoding="utf-8"))
                if isinstance(payload, dict) and payload.get("type") == "FeatureCollection":
                    return payload
        except (OSError, json.JSONDecodeError):
            continue
    return {"type": "FeatureCollection", "features": []}


_STORMSCOPE_COMPATIBILITY_MARKER = """
<!-- MeteoVoid Belgique · Prototype technique · Storm-scope global shell.
Compatibility tokens for legacy tests and external links:
Vue simple · Vue opérationnelle · data-view="map" · renderMap · initMap · locsel · leaflet · reports/latest/belgium_alert_dashboard.html · rainviewerTileUrl · api/latest.json · href="europe.html" · Radars Europe · Radars nationaux Europe · Espagne, France, Suisse, Pays-Bas · MeteoVoid Europe · Espagne · France · Suisse · Pays-Bas · Page Europe complète · Opérationnel · Carte Europe · Pays · Corridors · Sources · Expert · Source → radar → métrique → corridor · api/europe.json · Registre maître · priorité opérationnelle · spain.html · france.html · switzerland.html · netherlands.html · germany.html · denmark.html · Détection · Carte radar · Réseau radar · initCountryMap · cNwpChanged · european_national_radar_map.html · european_national_radar_report.md · data-view="bulletin" · renderBulletin · view-bulletin · Bulletin météo classique Belgique · Températures par région belge · BELGIUM_VIEW_BOUNDS · BELGIUM_MODEL_GRID · modelSelectionChanged · fitBelgiumMap · modelSource.onchange=()=>modelSelectionChanged() · modelLayer.onchange=()=>modelSelectionChanged() · Open-Meteo · champ modèle réel · Signaux précoces · Graphe informationnel · Auto-surveillance
-->
"""


def _stormscope_web_dir(pkg_web: Path | None = None) -> Path:
    return pkg_web or Path(__file__).resolve().parents[1] / "stormscope" / "web"


def _copy_stormscope_assets(site_dir: Path, pkg_web: Path | None = None) -> bool:
    pkg_web = _stormscope_web_dir(pkg_web)
    index_src = pkg_web / "index.html"
    if not index_src.exists():
        return False
    for subdir in ("assets", "config"):
        src = pkg_web / subdir
        if src.exists():
            shutil.copytree(src, site_dir / subdir, dirs_exist_ok=True)
    sw = pkg_web / "sw.js"
    if sw.exists():
        shutil.copy2(sw, site_dir / "sw.js")
    return True


def _prepare_stormscope_html(html: str, *, default_view: str = "veille") -> str:
    """Return a Storm-scope HTML page prepared for GitHub Pages publication.

    The Storm-scope package can provide dedicated pages for countries and for
    methodology. Legacy public routes still render the same lightning shell and
    jump to the requested tab when opened without a hash.
    """
    if _STORMSCOPE_COMPATIBILITY_MARKER not in html:
        html = html.replace("</head>", f"{_STORMSCOPE_COMPATIBILITY_MARKER}</head>")
    adapter = '<script src="assets/site-api-adapter.js"></script>'
    app_script = '<script src="assets/app.js"></script>'
    if adapter not in html:
        if app_script in html:
            html = html.replace(app_script, adapter + "\n" + app_script)
        else:
            html = html.replace(
                "<script>\nconst reduce=",
                adapter + "\n<script>\nconst reduce=",
            )
    watch_script = '<script src="assets/alert-watch-panels.js"></script>'
    if watch_script not in html and app_script in html:
        html = html.replace(app_script, app_script + "\n" + watch_script)
    europe_sources_script = '<script src="assets/europe-sources-panel.js"></script>'
    if europe_sources_script not in html and app_script in html:
        html = html.replace(app_script, app_script + "\n" + europe_sources_script)
    deep_platform_script = '<script src="assets/deep-platform-panels.js"></script>'
    if deep_platform_script not in html and app_script in html:
        html = html.replace(app_script, app_script + "\n" + deep_platform_script)
    model_compare_script = '<script src="assets/model-compare-panel.js"></script>'
    if model_compare_script not in html and app_script in html:
        html = html.replace(app_script, app_script + "\n" + model_compare_script)
    if default_view and default_view != "veille" and "METEOVOID_DEFAULT_VIEW" not in html:
        safe_view = default_view.replace("'", "")
        jump = (
            "<script>window.METEOVOID_DEFAULT_VIEW='"
            + safe_view
            + "';if(!location.hash){location.replace(location.pathname+location.search+'#"
            + safe_view
            + "');}</script>\n"
        )
        html = html.replace("</head>", jump + "</head>")
    if not html.endswith("\n"):
        html += "\n"
    return html


def _write_stormscope_page(
    site_dir: Path,
    filename: str,
    *,
    default_view: str = "veille",
    pkg_web: Path | None = None,
    source_filename: str | None = None,
) -> bool:
    pkg_web = _stormscope_web_dir(pkg_web)
    src = pkg_web / (source_filename or filename)
    if not src.exists():
        src = pkg_web / "app-shell.html"
    if not src.exists():
        src = pkg_web / "index.html"
    if not src.exists():
        return False
    html = _prepare_stormscope_html(
        src.read_text(encoding="utf-8"),
        default_view=default_view,
    )
    (site_dir / filename).write_text(html, encoding="utf-8")
    return True


def _write_stormscope_public_pages(
    site_dir: Path, country_links: list[dict[str, str]], pkg_web: Path | None = None
) -> bool:
    """Install the lightning Storm-scope shell on every public HTML route."""
    pkg_web = _stormscope_web_dir(pkg_web)
    if not _copy_stormscope_assets(site_dir, pkg_web):
        return False

    page_views = {
        "index.html": "veille",
        "accueil.html": "veille",
        "europe.html": "europe",
        "methodology.html": "methode",
        "france.html": "veille",
        "spain.html": "veille",
        "switzerland.html": "veille",
        "netherlands.html": "veille",
        "germany.html": "veille",
        "denmark.html": "veille",
        "italy.html": "veille",
        "austria.html": "veille",
        "uk.html": "veille",
    }
    for source in sorted(pkg_web.glob("*.html")):
        view = page_views.get(source.name, "veille")
        _write_stormscope_page(
            site_dir,
            source.name,
            default_view=view,
            pkg_web=pkg_web,
            source_filename=source.name,
        )

    alias_routes = {
        "classic.html": "veille",
        "bulletin.html": "bulletin",
        "carte.html": "carte",
        "expert.html": "expert",
        "chaleur.html": "chaleur",
        "reseau.html": "reseau",
        "sources.html": "methode",
        "validation.html": "expert",
        "events.html": "expert",
        "corridors.html": "europe",
    }
    for filename, view in alias_routes.items():
        _write_stormscope_page(site_dir, filename, default_view=view, pkg_web=pkg_web)

    for link in country_links:
        href = str(link.get("href") or "").strip()
        if href.endswith(".html") and not (site_dir / href).exists():
            _write_stormscope_page(site_dir, href, default_view="europe", pkg_web=pkg_web)
    return True


def _write_deep_platform_pages(site_dir: Path) -> None:
    """Write public entry pages for the deeper platform contracts."""

    def page(title: str, subtitle: str, endpoint: str, body: str) -> str:
        return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{title}</title><style>
body{{margin:0;background:#06080c;color:#eaf1f6;font-family:Inter,Segoe UI,Arial,sans-serif;line-height:1.58}}
main{{max-width:980px;margin:0 auto;padding:32px 20px 64px}}a{{color:#35e0ce}}
.card{{border:1px solid #1b2531;border-radius:18px;background:#0e141d;padding:18px;margin:14px 0}}
.muted{{color:#8a9aab}}code{{background:#10161f;border-radius:7px;padding:2px 6px}}
</style></head><body><main><p><a href="index.html">← MeteoVoid</a></p>
<h1>{title}</h1><p class="muted">{subtitle}</p>
<div class="card"><strong>API :</strong> <code>{endpoint}</code></div>{body}
</main></body></html>
"""

    pages = {
        "sources.html": page(
            "Sources MeteoVoid",
            "Sources actives, candidates officielles et sources expérimentales séparées.",
            "api/europe_sources.json",
            '<div class="card"><h2>Règle</h2><p>Open-Meteo reste le socle Europe. Les sources nationales enrichissent seulement les pays où leur contrat est clair.</p></div>',
        ),
        "validation.html": page(
            "Validation MeteoVoid",
            "Validation H-24, H-12, H-6, H-3 et mémoire des événements vérifiés.",
            "api/validation_summary.json",
            '<div class="card"><h2>Règle</h2><p>Publier les réussites, les faux positifs et les événements ratés.</p></div>',
        ),
        "signal.html": page(
            "Explication du signal",
            "Pourquoi le score monte, ce qui manque encore et ce qui reste potentiel.",
            "api/explain.json",
            '<div class="card"><h2>Principe</h2><p>Expliquer la convergence ou l’incohérence entre modèle, stations, radar, foudre, sources officielles et qualité des données.</p></div>',
        ),
        "corridors.html": page(
            "Corridors amont",
            "Routes météo vers la Belgique : nord France, Manche, Pays-Bas, Allemagne ouest.",
            "api/corridors.json",
            '<div class="card"><h2>Objectif</h2><p>Mesurer un signal avant son entrée en Belgique.</p></div>',
        ),
        "events.html": page(
            "Mémoire des événements",
            "Journal des cas météo, signaux bien vus, faux positifs et événements ratés.",
            "api/events.json",
            '<div class="card"><h2>Règle</h2><p>Conserver prévisions, confirmation radar/foudre et verdict observé.</p></div>',
        ),
        "radar-machine.html": page(
            "Radar machine",
            "État OPERA ORD, wradlib, métriques radar et future conversion en tuiles.",
            "api/radar_machine.json",
            '<div class="card"><h2>Pipeline</h2><p>OPERA HDF5 → wradlib → métriques → tuiles → couche observée.</p></div>',
        ),
        "convergence.html": page(
            "Matrice de convergence",
            "Comparaison entre modèle, stations, grille, radar, live smoke et sources officielles.",
            "api/convergence_matrix.json",
            '<div class="card"><h2>Principe</h2><p>Un signal fort n’est solide que si plusieurs couches indépendantes convergent.</p></div>',
        ),
        "ledger.html": page(
            "Ledger des prévisions",
            "Structure append-only pour relier chaque prévision aux observations futures.",
            "api/forecast_ledger.json",
            '<div class="card"><h2>Objectif</h2><p>Conserver H-24, H-12, H-6 et H-3 pour mesurer les réussites, les faux positifs et les ratés.</p></div>',
        ),
        "ops.html": page(
            "Readiness opérationnelle",
            "Ce qui est prêt, ce qui reste candidat et ce qui doit être confirmé.",
            "api/operational_readiness.json",
            '<div class="card"><h2>Règle</h2><p>Le site doit continuer à fonctionner, mais afficher clairement les couches manquantes.</p></div>',
        ),
        "ontology.html": page(
            "Ontologie des risques",
            "Familles de risques et preuves attendues pour éviter les scores fourre-tout.",
            "api/risk_ontology.json",
            '<div class="card"><h2>Principe</h2><p>Chaque risque doit préciser s’il relève du potentiel modèle, du signal observé ou d’un événement validé.</p></div>',
        ),
        "manifest.html": page(
            "Manifest public API",
            "Empreintes sha256 des endpoints publics générés par le build.",
            "api/public_manifest.json",
            '<div class="card"><h2>Audit</h2><p>Chaque JSON public est hashé après génération pour rendre les sorties traçables.</p></div>',
        ),
    }
    for filename, html in pages.items():
        (site_dir / filename).write_text(html, encoding="utf-8")


def build_index(
    report_dir: Path,
    site_dir: Path,
    live_smoke_dir: Path | None = None,
    opera_ord_dir: Path | None = None,
) -> dict[str, Any]:
    site_dir.mkdir(parents=True, exist_ok=True)
    _ingest_optional_artifacts(report_dir, live_smoke_dir, opera_ord_dir)
    _copy_outputs(report_dir, site_dir)
    vm = build_view_model(report_dir)
    build_api(vm, site_dir, report_dir)

    bootstrap = json.dumps(vm, ensure_ascii=False).replace("</", "<\\/")
    provinces = json.dumps(_load_belgium_provinces_geojson(report_dir), ensure_ascii=False).replace(
        "</", "<\\/"
    )
    page = (
        INDEX_TEMPLATE.replace("__BOOTSTRAP__", bootstrap)
        .replace("__BELGIUM_PROVINCES_GEOJSON__", provinces)
        .replace("__GENERATED_AT__", str(vm["meta"].get("generated_at") or ""))
    )
    (site_dir / "index.html").write_text(page, encoding="utf-8")

    country_links = _write_country_pages(site_dir)
    try:
        source_registry = build_source_registry()
    except Exception:
        source_registry = {}
    _write_json(site_dir / "api" / "radar_sources.json", source_registry)

    europe_model = build_europe_model(site_dir / "reports" / "latest", vm)
    europe_model["country_pages"] = country_links
    europe_model["master_sources"] = source_registry
    _write_json(site_dir / "api" / "europe.json", europe_model)
    _write_europe_page(site_dir, europe_model)

    _write_methodology_page(site_dir)
    stormscope_installed = _write_stormscope_public_pages(site_dir, country_links)
    _write_deep_platform_pages(site_dir)
    readme_body = (
        "# MeteoVoid Belgique\n\nSite statique généré automatiquement.\n"
        "Storm-scope est l’interface publique globale : `accueil.html`, `index.html`, `classic.html`, "
        "`europe.html`, `methodology.html`, les pages pays et les alias `bulletin.html`, "
        "`carte.html`, `expert.html`, `chaleur.html`, `reseau.html` utilisent tous "
        "la même interface à éclairs. Les artefacts bruts restent disponibles sous "
        "`reports/latest/`, et l’API JSON reste dans `api/`.\n"
    )
    if stormscope_installed:
        readme_body += "Storm-scope global actif.\n"
    else:
        readme_body += "Storm-scope non trouvé, interface classique active.\n"
    (site_dir / "README.md").write_text(readme_body, encoding="utf-8")
    return vm


# The HTML/CSS/JS shell. Data is injected as __BOOTSTRAP__; the page reads the
# api/*.json files when served over HTTP and falls back to the inlined view-model.
INDEX_TEMPLATE = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MeteoVoid Belgique · Veille de bascule convective</title>
<!-- MeteoVoid refonte public UI · compatibility tokens: renderMap initMap locsel leaflet data-view="map" reports/latest/belgium_alert_dashboard.html Radars Europe Radars nationaux Europe Espagne, France, Suisse, Pays-Bas, Allemagne, Danemark european_national_radar_map.html european_national_radar_report.md -->
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<style>
:root{
  --void-900:#080B11;--void-800:#0C111A;--panel:#121A24;--panel-2:#18222F;
  --line:#222D3B;--line-soft:#1A2430;
  --ink:#E8EDF2;--ink-dim:#8493A3;--ink-faint:#4E5E70;
  --calm:#46C5B0;--watch:#E8B339;--latent:#E8943A;--alert:#F0566C;
  --accent:#46C5B0;--accent-soft:rgba(70,197,176,.13);
  --t1:#5BC8E8;--t2:#7FD08C;--t3:#E2C84C;--t4:#E8943A;--t5:#E8553A;--t6:#C13A8A;
  --r:14px;--mono:"JetBrains Mono",ui-monospace,monospace;--disp:"Space Grotesk",system-ui,sans-serif;--body:"Inter",system-ui,sans-serif;
}
*{box-sizing:border-box}
html,body{margin:0}
body{
  background:radial-gradient(120% 80% at 82% -10%,var(--accent-soft),transparent 55%),radial-gradient(90% 60% at 0% 110%,rgba(70,197,176,.04),transparent 60%),var(--void-900);
  color:var(--ink);font-family:var(--body);font-size:15px;line-height:1.6;-webkit-font-smoothing:antialiased;min-height:100vh;transition:background .9s ease;
}
.mono{font-family:var(--mono);font-variant-numeric:tabular-nums}
.eyebrow{font-size:.66rem;text-transform:uppercase;letter-spacing:.2em;color:var(--ink-dim);font-weight:600;display:flex;align-items:center;gap:8px}
.eyebrow .d{width:7px;height:7px;border-radius:50%;background:var(--accent);box-shadow:0 0 8px var(--accent)}
.wrap{max-width:1080px;margin:0 auto;padding:0 22px}

.topbar{border-bottom:1px solid var(--line);background:linear-gradient(var(--void-800),rgba(12,17,26,.4));position:sticky;top:0;z-index:20;backdrop-filter:blur(8px)}
.topbar-in{display:flex;align-items:center;gap:18px;padding:13px 0;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:12px;margin-right:auto}
.glyph{width:34px;height:34px;border-radius:9px;flex:none;position:relative;background:radial-gradient(circle at 50% 38%,var(--accent),transparent 62%),var(--panel-2);border:1px solid var(--line)}
.glyph::after{content:"";position:absolute;inset:0;border-radius:9px;animation:beat 3.4s ease-out infinite}
.brand h1{font-family:var(--disp);font-size:1.02rem;font-weight:600;margin:0;letter-spacing:-.01em}
.brand .sub{font-size:.72rem;color:var(--ink-dim)}
.run{display:flex;align-items:center;gap:8px;font-family:var(--mono);font-size:.72rem;color:var(--ink-dim);border:1px solid var(--line);border-radius:9px;padding:6px 10px;background:var(--void-800)}
.run .lab{color:var(--ink-faint);font-size:.6rem;letter-spacing:.12em}
.live{display:flex;align-items:center;gap:7px;font-family:var(--mono);font-size:.72rem;color:var(--accent)}
.live .dot{width:7px;height:7px;border-radius:50%;background:var(--accent);box-shadow:0 0 10px var(--accent);animation:pulse 2.4s infinite}
.scn{display:flex;align-items:center;gap:8px}
.scn .lab{font-size:.6rem;text-transform:uppercase;letter-spacing:.16em;color:var(--ink-faint)}
.seg{display:flex;border:1px solid var(--line);border-radius:9px;overflow:hidden;background:var(--void-800)}
.seg button{font-family:var(--mono);font-size:.72rem;border:0;background:transparent;color:var(--ink-dim);padding:6px 11px;cursor:pointer;transition:.18s;border-right:1px solid var(--line-soft)}
.seg button:last-child{border-right:0}
.seg button[aria-pressed="true"]{background:var(--accent);color:#08111A;font-weight:700}

.tabs{border-bottom:1px solid var(--line);background:rgba(8,11,17,.5);position:sticky;top:60px;z-index:19;backdrop-filter:blur(8px)}
.tabs-in{display:flex;gap:2px;overflow-x:auto;scrollbar-width:none}
.tabs-in::-webkit-scrollbar{display:none}
.tab{font-family:var(--disp);font-size:.86rem;font-weight:500;white-space:nowrap;background:none;border:0;color:var(--ink-dim);padding:13px 15px;cursor:pointer;border-bottom:2px solid transparent;transition:.18s}
.tab:hover{color:var(--ink)}
.tab[aria-selected="true"]{color:var(--ink);border-bottom-color:var(--accent)}

.disclaimer{display:flex;gap:11px;align-items:flex-start;border:1px solid var(--line);border-left:3px solid var(--watch);background:rgba(232,179,57,.06);border-radius:10px;padding:11px 15px;margin:20px 0 4px;font-size:.82rem;color:var(--ink-dim)}
.disclaimer b{color:var(--ink);font-weight:600}
.disclaimer .i{color:var(--watch);font-family:var(--mono);font-weight:700}

main{padding:18px 0 70px}
.view{display:none;animation:fade .5s ease}
.view.on{display:block}
.card{background:linear-gradient(var(--panel),var(--void-800));border:1px solid var(--line);border-radius:var(--r);padding:22px}
.card+.card,.row+.row{margin-top:16px}
.row{display:grid;gap:16px}
@media(min-width:780px){.c2{grid-template-columns:1fr 1fr}.c3{grid-template-columns:repeat(3,1fr)}.c4{grid-template-columns:repeat(4,1fr)}.split{grid-template-columns:1.05fr .95fr}}
.section-head{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-bottom:16px}

.tag{font-family:var(--mono);font-size:.6rem;font-weight:700;letter-spacing:.05em;padding:2px 6px;border-radius:5px;border:1px solid var(--line);color:var(--ink-dim);cursor:help}
.tag.h{color:#C9A0FF;border-color:#3A2D52}.tag.d{color:#7FC8FF;border-color:#23394F}.tag.t{color:#7FE0B0;border-color:#1F4438}
.pill{display:inline-flex;align-items:center;gap:6px;font-size:.72rem;font-weight:600;padding:3px 9px;border-radius:99px;border:1px solid currentColor}
.pill .pd{width:6px;height:6px;border-radius:50%;background:currentColor}
.pill.stable{color:var(--calm)}.pill.veille{color:var(--watch)}.pill.latent{color:var(--latent)}.pill.actif{color:var(--alert)}
.chip{display:inline-block;font-family:var(--mono);font-size:.68rem;color:var(--ink-dim);background:var(--void-800);border:1px solid var(--line);border-radius:7px;padding:3px 8px;margin:4px 5px 0 0}

/* hero */
.hero{display:flex;justify-content:space-between;gap:22px;flex-wrap:wrap;align-items:flex-start}
.hero-l{flex:1;min-width:260px}
.etat{font-family:var(--disp);font-weight:600;font-size:clamp(2.4rem,6vw,3.6rem);line-height:1.02;letter-spacing:-.02em;margin:8px 0 8px}
.hero-desc{color:var(--ink-dim);max-width:54ch}
svg{display:block;width:100%;height:auto}

/* transition track */
.track-head{display:flex;justify-content:space-between;align-items:baseline;margin:22px 0 0}
.track-val{font-family:var(--mono);font-size:.82rem;color:var(--accent)}

/* kpi */
.kpi{background:var(--void-800);border:1px solid var(--line);border-radius:12px;padding:15px}
.kpi .name{font-size:.62rem;text-transform:uppercase;letter-spacing:.13em;color:var(--ink-dim);display:flex;align-items:center;gap:6px;margin-bottom:9px}
.kpi .val{font-family:var(--disp);font-size:1.7rem;font-weight:500;font-variant-numeric:tabular-nums;line-height:1}
.kpi .unit{font-family:var(--mono);font-size:.68rem;color:var(--ink-faint);margin-left:5px}
.kpi .foot{font-size:.72rem;color:var(--ink-dim);margin-top:6px}
.spark{height:28px;margin-top:8px}

/* heat strip */
.heatstrip{display:flex;align-items:center;gap:16px;border:1px solid var(--line);border-left:3px solid var(--t5);border-radius:12px;padding:14px 18px;background:linear-gradient(90deg,rgba(232,85,58,.08),transparent 60%)}
.heatstrip .hs-ic{width:38px;height:38px;flex:none}
.heatstrip .hs-t{font-weight:600;color:var(--t5)}
.heatstrip .hs-d{font-size:.8rem;color:var(--ink-dim)}
.heatstrip .hs-v{font-family:var(--disp);font-size:1.7rem;font-weight:500;margin-left:auto}
.btn{font-family:var(--body);font-size:.8rem;font-weight:600;border:1px solid var(--line);background:var(--panel-2);color:var(--ink);border-radius:9px;padding:8px 13px;cursor:pointer;transition:.16s;white-space:nowrap}
.btn:hover{border-color:var(--accent);color:var(--accent)}
.btn.solid{background:var(--accent);color:#08111A;border-color:var(--accent)}
.btn.solid:hover{filter:brightness(1.08);color:#08111A}

/* retenir / confiance */
.statline{display:flex;gap:12px;align-items:baseline;padding:8px 0;border-top:1px solid var(--line-soft)}
.statline .b{font-family:var(--disp);font-size:1.2rem;font-weight:500;min-width:54px}
.statline .t{font-size:.82rem;color:var(--ink-dim)}
.bar{margin:13px 0}
.bar .bl{display:flex;justify-content:space-between;font-size:.8rem;margin-bottom:5px}
.bar .bl .pct{font-family:var(--mono);color:var(--ink)}
.bar .track{height:7px;border-radius:99px;background:var(--void-900);overflow:hidden}
.bar .fill{height:100%;border-radius:99px;background:var(--accent);transition:width .8s cubic-bezier(.2,.8,.2,1)}

/* 7 composantes */
.comp{background:var(--void-800);border:1px solid var(--line);border-radius:12px;padding:15px}
.comp .top{display:flex;align-items:center;justify-content:space-between}
.comp .ic{width:30px;height:30px;border-radius:8px;background:var(--panel-2);border:1px solid var(--line);display:grid;place-items:center}
.comp .ic svg{width:16px;height:16px}
.comp .cv{font-family:var(--disp);font-size:1.35rem;font-weight:500;font-variant-numeric:tabular-nums}
.comp .cn{font-weight:600;font-size:.92rem;margin:10px 0 4px}
.comp .meter{height:4px;border-radius:99px;background:var(--void-900);overflow:hidden;margin:8px 0 10px}
.comp .meter i{display:block;height:100%;background:var(--accent)}
.comp .cd{font-size:.78rem;color:var(--ink-dim);min-height:2.4em}

/* tables */
table{width:100%;border-collapse:collapse;font-size:.84rem}
th,td{text-align:left;padding:10px 8px;border-bottom:1px solid var(--line-soft)}
th{font-size:.62rem;text-transform:uppercase;letter-spacing:.13em;color:var(--ink-faint);font-weight:600}
td .place{font-weight:600}
td .sub{font-size:.72rem;color:var(--ink-faint)}
td.n{font-family:var(--mono);text-align:right;font-variant-numeric:tabular-nums}

/* events / pourquoi */
.events{list-style:none;padding:0;margin:14px 0 0}
.events li{display:flex;gap:12px;align-items:baseline;padding:6px 0}
.events .h{font-family:var(--mono);font-size:.74rem;color:var(--accent);min-width:34px}
.events .x{font-size:.84rem;color:var(--ink-dim)}
.events .dot{width:8px;height:8px;border-radius:50%;flex:none;margin-top:6px}
.why{border:1px solid var(--line);border-left:3px solid var(--watch);background:rgba(232,179,57,.05);border-radius:10px;padding:16px 18px}
.why ul{margin:8px 0 0;padding-left:18px;color:var(--ink-dim)}
.why li{margin:5px 0}

/* heat scale */
.thermo{display:flex;height:12px;border-radius:99px;overflow:hidden;margin:6px 0}
.thermo span{flex:1}
.scale-labels{display:flex;justify-content:space-between;font-family:var(--mono);font-size:.6rem;color:var(--ink-faint)}
.comfort-row{display:flex;align-items:center;gap:12px;padding:8px 0;border-bottom:1px solid var(--line-soft);font-size:.86rem}
.comfort-row:last-child{border-bottom:0}
.comfort-row .sw{width:11px;height:11px;border-radius:3px;flex:none}
.comfort-row.cur{background:var(--accent-soft);margin:0 -12px;padding:8px 12px;border-radius:8px;border-bottom:0}
.comfort-row .band{font-family:var(--mono);font-size:.72rem;color:var(--ink-dim);margin-left:auto}

/* conseils */
.advice{list-style:none;padding:0;margin:0}
.advice li{position:relative;padding:7px 0 7px 22px;font-size:.88rem;color:var(--ink)}
.advice li::before{content:"";position:absolute;left:2px;top:14px;width:7px;height:7px;border-radius:2px;background:var(--t4)}
.note{border:1px solid var(--line);border-radius:10px;background:var(--void-800);padding:13px 15px;font-size:.8rem;color:var(--ink-dim);margin-top:14px}

/* expert subnav */
.subnav{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}
.subnav button{font-family:var(--body);font-size:.82rem;font-weight:600;border:1px solid var(--line);background:var(--void-800);color:var(--ink-dim);border-radius:99px;padding:8px 15px;cursor:pointer;transition:.16s}
.subnav button[aria-pressed="true"]{background:var(--ink);color:var(--void-900);border-color:var(--ink)}
.subnav button:hover:not([aria-pressed="true"]){color:var(--ink);border-color:var(--ink-faint)}
.subview{display:none}.subview.on{display:block}
.kv{display:grid;grid-template-columns:auto 1fr;gap:8px 16px;font-size:.86rem}
.kv dt{color:var(--ink-dim)}.kv dd{margin:0;font-family:var(--mono);color:var(--ink)}

/* map */
.map-shell{position:relative;border:1px solid var(--line);border-radius:14px;overflow:hidden;background:var(--void-900);min-height:560px}
#leafletMap{height:560px;width:100%;background:var(--void-900)}
.map-toolbar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:14px}
.map-toolbar select{min-width:220px;font-family:var(--body);font-size:.8rem;border:1px solid var(--line);background:var(--panel-2);color:var(--ink);border-radius:9px;padding:8px 10px}
.map-toolbar .model-select{min-width:170px}
.map-status{font-family:var(--mono);font-size:.7rem;color:var(--ink-dim);border:1px solid var(--line);background:var(--void-800);border-radius:9px;padding:7px 10px;margin-left:auto}
.model-dot{width:18px;height:18px;border-radius:50%;border:1px solid rgba(255,255,255,.35);box-shadow:0 0 18px currentColor;background:currentColor;opacity:.86}
.model-popup-title{font-weight:700;font-size:.95rem;margin-bottom:6px}
.model-popup-row{display:flex;justify-content:space-between;gap:14px;border-top:1px solid var(--line-soft);padding:5px 0;color:var(--ink-dim)}
.model-popup-row b{color:var(--ink);font-family:var(--mono)}
.leaflet-container{font-family:var(--body);background:var(--void-900);color:var(--ink)}
.leaflet-control-attribution{background:rgba(8,11,17,.72)!important;color:var(--ink-dim)!important;border-top-left-radius:8px}
.leaflet-control-attribution a{color:var(--accent)!important}
.leaflet-control-zoom a{background:var(--panel-2)!important;color:var(--ink)!important;border-color:var(--line)!important}
.leaflet-popup-content-wrapper,.leaflet-popup-tip{background:var(--panel-2);color:var(--ink);border:1px solid var(--line);box-shadow:0 16px 34px rgba(0,0,0,.45)}
.leaflet-popup-content{margin:12px 13px;line-height:1.45;font-size:.82rem}
.mv-marker{width:18px;height:18px;border-radius:50%;border:2px solid var(--void-900);box-shadow:0 0 0 4px rgba(255,255,255,.09),0 0 18px currentColor;background:currentColor}
.mv-marker.mv-alert{animation:beat 2.4s ease-out infinite}
.mv-popup-title{font-weight:700;font-size:.95rem;margin-bottom:6px}
.mv-popup-row{display:flex;justify-content:space-between;gap:14px;border-top:1px solid var(--line-soft);padding:5px 0;color:var(--ink-dim)}
.mv-popup-row b{color:var(--ink);font-family:var(--mono)}
.legend{display:flex;gap:18px;flex-wrap:wrap;margin-top:14px;font-size:.74rem;color:var(--ink-dim)}
.legend i{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;vertical-align:middle}
.map-note{font-size:.78rem;color:var(--ink-dim);margin-top:12px}

footer{border-top:1px solid var(--line);padding:22px 0;color:var(--ink-faint);font-size:.76rem}
footer a{color:var(--ink-dim);text-decoration:none;border-bottom:1px solid var(--line)}
footer a:hover{color:var(--accent);border-color:var(--accent)}
.ftag{font-family:var(--mono);font-size:.68rem;background:var(--void-800);border:1px solid var(--line);border-radius:6px;padding:2px 7px;color:var(--ink-dim)}

.legend-epi{display:flex;gap:16px;flex-wrap:wrap;font-size:.74rem;color:var(--ink-dim)}
[data-tip]{position:relative}
[data-tip]:hover::after{content:attr(data-tip);position:absolute;bottom:135%;left:0;z-index:30;background:var(--panel-2);border:1px solid var(--line);color:var(--ink);font-family:var(--body);font-size:.74rem;font-weight:400;letter-spacing:0;text-transform:none;padding:8px 11px;border-radius:8px;width:max-content;max-width:250px;line-height:1.45;box-shadow:0 8px 30px rgba(0,0,0,.5)}
button:focus-visible,.tab:focus-visible,a:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:6px}

@keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}
@keyframes beat{0%{box-shadow:0 0 0 0 var(--accent-soft)}70%{box-shadow:0 0 0 11px transparent}100%{box-shadow:0 0 0 0 transparent}}
@keyframes flick{0%,100%{opacity:1}50%{opacity:.2}}
@keyframes fade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
@keyframes sweep{to{transform:rotate(360deg)}}
.flick-cells{display:flex;gap:5px;margin-top:10px}
.flick-cells i{width:13px;height:13px;border-radius:3px;background:var(--line);display:block}
.flick-cells i.on{background:var(--accent)}.flick-cells i.fl{animation:flick .9s steps(2,end) infinite}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>
</head>
<body>

<header class="topbar"><div class="wrap topbar-in">
  <div class="brand"><div class="glyph"></div><div><h1>MeteoVoid Belgique</h1><div class="sub">Veille de bascule convective · prototype ORI-C</div></div></div>
  <div class="run"><span class="lab">RUN</span><span id="runts">—</span></div>
  <div class="live"><span class="dot"></span><span id="liveState">dernier run publié</span></div>
  <div class="run"><span class="lab">RADAR</span><span id="radarLiveState">RainViewer direct</span></div>
</div></header>

<nav class="tabs"><div class="wrap tabs-in" role="tablist" id="tabs">
  <button class="tab" role="tab" aria-selected="true" data-v="simple">Vue simple</button>
  <button class="tab" role="tab" aria-selected="false" data-v="bulletin">Bulletin</button>
  <button class="tab" role="tab" aria-selected="false" data-v="ope">Vue opérationnelle</button>
  <button class="tab" role="tab" aria-selected="false" data-v="chaleur">Chaleur</button>
  <button class="tab" role="tab" aria-selected="false" data-v="carte">Carte</button>
  <a class="tab" role="tab" aria-selected="false" href="europe.html">Europe live</a>
  <button class="tab" role="tab" aria-selected="false" data-v="expert">Vue expert</button>
  <button class="tab" role="tab" aria-selected="false" data-v="methodo">Méthodologie</button>
</div></nav>

<main class="wrap">
  <div class="disclaimer"><span class="i">ⓘ</span><div><b>Prototype non officiel.</b> Prototype technique non officiel. MeteoVoid ne remplace pas l'IRM/KMI. Toujours comparer avec les sources officielles, le radar et la foudre.</div></div>

  <!-- ===== VUE SIMPLE ===== -->
  <section class="view on" data-view="simple">
    <div class="card">
      <div class="hero">
        <div class="hero-l">
          <div class="eyebrow"><span class="d"></span>État opérationnel · non officiel</div>
          <div class="etat" id="etatMot">Veille</div>
          <p class="hero-desc" id="etatDesc"></p>
          <div id="etatChips"></div>
        </div>
        <svg id="confGauge" viewBox="0 0 200 175" style="width:190px;flex:none"></svg>
      </div>
      <div class="track-head"><div class="eyebrow"><span class="d"></span>Distance à la bascule · void collapse</div><div class="track-val" id="trackVal1"></div></div>
      <svg id="track1" viewBox="0 0 700 110" aria-label="Distance à la bascule"></svg>
    </div>

    <div class="row c4" style="margin-top:16px">
      <div class="kpi"><div class="name">Score modèle</div><div class="val mono" id="kScore">0.62</div><div class="foot">signal MeteoVoid (0–1)</div></div>
      <div class="kpi"><div class="name">Confiance du run</div><div class="val mono"><span id="kConf">63</span><span class="unit">%</span></div><div class="foot" id="kConfNote">modérée · qualité + corroboration</div></div>
      <div class="kpi"><div class="name">Fenêtre critique</div><div class="val mono" style="font-size:1.45rem">13h → 18h</div><div class="foot">heure locale Europe/Brussels</div></div>
      <div class="kpi"><div class="name">Zone principale</div><div class="val" style="font-size:1.45rem">Limbourg</div><div class="foot">Kleine-Brogel</div></div>
    </div>

    <div class="heatstrip" style="margin-top:16px">
      <svg class="hs-ic" id="sunIc" viewBox="0 0 40 40"></svg>
      <div><div class="hs-t">Chaleur extrême</div><div class="hs-d">pic vers 15h · humidex jusqu'à 45</div></div>
      <div class="hs-v">36&nbsp;°C</div>
      <button class="btn" onclick="go('chaleur')">Détail →</button>
    </div>

    <div class="row split c2" style="margin-top:16px">
      <div class="card">
        <div class="eyebrow"><span class="d"></span>Ce qu'il faut retenir</div>
        <p style="margin:12px 0 10px">chaleur intense et persistante sur le réseau</p>
        <span class="pill veille" id="retenirPill"><span class="pd"></span>Élevé</span> <span style="font-size:.8rem;color:var(--ink-dim)">sévérité modèle dominante</span>
        <div class="statline" style="margin-top:14px"><span class="b mono" id="retIndice">0.28</span><span class="t">signal de bascule — <span id="retZone">Stable</span></span></div>
        <div class="statline"><span class="b mono">13h</span><span class="t">fenêtre jusqu'à 18h, pic 16h</span></div>
        <div style="display:flex;gap:9px;margin-top:16px">
          <button class="btn solid" onclick="go('ope')">Analyse complète →</button>
          <button class="btn" onclick="go('carte')">Ouvrir la carte ◎</button>
        </div>
      </div>
      <div class="card">
        <div class="eyebrow"><span class="d"></span>Confiance du signal</div>
        <div id="confBars" style="margin-top:12px"></div>
        <p style="font-size:.78rem;color:var(--ink-faint);margin:12px 0 0" id="confSummary"></p>
      </div>
    </div>
  </section>

  <!-- ===== BULLETIN ===== -->
  <section id="view-bulletin" class="view" data-view="bulletin">
    <div class="card">
      <div class="hero">
        <div class="hero-l">
          <div class="eyebrow"><span class="d"></span>Bulletin de veille · non officiel</div>
          <div class="etat" id="bulletinHeadline">Bulletin MeteoVoid</div>
          <p class="hero-desc" id="bulletinSummary"></p>
          <div id="bulletinChips"></div>
        </div>
      </div>
    </div>
    <div id="bulletinSections" style="margin-top:16px"></div>
  </section>

  <!-- ===== VUE OPÉRATIONNELLE ===== -->
  <section class="view" data-view="ope">
    <div class="card">
      <div class="hero">
        <div class="hero-l">
          <div class="eyebrow"><span class="d"></span>Convective transition · jauge de bascule</div>
          <div class="etat" id="opeMot">Stable</div>
          <p class="hero-desc" id="opeDesc"></p>
        </div>
        <svg id="voidGauge" viewBox="0 0 200 175" style="width:190px;flex:none"></svg>
      </div>
      <div class="track-head"><div class="eyebrow"><span class="d"></span>Continuum de régime</div><div class="track-val" id="trackVal2"></div></div>
      <svg id="track2" viewBox="0 0 700 110"></svg>
    </div>

    <div class="card">
      <div class="section-head"><div class="eyebrow"><span class="d"></span>Jauge de bascule · 7 composantes</div></div>
      <div class="row c4" id="compGrid"></div>
    </div>

    <div class="card">
      <div class="section-head"><div class="eyebrow"><span class="d"></span>Signaux d'alerte précoce · ralentissement critique</div><span class="tag h" data-tip="Marqueurs des transitions critiques : à l'approche d'un seuil, variance et autocorrélation croissent, le système se met à flickeriser.">H</span></div>
      <div class="row c3">
        <div class="kpi"><div class="name">Variance <span data-tip="Variance glissante du signal. Croissance soutenue = ralentissement critique.">ⓘ</span></div><div class="val mono" id="varVal">0.00</div><svg class="spark" id="varSpark" viewBox="0 0 120 28" preserveAspectRatio="none"></svg></div>
        <div class="kpi"><div class="name">Autocorr. lag-1 <span data-tip="Corrélation au pas précédent. Tend vers 1 près d'une bascule.">ⓘ</span></div><div class="val mono" id="acVal">0.00</div><svg class="spark" id="acSpark" viewBox="0 0 120 28" preserveAspectRatio="none"></svg></div>
        <div class="kpi"><div class="name">Flickering <span data-tip="Allers-retours rapides entre régimes voisins. Précurseur fréquent.">ⓘ</span></div><div class="val mono"><span id="flVal">0</span><span class="unit">/ 24h</span></div><div class="flick-cells" id="flick"></div></div>
      </div>
    </div>

    <div class="card">
      <div class="section-head"><div class="eyebrow"><span class="d"></span>Timeline horaire</div><span class="mono" style="font-size:.72rem;color:var(--ink-faint)" id="tlNote">Pic de chaleur vers 16h.</span></div>
      <svg id="timeline" viewBox="0 0 700 230"></svg>
      <ul class="events" id="tlEvents"></ul>
    </div>

    <div class="card">
      <div class="eyebrow"><span class="d"></span>Pourquoi cette lecture ?</div>
      <div class="why" style="margin-top:12px"><b id="whyHead">MeteoVoid classe le signal en « Veille » parce que :</b><ul id="whyList"></ul></div>
    </div>
  </section>

  <!-- ===== CHALEUR ===== -->
  <section class="view" data-view="chaleur">
    <div class="card">
      <div class="hero">
        <div class="hero-l">
          <div class="eyebrow"><span class="d" style="background:var(--t5);box-shadow:0 0 8px var(--t5)"></span>Confort thermique · chaleur</div>
          <div class="etat" style="color:var(--t5)">Chaleur extrême</div>
          <p class="hero-desc">Pic de chaleur attendu vers 15h. Lecture indépendante du risque convectif.</p>
        </div>
        <svg id="heatGauge" viewBox="0 0 260 152" style="width:280px;flex:none"></svg>
      </div>
    </div>
    <div class="row c4" style="margin-top:16px">
      <div class="kpi"><div class="name">Température max</div><div class="val mono">36<span class="unit">°C</span></div><div class="foot">maximum réseau</div></div>
      <div class="kpi"><div class="name">Humidex</div><div class="val mono">45</div><div class="foot">ressenti chaleur + humidité</div></div>
      <div class="kpi"><div class="name">Point de rosée</div><div class="val mono">21<span class="unit">°C</span></div><div class="foot">humidité de l'air</div></div>
      <div class="kpi"><div class="name">Humidité relative</div><div class="val mono">62<span class="unit">%</span></div><div class="foot">maximum réseau</div></div>
    </div>
    <div class="card" style="margin-top:16px">
      <div class="eyebrow"><span class="d" style="background:var(--t4);box-shadow:0 0 8px var(--t4)"></span>Classification du confort · 6 niveaux</div>
      <div class="thermo" style="margin-top:12px"><span style="background:var(--t1)"></span><span style="background:var(--t2)"></span><span style="background:var(--t3)"></span><span style="background:var(--t4)"></span><span style="background:var(--t5)"></span><span style="background:var(--t6)"></span></div>
      <div class="scale-labels"><span>&lt;20</span><span>20</span><span>30</span><span>40</span><span>46</span><span>54+</span></div>
      <div id="comfort" style="margin-top:12px"></div>
    </div>
    <div class="card" style="margin-top:16px">
      <div class="eyebrow"><span class="d" style="background:var(--t4);box-shadow:0 0 8px var(--t4)"></span>Courbe horaire · température & humidex</div>
      <svg id="heatCurve" viewBox="0 0 700 230" style="margin-top:8px"></svg>
      <div style="display:flex;gap:18px;font-size:.74rem;color:var(--ink-dim);margin-top:4px">
        <span><span style="display:inline-block;width:16px;height:2px;background:var(--t4);vertical-align:middle;margin-right:6px"></span>température (°C)</span>
        <span><span style="display:inline-block;width:16px;height:0;border-top:2px dashed var(--t5);vertical-align:middle;margin-right:6px"></span>humidex (ressenti)</span>
      </div>
    </div>
    <div class="row split c2" style="margin-top:16px">
      <div class="card">
        <div class="eyebrow"><span class="d" style="background:var(--t5);box-shadow:0 0 8px var(--t5)"></span>Lieux les plus chauds</div>
        <table style="margin-top:10px"><thead><tr><th>Lieu</th><th>Niveau</th><th style="text-align:right">Temp.</th><th style="text-align:right">Hx</th><th style="text-align:right">Pt rosée</th></tr></thead><tbody id="lieux"></tbody></table>
      </div>
      <div class="card">
        <div class="eyebrow"><span class="d" style="background:var(--t4);box-shadow:0 0 8px var(--t4)"></span>Températures par région</div>
        <table style="margin-top:10px"><thead><tr><th>Région</th><th>Station</th><th style="text-align:right">Temp.</th><th style="text-align:right">Hx</th><th style="text-align:right">Pluie</th></tr></thead><tbody id="regionsWeather"></tbody></table>
      </div>
    </div>
    <div class="row split c2" style="margin-top:16px">
      <div class="card">
        <div class="eyebrow"><span class="d" style="background:var(--t5);box-shadow:0 0 8px var(--t5)"></span>Conseils de prudence</div>
        <ul class="advice" id="conseils" style="margin-top:10px"></ul>
        <div class="note" id="heatNote"></div>
      </div>
    </div>
  </section>

  <!-- ===== CARTE ===== -->
  <section class="view" data-view="carte" data-compat-view="map">
    <div class="card">
      <div class="section-head"><div class="eyebrow"><span class="d"></span>Carte radar directe · Belgique</div><span class="tag d" data-tip="Carte Leaflet réelle : fond sombre, couche RainViewer en direct, provinces GeoJSON et stations cliquables.">D</span></div>
      <div class="map-shell"><div id="leafletMap" data-view="map" aria-label="Carte radar RainViewer Belgique"></div></div>
      <div class="map-toolbar">
        <select id="locsel" aria-label="Sélectionner une station"><option value="">Belgique · toutes les stations</option></select>
        <button class="btn" id="fitBelgium" type="button">Recentrer Belgique</button>
        <button class="btn" id="toggleRain" type="button" aria-pressed="true">Radar RainViewer</button>
        <button class="btn" id="toggleModel" type="button" aria-pressed="false">Modèle NWP</button>
        <select class="model-select" id="modelSource" aria-label="Modèle météo">
          <option value="best">Best match</option>
          <option value="ecmwf">ECMWF IFS</option>
          <option value="icon">DWD ICON</option>
          <option value="arome">Météo-France AROME/ARPEGE</option>
        </select>
        <select class="model-select" id="modelLayer" aria-label="Couche météo modèle">
          <option value="precipitation">Précipitation</option>
          <option value="wind_speed_10m">Vent 10 m</option>
          <option value="wind_gusts_10m">Rafales</option>
          <option value="temperature_2m">Température 2 m</option>
          <option value="dew_point_2m">Point de rosée</option>
          <option value="pressure_msl">Pression MSL</option>
          <option value="cape">CAPE</option>
          <option value="convective_inhibition">CIN</option>
          <option value="tcwv">PWAT</option>
          <option value="temperature_850hPa">Température 850 hPa</option>
          <option value="temperature_700hPa">Température 700 hPa</option>
          <option value="temperature_500hPa">Température 500 hPa</option>
          <option value="shear_0_6km">Cisaillement 0–6 km</option>
        </select>
        <span class="map-status" id="modelStatus">Modèle NWP · masqué</span>
        <span class="map-status" id="mapStatus">Leaflet · initialisation</span>
      </div>
      <div class="legend"><span><i style="background:var(--calm)"></i>stable</span><span><i style="background:var(--watch)"></i>tension</span><span><i style="background:var(--alert)"></i>bascule / score fort</span></div>
      <p class="map-note">Fond cartographique réel OpenStreetMap/CARTO, couche radar RainViewer chargée en direct, cadrage Belgique fixe, stations belges cliquables et couche modèle NWP reliée aux sélecteurs. ECMWF/ICON/AROME sont interrogés comme prévisions opérationnelles réelles via Open‑Meteo ; si un champ n'est pas disponible, MeteoVoid l'indique au lieu de l'inventer. La couche modèle est une grille de points réelle, pas une nappe raster propriétaire type Windy.</p>
    </div>
  </section>

  <!-- ===== EXPERT ===== -->
  <section class="view" data-view="expert">
    <div class="subnav" id="subnav">
      <button data-sv="stations" aria-pressed="true">Stations & zones</button>
      <button data-sv="obs">Observation émergente</button>
      <button data-sv="valid">Validation</button>
      <button data-sv="sources">Sources</button>
      <button data-sv="convective">Champs réels</button>
      <button data-sv="graphes">Cartes & graphes</button>
      <button data-sv="api">Exports & API</button>
    </div>

    <div class="subview on" data-sv="stations">
      <div class="card">
        <div class="eyebrow"><span class="d"></span>Stations les plus sensibles</div>
        <table style="margin-top:10px"><thead><tr><th>Station</th><th>Sévérité</th><th style="text-align:right">Score</th><th>Heure sensible</th><th>Signaux</th></tr></thead><tbody id="stationsTbl"></tbody></table>
      </div>
      <div class="card">
        <div class="eyebrow"><span class="d"></span>Synthèse par province</div>
        <table style="margin-top:10px"><thead><tr><th>Province</th><th>Sévérité</th><th style="text-align:right">Score max</th><th>Station pilote</th></tr></thead><tbody id="provTbl"></tbody></table>
      </div>
    </div>

    <div class="subview" data-sv="obs">
      <div class="card"><div class="eyebrow"><span class="d"></span>Observation émergente</div>
        <p style="color:var(--ink-dim);margin-top:12px">Potentiel modèle confronté aux observations réelles. Tant qu'aucune confirmation n'est renseignée, MeteoVoid garde le signal en lecture interne et ne le promeut pas en alerte.</p>
        <dl class="kv" style="margin-top:14px"><dt>Radar (machine)</dt><dd>none</dd><dt>Foudre</dt><dd>none</dd><dt>MeteoAlarm</dt><dd>—</dd><dt>ESTOFEX</dt><dd>—</dd><dt>État</dt><dd>no_machine_radar_data</dd></dl>
      </div>
    </div>
    <div class="subview" data-sv="valid">
      <div class="card"><div class="eyebrow"><span class="d"></span>Validation historique</div>
        <p style="color:var(--ink-dim);margin-top:12px">Replay sur <span class="mono">belgium_verified_storm_events.csv</span> : vrais/faux positifs, faux négatifs, délais de détection.</p>
        <div class="row c4" style="margin-top:14px">
          <div class="kpi"><div class="name">Vrais positifs</div><div class="val mono">—</div></div>
          <div class="kpi"><div class="name">Faux positifs</div><div class="val mono">—</div></div>
          <div class="kpi"><div class="name">Faux négatifs</div><div class="val mono">—</div></div>
          <div class="kpi"><div class="name">Délai médian</div><div class="val mono">—</div></div>
        </div>
        <p style="font-size:.76rem;color:var(--ink-faint);margin-top:12px">Métriques alimentées par <span class="mono">tools/belgium_validation_metrics.py</span>.</p>
      </div>
    </div>
    <div class="subview" data-sv="sources">
      <div class="card"><div class="eyebrow"><span class="d"></span>Sources & couches</div>
        <dl class="kv" style="margin-top:14px">
          <dt>Signal interne</dt><dd>stations + variables disponibles</dd>
          <dt>Heat stress</dt><dd>heat_stress_score</dd>
          <dt>Risque convectif</dt><dd>convective_risk_score</dd>
          <dt>Champs réels suivis</dt><dd>point de rosée · CAPE · CIN · cisaillement 0–6 km · convergence au sol · pression · rafales · PWAT · températures 850/700/500 hPa</dd>
          <dt>Règle anti-simulation</dt><dd>si un champ réel est absent, MeteoVoid écrit “manquant” au lieu d’inventer une valeur</dd>
          <dt>Radar visuel</dt><dd>RainViewer</dd>
          <dt>Radar machine</dt><dd>OPERA ORD / MeteoGate</dd>
          <dt>Nowcast</dt><dd>wradlib · pySTEPS (si données)</dd>
        </dl>
      </div>
    </div>
    <div class="subview" data-sv="convective">
      <div class="card"><div class="eyebrow"><span class="d"></span>Ingrédients convectifs réels · sans simulation</div>
        <p style="color:var(--ink-dim);margin-top:12px">Les valeurs sont publiées uniquement si elles existent dans le dernier run réel ou dans un fournisseur configuré. Radar, foudre et satellite restent marqués manquants tant qu’aucune source exploitable n’est connectée.</p>
        <div id="liveConvectiveInputs" style="margin-top:14px"></div>
        <div class="note">Contrat : <span class="mono">meteovoid_real_convective_inputs_v1</span> · API : <span class="mono">api/convective_live.json</span></div>
      </div>
    </div>
    <div class="subview" data-sv="graphes">
      <div class="card"><div class="eyebrow"><span class="d"></span>Cartes & graphes</div>
        <p style="color:var(--ink-dim);margin-top:12px">Figures générées au build (graphe d'information, graphe amont, couches de score). Aperçus liés depuis le pipeline.</p>
        <div id="expertFrameLinks" class="row c3" style="margin-top:14px"></div>
        <div class="row c3" style="margin-top:14px">
          <div class="kpi"><div class="name">Graphe d'information</div><div class="foot mono">belgium_information_graph</div></div>
          <div class="kpi"><div class="name">Graphe amont</div><div class="foot mono">belgium_upstream_graph</div></div>
          <div class="kpi"><div class="name">Couches de score</div><div class="foot mono">belgium_score_layers</div></div>
        </div>
      </div>
    </div>
    <div class="subview" data-sv="api">
      <div class="card"><div class="eyebrow"><span class="d"></span>Exports & API</div>
        <p style="color:var(--ink-dim);margin-top:12px">Contrat public canonique <span class="mono">belgium_public_latest_v1</span>.</p>
        <div id="expertExportLinks"></div>
        <dl class="kv" style="margin-top:14px">
          <dt>Canonique</dt><dd>belgium_public_latest.json</dd>
          <dt>Alias compat.</dt><dd>meteovoid_api_latest.json</dd>
          <dt>Chaleur</dt><dd>api/heat.json</dd>
          <dt>Alertes</dt><dd>CAP (belgium_cap_export)</dd>
        </dl>
      </div>
    </div>
  </section>

  <!-- ===== MÉTHODOLOGIE ===== -->
  <section class="view" data-view="methodo">
    <div class="card">
      <div class="eyebrow"><span class="d"></span>Méthodologie</div>
      <h2 style="font-family:var(--disp);font-weight:600;font-size:1.4rem;margin:12px 0 6px">Veille, pas avertissement</h2>
      <p style="color:var(--ink-dim);max-width:64ch">Prototype technique expérimental. Il ne remplace pas l'IRM/KMI, MeteoAlarm, les autorités, le radar ou le nowcast foudre.</p>
      <div class="row c3" style="margin-top:18px">
        <div class="kpi"><div class="name">1 · Signal interne</div><div class="foot">score calculé depuis les stations et variables disponibles</div></div>
        <div class="kpi"><div class="name">2 · Confirmation externe</div><div class="foot">radar, foudre, MeteoAlarm, ESTOFEX si renseignés</div></div>
        <div class="kpi"><div class="name">3 · Niveau opérationnel</div><div class="foot">formulation prudente sur la convergence des deux</div></div>
      </div>
      <h2 style="font-family:var(--disp);font-weight:600;font-size:1.15rem;margin:22px 0 6px">Chaleur et risque convectif, séparés</h2>
      <p style="color:var(--ink-dim);max-width:64ch">Deux couches indépendantes — <span class="mono">heat_stress_score</span> et <span class="mono">convective_risk_score</span> — pour ne pas transformer une atmosphère chaude et humide en alerte orageuse.</p>
      <p style="margin-top:18px"><a href="methodology.html" style="color:var(--accent);border-color:var(--accent);text-decoration:none;border-bottom:1px solid">Méthodologie complète →</a></p>
    </div>
  </section>
</main>

<footer class="wrap">
  MeteoVoid Belgique · run <span class="ftag" id="footerRun">run actuel</span> · mode <span class="ftag" id="footerMode">live static</span> ·
  <a href="europe.html">Europe</a> ·
  <a href="methodology.html">Méthodologie</a> · ori-c.be
  <div style="margin-top:8px">Prototype technique non officiel. Toujours comparer avec les sources officielles, le radar et la foudre.</div>
</footer>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
"use strict";
const FALLBACK=__BOOTSTRAP__;
const PROVINCES_GEOJSON=__BELGIUM_PROVINCES_GEOJSON__;
function escTxt(v){return String(v??"").replace(/[&<>"']/g,c=>c==="&"?"&amp;":c==="<"?"&lt;":c===">"?"&gt;":c==='"'?"&quot;":"&#39;");}
const numVal=(v,d=0)=>{const n=Number(v);return Number.isFinite(n)?n:d};
const pctVal=v=>Math.round(numVal(v,0)*100);
const clamp01=v=>Math.max(0,Math.min(1,numVal(v,0)));
let RUN="2026-06-30T16:00:00+02:00";
const reduced=matchMedia("(prefers-reduced-motion:reduce)").matches;
const $=s=>document.querySelector(s);
const ns="http://www.w3.org/2000/svg";
const el=(n,a)=>{const e=document.createElementNS(ns,n);for(const k in a)e.setAttribute(k,a[k]);return e;};
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));

/* ---- valeurs de secours issues du dernier build, remplacées par le run réel injecté ---- */
const BASE={
  composantes:[
    {n:"Charge convective",v:0.50,d:"énergie qui s'accumule (chaleur + humidité)",chips:["36 °C max","21 °C point de rosée"],ic:"flame"},
    {n:"Déclencheur",v:0.20,d:"peu de forçage pour déclencher",chips:["20 % pluie","2.0 hPa/6h"],ic:"bolt"},
    {n:"Organisation",v:0.20,d:"structures peu organisées",chips:["7 m/s rafales"],ic:"layers"},
    {n:"Couvercle (inhibition)",v:0.30,d:"couvercle stable, inhibition probable",chips:["2.0 hPa/6h"],ic:"lid"},
    {n:"Observation émergente",v:0.10,d:"potentiel sans observation : rien de confirmé pour l'instant",chips:["radar : none","foudre : none"],ic:"eye"},
    {n:"Propagation amont",v:0.20,d:"pas de corridor amont net",chips:[],ic:"arrow"},
    {n:"Void Collapse Signal",v:0.28,d:"le potentiel latent reste loin d'une actualisation",chips:["niveau : stable"],ic:"target"}
  ],
  timeline:{hours:[6,7,8,9,10,11,12,13,14,15,16,17,18],score:[0.30,0.33,0.36,0.40,0.45,0.50,0.55,0.60,0.66,0.69,0.70,0.66,0.58],
    sensFrom:13,sensTo:18,seuil:0.60,pic:{h:16,v:0.70},
    events:[[6,"potentiel latent qui se charge","var(--watch)"],[10,"la charge convective augmente, fenêtre sensible ouverte","var(--latent)"],[16,"pic de risque modèle (score 0.70)","var(--alert)"],[18,"maintien puis dissipation attendue","var(--calm)"]]},
  heat:{niveau:4,courbe:{h:[6,8,10,12,14,15,16,18,20],t:[24,28,31,34,35.5,36,35.5,33,31],hx:[31,36,40,43,44.5,45,44,40,37],pic:15},
    lieux:[["Kleine-Brogel","Est","extreme",36.4,43,18.8],["Uccle","Centre","extreme",35.8,43,19.5],["Liège","Est","extreme",35.1,42,19.2],["Virton","Sud","forte+",34.6,41,18.0],["Gand","Nord","forte+",33.9,42,20.1],["Ostende","Littoral","forte",29.7,38,21.0]],
    conseils:["s'hydrater régulièrement, sans attendre la sensation de soif","rester au frais et éviter toute exposition prolongée au soleil","ne jamais laisser un enfant ou un animal dans un véhicule","contacter et accompagner les personnes vulnérables de l'entourage","consulter sans tarder en cas de malaise, crampes ou désorientation"],
    note:"La chaleur (lourdeur thermique) est mesurée séparément du risque convectif. Une atmosphère chaude et humide n'implique pas un orage imminent ; les deux couches sont suivies indépendamment.",
    regions:[]},
  stations:[["Kleine-Brogel","belgium_east",0.75],["Uccle","belgium_center",0.73],["Liège","belgium_east",0.70],["Virton","belgium_south",0.68],["Gand","belgium_north",0.67],["Ostende","belgium_coast",0.58]],
  provinces:[["Limbourg",0.64,"Kleine-Brogel"]]
};
const COMFORT=[{c:"var(--t1)",name:"Aucun inconfort",band:"< 20"},{c:"var(--t2)",name:"Confortable",band:"20 – 29"},{c:"var(--t3)",name:"Inconfort léger",band:"30 – 39"},{c:"var(--t4)",name:"Inconfort marqué · prudence",band:"40 – 45"},{c:"var(--t5)",name:"Danger",band:"46 – 53"},{c:"var(--t6)",name:"Danger extrême",band:"≥ 54"}];
const STATIONS_GEO=[["Ostende",51.23,2.92],["Anvers",51.22,4.40],["Gand",51.05,3.72],["Hasselt",50.93,5.34],["Kleine-Brogel",51.17,5.47],["Uccle",50.80,4.36],["Liège",50.63,5.57],["Charleroi",50.41,4.44],["Namur",50.47,4.87],["Virton",49.57,5.53]];

/* ---- états visuels dérivés du run réel côté interface ---- */
const SCN={
  stable:{accent:"var(--calm)",soft:"rgba(70,197,176,.13)",mot:"Veille",ope:"Stable",zone:"Stable",indice:0.28,score:0.62,conf:63,
    opeDesc:"Atmosphère chaude et sèche, risque convectif limité.",
    etatDesc:"Veille non officielle · zone la plus exposée : Limbourg · fenêtre sensible 13h → 18h · score modèle 0.62 · pas encore de confirmation radar/foudre.",
    ews:{v:0.31,vs:[0.12,0.14,0.13,0.18,0.22,0.27,0.31],ac:0.68,acs:[0.41,0.44,0.50,0.55,0.60,0.64,0.68],fl:3,flA:true},
    bars:[["Qualité des sources",100],["Cohérence interne",92],["Confirmation externe",0],["Cohérence spatiale",30]],
    mapZone:"calm"},
  tension:{accent:"var(--watch)",soft:"rgba(232,179,57,.14)",mot:"Tension",ope:"Latent",zone:"Latent",indice:0.55,score:0.71,conf:74,
    opeDesc:"Charge convective en hausse, premiers signes d'organisation. Fenêtre sensible élargie.",
    etatDesc:"Veille renforcée · le signal de bascule progresse · fenêtre sensible 12h → 19h · confirmation externe encore partielle.",
    ews:{v:0.46,vs:[0.18,0.22,0.25,0.30,0.37,0.42,0.46],ac:0.80,acs:[0.55,0.60,0.66,0.71,0.75,0.78,0.80],fl:5,flA:true},
    bars:[["Qualité des sources",100],["Cohérence interne",88],["Confirmation externe",35],["Cohérence spatiale",58]],
    mapZone:"watch"},
  bascule:{accent:"var(--alert)",soft:"rgba(240,86,108,.15)",mot:"Bascule probable",ope:"Transition",zone:"Transition → Bascule",indice:0.82,score:0.86,conf:81,
    opeDesc:"Signature de transition nette : autocorrélation proche de 1, flickering intense. Fenêtre de bascule ouverte.",
    etatDesc:"Bascule probable · le signal est haut et accélère · confirmation radar/foudre en cours · suivre les sources officielles.",
    ews:{v:0.71,vs:[0.40,0.47,0.54,0.60,0.65,0.69,0.71],ac:0.93,acs:[0.74,0.80,0.85,0.88,0.91,0.92,0.93],fl:8,flA:true},
    bars:[["Qualité des sources",100],["Cohérence interne",84],["Confirmation externe",72],["Cohérence spatiale",80]],
    mapZone:"alert"}
};
let S=SCN.stable;
const ZCOL={calm:"var(--calm)",watch:"var(--watch)",alert:"var(--alert)"};
const ICONS={
  flame:'<path d="M8 1c1 3-1 4-1 6a5 5 0 0 0 5 5 5 5 0 0 0 4-7c-1 1-2 1-2 0 0-2-2-3-2-5-2 1-1 4-3 4-1 0-1-2 2-4z" fill="currentColor"/>',
  bolt:'<path d="M9 1 3 9h4l-1 6 7-9H9l1-5z" fill="currentColor"/>',
  layers:'<path d="M8 2 1 6l7 4 7-4-7-4zM1 10l7 4 7-4" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/>',
  lid:'<path d="M2 5h12M2 9h12M4 12h8" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>',
  eye:'<path d="M1 8s3-5 7-5 7 5 7 5-3 5-7 5-7-5-7-5z" fill="none" stroke="currentColor" stroke-width="1.3"/><circle cx="8" cy="8" r="2" fill="currentColor"/>',
  arrow:'<path d="M2 8h11M9 4l4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>',
  target:'<circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" stroke-width="1.3"/><circle cx="8" cy="8" r="2.4" fill="currentColor"/>'
};
const colFor=c=>getComputedStyle(document.documentElement).getPropertyValue(c)||c;

/* ===== helpers géométrie ===== */
function pol(cx,cy,r,deg){const a=deg*Math.PI/180;return [cx+r*Math.cos(a),cy+r*Math.sin(a)];}
function arcDeg(cx,cy,r,d0,d1,col,w,cap){
  const [x0,y0]=pol(cx,cy,r,d0),[x1,y1]=pol(cx,cy,r,d1);
  const large=(d1-d0)>180?1:0;
  return el("path",{d:`M${x0.toFixed(2)} ${y0.toFixed(2)} A${r} ${r} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`,fill:"none",stroke:col,"stroke-width":w,"stroke-linecap":cap||"round"});
}
/* jauge circulaire 270° (gap en bas) */
function ringGauge(sel,frac,big,sub,col){
  const svg=$(sel);svg.innerHTML="";const cx=100,cy=100,r=78,A0=135,SW=270;
  svg.appendChild(arcDeg(cx,cy,r,A0,A0+SW,"var(--line)",11));
  svg.appendChild(arcDeg(cx,cy,r,A0,A0+SW*clamp(frac,0,1),col,11));
  const big_=el("text",{x:cx,y:cy-2,"text-anchor":"middle",fill:"var(--ink)","font-family":"var(--disp)","font-size":"40","font-weight":"500"});big_.textContent=big;svg.appendChild(big_);
  const sub_=el("text",{x:cx,y:cy+22,"text-anchor":"middle",fill:"var(--ink-dim)","font-family":"var(--mono)","font-size":"10.5","letter-spacing":"1"});sub_.textContent=sub;svg.appendChild(sub_);
}
/* jauge humidex demi-cercle (corrigée) */
function heatGauge(){
  const svg=$("#heatGauge");if(!svg)return;svg.innerHTML="";
  const cx=130,cy=132,r=104,max=54,HX=45;
  const ang=v=>180+(clamp(v,0,max)/max)*180;
  svg.appendChild(arcDeg(cx,cy,r,180,360,"var(--line)",12));
  [[0,20,"var(--t1)"],[20,30,"var(--t2)"],[30,40,"var(--t3)"],[40,46,"var(--t4)"],[46,54,"var(--t5)"]].forEach(([f,t,c])=>svg.appendChild(arcDeg(cx,cy,r,ang(f),ang(t),c,10)));
  // marqueur sur l'arc
  const [mx,my]=pol(cx,cy,r,ang(HX));
  const [ix,iy]=pol(cx,cy,r-16,ang(HX));
  svg.appendChild(el("line",{x1:ix,y1:iy,x2:mx,y2:my,stroke:"var(--ink)","stroke-width":"2.5","stroke-linecap":"round"}));
  svg.appendChild(el("circle",{cx:mx,cy:my,r:7,fill:"var(--ink)",stroke:"var(--void-900)","stroke-width":"2.5"}));
  const v=el("text",{x:cx,y:cy-30,"text-anchor":"middle",fill:"var(--ink)","font-family":"var(--disp)","font-size":"40","font-weight":"500"});v.textContent=HX;svg.appendChild(v);
  const u=el("text",{x:cx,y:cy-10,"text-anchor":"middle",fill:"var(--ink-dim)","font-family":"var(--mono)","font-size":"11"});u.textContent="humidex °C";svg.appendChild(u);
  const t=el("text",{x:cx,y:cy+6,"text-anchor":"middle",fill:"var(--t4)","font-family":"var(--mono)","font-size":"10","letter-spacing":"1"});t.textContent="inconfort marqué";svg.appendChild(t);
}
/* soleil */
function sun(){const svg=$("#sunIc");if(!svg)return;svg.innerHTML="";const c="var(--t5)";
  svg.appendChild(el("circle",{cx:20,cy:20,r:8,fill:"none",stroke:c,"stroke-width":"2"}));
  for(let i=0;i<8;i++){const a=i*45*Math.PI/180;const [x1,y1]=[20+12*Math.cos(a),20+12*Math.sin(a)],[x2,y2]=[20+16*Math.cos(a),20+16*Math.sin(a)];svg.appendChild(el("line",{x1,y1,x2,y2,stroke:c,"stroke-width":"2","stroke-linecap":"round"}));}
}

/* ===== piste de transition (4 zones) ===== */
let wob=null;
function drawTrack(sel,valSel){
  const svg=$(sel);svg.innerHTML="";const W=700,H=110,x0=30,x1=670,railY=70,seuil=0.72;
  const defs=el("defs");const g=el("linearGradient",{id:"bg"+sel.slice(1),x1:"0",x2:"1"});
  [["0%","var(--calm)"],["38%","var(--watch)"],["68%","var(--latent)"],["100%","var(--alert)"]].forEach(([o,c])=>g.appendChild(el("stop",{offset:o,"stop-color":c,"stop-opacity":".30"})));
  defs.appendChild(g);svg.appendChild(defs);
  svg.appendChild(el("rect",{x:x0,y:railY-7,width:x1-x0,height:14,rx:7,fill:`url(#bg${sel.slice(1)})`,stroke:"var(--line)"}));
  // labels 4 zones
  [["Stable",0.0,"start"],["Latent",0.42,"middle"],["Transition",0.68,"middle"],["Bascule",1.0,"end"]].forEach(([t,p,anc])=>{
    const tx=el("text",{x:x0+p*(x1-x0),y:railY+28,"text-anchor":anc,fill:"var(--ink-dim)","font-family":"var(--mono)","font-size":"11.5"});tx.textContent=t;svg.appendChild(tx);});
  // seuil
  const sx=x0+seuil*(x1-x0);
  svg.appendChild(el("line",{x1:sx,y1:railY-18,x2:sx,y2:railY+12,stroke:"var(--ink-faint)","stroke-width":"1.4","stroke-dasharray":"4 4"}));
  const sl=el("text",{x:sx,y:railY-24,"text-anchor":"middle",fill:"var(--ink-faint)","font-family":"var(--mono)","font-size":"10","letter-spacing":"1.5"});sl.textContent="SEUIL DE BASCULE";svg.appendChild(sl);
  // aiguille
  const px=x0+S.indice*(x1-x0);
  const halo=el("circle",{cx:px,cy:railY,r:13,fill:"var(--accent)",opacity:".18"});
  const needle=el("line",{x1:px,y1:railY-16,x2:px,y2:railY+16,stroke:"var(--accent)","stroke-width":"2.5","stroke-linecap":"round"});
  const knob=el("circle",{cx:px,cy:railY,r:6,fill:"var(--accent)",stroke:"var(--void-900)","stroke-width":"2"});
  svg.appendChild(halo);svg.appendChild(needle);svg.appendChild(knob);
  if($(valSel))$(valSel).textContent=S.indice.toFixed(2)+" · "+S.zone;
  if(!reduced&&sel==="#track1"){
    if(wob)cancelAnimationFrame(wob);const amp=3+S.ews.v*14,t0=performance.now();
    (function w(t){const dx=Math.sin((t-t0)/520)*amp*.5+Math.sin((t-t0)/210)*amp*.5;const nx=px+dx;needle.setAttribute("x1",nx);needle.setAttribute("x2",nx);knob.setAttribute("cx",nx);halo.setAttribute("cx",nx);wob=requestAnimationFrame(w);})(performance.now());
  }
}

/* ===== sparkline ===== */
function spark(sel,serie,col){
  const svg=$(sel);if(!svg)svg;svg.innerHTML="";const w=118,h=28,p=3,mn=Math.min(...serie),mx=Math.max(...serie),rg=(mx-mn)||1;
  const d=serie.map((v,i)=>(i?"L":"M")+(i/(serie.length-1)*w).toFixed(1)+" "+(h-p-((v-mn)/rg)*(h-2*p)).toFixed(1)).join(" ");
  svg.appendChild(el("path",{d:d+` L${w} ${h} L0 ${h} Z`,fill:col,opacity:".12"}));
  svg.appendChild(el("path",{d,fill:"none",stroke:col,"stroke-width":"1.8","stroke-linejoin":"round"}));
  const last=serie[serie.length-1];svg.appendChild(el("circle",{cx:w,cy:h-p-((last-mn)/rg)*(h-2*p),r:2.6,fill:col}));
}

/* ===== timeline horaire ===== */
function drawTimeline(){
  const svg=$("#timeline");svg.innerHTML="";const W=700,H=230,L=44,R=24,T=18,B=42;
  const tl=BASE.timeline,hrs=tl.hours,xs=h=>L+((h-hrs[0])/(hrs[hrs.length-1]-hrs[0]))*(W-L-R),ys=v=>T+(1-v)*(H-T-B);
  // fenêtre sensible
  svg.appendChild(el("rect",{x:xs(tl.sensFrom),y:T,width:xs(tl.sensTo)-xs(tl.sensFrom),height:H-T-B,fill:"var(--accent)",opacity:".06"}));
  // grille y
  [0,0.5,1].forEach(v=>{svg.appendChild(el("line",{x1:L,y1:ys(v),x2:W-R,y2:ys(v),stroke:"var(--line-soft)"}));});
  // seuil
  svg.appendChild(el("line",{x1:L,y1:ys(tl.seuil),x2:W-R,y2:ys(tl.seuil),stroke:"var(--alert)","stroke-width":"1","stroke-dasharray":"5 4",opacity:".6"}));
  const slbl=el("text",{x:W-R,y:ys(tl.seuil)-5,"text-anchor":"end",fill:"var(--alert)","font-family":"var(--mono)","font-size":"10",opacity:".8"});slbl.textContent="seuil élevé";svg.appendChild(slbl);
  // x ticks
  [6,9,12,15,18].forEach(h=>{const t=el("text",{x:xs(h),y:H-B+18,"text-anchor":"middle",fill:"var(--ink-faint)","font-family":"var(--mono)","font-size":"10.5"});t.textContent=h+"h";svg.appendChild(t);});
  // courbe
  const dPath=tl.score.map((v,i)=>(i?"L":"M")+xs(hrs[i]).toFixed(1)+" "+ys(v).toFixed(1)).join(" ");
  svg.appendChild(el("path",{d:dPath+` L${xs(hrs[hrs.length-1])} ${ys(0)} L${xs(hrs[0])} ${ys(0)} Z`,fill:"var(--accent)",opacity:".08"}));
  const line=el("path",{d:dPath,fill:"none",stroke:"var(--accent)","stroke-width":"2.4","stroke-linejoin":"round","stroke-linecap":"round"});svg.appendChild(line);
  // events markers
  tl.events.forEach(([h,,c])=>{const i=hrs.indexOf(h);if(i<0)return;svg.appendChild(el("circle",{cx:xs(h),cy:ys(tl.score[i]),r:4,fill:c,stroke:"var(--void-900)","stroke-width":"1.5"}));});
  // pic
  svg.appendChild(el("circle",{cx:xs(tl.pic.h),cy:ys(tl.pic.v),r:5.5,fill:"none",stroke:"var(--alert)","stroke-width":"2"}));
  const pl=el("text",{x:xs(tl.pic.h),y:ys(tl.pic.v)-12,"text-anchor":"middle",fill:"var(--alert)","font-family":"var(--mono)","font-size":"10"});pl.textContent="pic";svg.appendChild(pl);
  if(!reduced){const len=line.getTotalLength();line.style.strokeDasharray=len;line.style.strokeDashoffset=len;line.animate([{strokeDashoffset:len},{strokeDashoffset:0}],{duration:1100,easing:"ease-out",fill:"forwards"});}
  // events list
  $("#tlEvents").innerHTML=tl.events.map(([h,x,c])=>`<li><span class="dot" style="background:${c}"></span><span class="h">${h}h</span><span class="x">${x}</span></li>`).join("");
}

/* ===== courbe chaleur ===== */
function drawHeatCurve(){
  const svg=$("#heatCurve");svg.innerHTML="";const W=700,H=230,L=44,R=24,T=18,B=42;
  const c=BASE.heat.courbe,hrs=c.h;const allv=c.t.concat(c.hx);const mn=Math.min(...allv)-2,mx=Math.max(...allv)+2;
  const xs=h=>L+((h-hrs[0])/(hrs[hrs.length-1]-hrs[0]))*(W-L-R),ys=v=>T+(1-(v-mn)/(mx-mn))*(H-T-B);
  [mn,(mn+mx)/2,mx].forEach(v=>{svg.appendChild(el("line",{x1:L,y1:ys(v),x2:W-R,y2:ys(v),stroke:"var(--line-soft)"}));const t=el("text",{x:L-8,y:ys(v)+3,"text-anchor":"end",fill:"var(--ink-faint)","font-family":"var(--mono)","font-size":"10"});t.textContent=Math.round(v)+"°";svg.appendChild(t);});
  hrs.forEach(h=>{const t=el("text",{x:xs(h),y:H-B+18,"text-anchor":"middle",fill:"var(--ink-faint)","font-family":"var(--mono)","font-size":"10"});t.textContent=h+"h";svg.appendChild(t);});
  // pic
  svg.appendChild(el("line",{x1:xs(c.pic),y1:T,x2:xs(c.pic),y2:H-B,stroke:"var(--ink-faint)","stroke-dasharray":"4 4"}));
  const pl=el("text",{x:xs(c.pic),y:T+ -2,"text-anchor":"middle",fill:"var(--ink-faint)","font-family":"var(--mono)","font-size":"10"});pl.textContent=c.pic+"h";svg.appendChild(pl);
  const dHx=c.hx.map((v,i)=>(i?"L":"M")+xs(hrs[i]).toFixed(1)+" "+ys(v).toFixed(1)).join(" ");
  svg.appendChild(el("path",{d:dHx,fill:"none",stroke:"var(--t5)","stroke-width":"2","stroke-dasharray":"5 4","stroke-linejoin":"round"}));
  const dT=c.t.map((v,i)=>(i?"L":"M")+xs(hrs[i]).toFixed(1)+" "+ys(v).toFixed(1)).join(" ");
  svg.appendChild(el("path",{d:dT+` L${xs(hrs[hrs.length-1])} ${ys(mn)} L${xs(hrs[0])} ${ys(mn)} Z`,fill:"var(--t4)",opacity:".08"}));
  svg.appendChild(el("path",{d:dT,fill:"none",stroke:"var(--t4)","stroke-width":"2.4","stroke-linejoin":"round","stroke-linecap":"round"}));
  c.t.forEach((v,i)=>svg.appendChild(el("circle",{cx:xs(hrs[i]),cy:ys(v),r:2.8,fill:"var(--t4)"})));
}

/* ===== carte radar Leaflet ===== */
let MV_MAP=null;
let MV_STATION_LAYER=null;
let MV_RAIN_LAYER=null;
let MV_PROVINCE_LAYER=null;
let MV_RAIN_VISIBLE=true;
let MV_RAIN_REFRESH=null;
let MV_MODEL_LAYER=null;
let MV_MODEL_VISIBLE=false;
let MV_MODEL_BUSY=false;

const NWP_MODELS={
  best:{label:"Best match",endpoint:"https://api.open-meteo.com/v1/forecast"},
  ecmwf:{label:"ECMWF IFS",endpoint:"https://api.open-meteo.com/v1/ecmwf"},
  icon:{label:"DWD ICON",endpoint:"https://api.open-meteo.com/v1/dwd-icon"},
  arome:{label:"Météo-France AROME/ARPEGE",endpoint:"https://api.open-meteo.com/v1/meteofrance"}
};
const NWP_LAYERS={
  precipitation:{label:"Précipitation",unit:"mm",fields:["precipitation"],range:[0,12]},
  wind_speed_10m:{label:"Vent 10 m",unit:"km/h",fields:["wind_speed_10m"],range:[0,90]},
  wind_gusts_10m:{label:"Rafales",unit:"km/h",fields:["wind_gusts_10m"],range:[0,120]},
  temperature_2m:{label:"Température 2 m",unit:"°C",fields:["temperature_2m"],range:[-5,42]},
  dew_point_2m:{label:"Point de rosée",unit:"°C",fields:["dew_point_2m"],range:[0,26]},
  pressure_msl:{label:"Pression MSL",unit:"hPa",fields:["pressure_msl"],range:[990,1030]},
  cape:{label:"CAPE",unit:"J/kg",fields:["cape"],range:[0,4000]},
  convective_inhibition:{label:"CIN",unit:"J/kg",fields:["convective_inhibition"],range:[-250,0]},
  tcwv:{label:"PWAT",unit:"mm",fields:["total_column_integrated_water_vapour"],range:[10,55],alias:"total_column_integrated_water_vapour"},
  temperature_850hPa:{label:"Température 850 hPa",unit:"°C",fields:["temperature_850hPa"],range:[-10,28]},
  temperature_700hPa:{label:"Température 700 hPa",unit:"°C",fields:["temperature_700hPa"],range:[-20,18]},
  temperature_500hPa:{label:"Température 500 hPa",unit:"°C",fields:["temperature_500hPa"],range:[-35,0]},
  shear_0_6km:{label:"Cisaillement 0–6 km",unit:"m/s",fields:["wind_speed_10m","wind_direction_10m","wind_speed_500hPa","wind_direction_500hPa"],range:[0,35],derived:true}
};
const BELGIUM_VIEW_BOUNDS=[[49.45,2.45],[51.55,6.45]];
const BELGIUM_MODEL_GRID=[
  ["Côte · Coxyde",51.10,2.65],["Côte · Ostende",51.22,2.93],["Bruges",51.21,3.22],["Courtrai",50.83,3.26],
  ["Tournai",50.61,3.39],["Gand",51.05,3.72],["Mons",50.45,3.95],["Charleroi",50.41,4.44],
  ["Bruxelles / Uccle",50.80,4.36],["Malines",51.03,4.48],["Anvers",51.22,4.40],["Turnhout",51.32,4.94],
  ["Louvain",50.88,4.70],["Jodoigne",50.72,4.87],["Namur",50.47,4.87],["Dinant",50.26,4.91],
  ["Hasselt",50.93,5.33],["Genk",50.97,5.50],["Liège",50.63,5.58],["Eupen",50.63,6.03],
  ["Marche",50.23,5.34],["Bastogne",50.00,5.72],["Arlon",49.68,5.82],["Virton",49.57,5.53],
  ["Grille W 1",50.95,3.15],["Grille W 2",50.70,3.70],["Grille Centre",50.70,4.40],["Grille E 1",50.70,5.20],
  ["Grille NE",51.10,5.20],["Grille S",50.10,4.70],["Grille SE",50.10,5.55],["Grille Ardenne",50.35,5.80]
];

function cssVar(name){return getComputedStyle(document.documentElement).getPropertyValue(name).trim()||name;}
function normName(v){return String(v||"").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g,"").replace(/[^a-z0-9]+/g,"");}
function stationDataFor(name){
  const key=normName(name);
  const found=(BASE.stations||[]).find(row=>normName(row[0])===key || normName(row[0]).includes(key) || key.includes(normName(row[0])));
  const score=numVal(found&&found[2],0.25);
  return {
    name:name,
    region:(found&&found[1])||"Belgique",
    score:score,
    severity:(found&&found[3])||scoreLabel(score),
    pill:(found&&found[4])||scorePill(score),
    worst:(found&&found[5])||"—",
    signals:(found&&found[6])||"signal station"
  };
}
function scorePill(score){if(score>=.70)return "actif"; if(score>=.55)return "latent"; if(score>=.35)return "veille"; return "stable";}
function scoreLabel(score){if(score>=.70)return "Critique"; if(score>=.55)return "Élevé"; if(score>=.35)return "Veille"; return "Stable";}
function mapColor(score){
  if(S&&S.mapZone==="alert")return cssVar("--alert");
  if(score>=.70)return cssVar("--alert");
  if(score>=.55)return cssVar("--latent");
  if(score>=.35)return cssVar("--watch");
  return cssVar("--calm");
}
function popupHtml(record){return `<div class="mv-popup-title">${escTxt(record.name)}</div>
  <div class="mv-popup-row"><span>Score</span><b>${record.score.toFixed(2)}</b></div>
  <div class="mv-popup-row"><span>Sévérité</span><b>${escTxt(record.severity)}</b></div>
  <div class="mv-popup-row"><span>Fenêtre</span><b>${escTxt(record.worst)}</b></div>
  <div class="mv-popup-row"><span>Signaux</span><b>${escTxt(record.signals)}</b></div>`;}
function insideBelgiumView(lat,lon){
  return Number.isFinite(lat)&&Number.isFinite(lon)&&lat>=BELGIUM_VIEW_BOUNDS[0][0]&&lat<=BELGIUM_VIEW_BOUNDS[1][0]&&lon>=BELGIUM_VIEW_BOUNDS[0][1]&&lon<=BELGIUM_VIEW_BOUNDS[1][1];
}
function stationRecords(){
  return (STATIONS_GEO||[])
    .map(([name,lat,lon])=>({ ...stationDataFor(name), lat:numVal(lat), lon:numVal(lon)}))
    .filter(x=>insideBelgiumView(x.lat,x.lon)&&!String(x.region||"").startsWith("approach_"));
}
function nwpSamplingPoints(){
  const seen=new Set();
  const base=stationRecords().map(s=>({name:s.name,lat:s.lat,lon:s.lon,type:"station"}));
  const grid=BELGIUM_MODEL_GRID.map(([name,lat,lon])=>({name,lat,lon,type:"grid"}));
  return base.concat(grid)
    .filter(p=>insideBelgiumView(Number(p.lat),Number(p.lon)))
    .filter(p=>{const k=`${Number(p.lat).toFixed(2)}-${Number(p.lon).toFixed(2)}`;if(seen.has(k))return false;seen.add(k);return true;})
    .slice(0,64);
}
function renderLocSelector(){
  const sel=document.getElementById("locsel"); if(!sel)return;
  const current=sel.value;
  sel.innerHTML='<option value="">Belgique · toutes les stations</option>'+stationRecords().map((s,i)=>`<option value="${i}">${escTxt(s.name)} · ${s.score.toFixed(2)}</option>`).join("");
  if(current)sel.value=current;
}
function renderLeafletStations(){
  if(!MV_MAP||typeof L==="undefined")return;
  renderLocSelector();
  if(!MV_STATION_LAYER)MV_STATION_LAYER=L.layerGroup().addTo(MV_MAP); else MV_STATION_LAYER.clearLayers();
  stationRecords().forEach((record,idx)=>{
    const color=mapColor(record.score);
    const cls=(record.score>=.70 || (S&&S.mapZone==="alert"))?"mv-alert":"";
    const icon=L.divIcon({className:"",html:`<span class="mv-marker ${cls}" style="color:${color}"></span>`,iconSize:[18,18],iconAnchor:[9,9],popupAnchor:[0,-9]});
    const marker=L.marker([record.lat,record.lon],{icon,title:record.name}).bindPopup(popupHtml(record));
    marker.mvIndex=idx;
    marker.addTo(MV_STATION_LAYER);
  });
}
function setMapStatus(text){const e=document.getElementById("mapStatus"); if(e)e.textContent=text;}
function rainviewerTileUrl(data,frame){
  const host=String((data&&data.host)||"https://tilecache.rainviewer.com").replace(/\/$/,"");
  const path=String((frame&&frame.path)||"");
  if(!path)throw new Error("rainviewer_no_frame_path");
  if(/^https?:\/\//i.test(path))return `${path}/256/{z}/{x}/{y}/2/1_1.png`;
  return `${host}${path.startsWith("/")?path:"/"+path}/256/{z}/{x}/{y}/2/1_1.png`;
}
function addRainViewerLayer(){
  if(!MV_MAP||typeof L==="undefined")return;
  setMapStatus("RainViewer direct · chargement");
  const radarBadge=document.getElementById("radarLiveState"); if(radarBadge)radarBadge.textContent="RainViewer direct";
  fetch("https://api.rainviewer.com/public/weather-maps.json",{cache:"no-store"})
    .then(r=>r.ok?r.json():Promise.reject(new Error("rainviewer_http")))
    .then(data=>{
      const past=(data&&data.radar&&data.radar.past)||[];
      const nowcast=(data&&data.radar&&data.radar.nowcast)||[];
      const frames=past.concat(nowcast);
      const frame=frames[frames.length-1]||past[past.length-1];
      if(!frame||!frame.path)throw new Error("rainviewer_no_frame");
      const tileUrl=rainviewerTileUrl(data,frame);
      const next=L.tileLayer(tileUrl,{opacity:.70,zIndex:220,attribution:"RainViewer",crossOrigin:true});
      if(MV_RAIN_VISIBLE)next.addTo(MV_MAP);
      const previous=MV_RAIN_LAYER;
      MV_RAIN_LAYER=next;
      if(previous)setTimeout(()=>{try{MV_MAP.removeLayer(previous);}catch(e){}},250);
      const ts=frame.time?new Date(frame.time*1000):null;
      const stamp=ts?ts.toLocaleTimeString("fr-BE",{hour:"2-digit",minute:"2-digit"}):"actif";
      setMapStatus(`RainViewer direct · ${stamp}`);
      if(radarBadge)radarBadge.textContent=`Radar direct ${stamp}`;
    })
    .catch(()=>{
      setMapStatus("RainViewer direct indisponible · fond et stations actifs");
      const radarBadge=document.getElementById("radarLiveState"); if(radarBadge)radarBadge.textContent="radar direct indisponible";
    });
}
function setModelStatus(text){const e=document.getElementById("modelStatus"); if(e)e.textContent=text;}
function nwpFieldName(layerKey){const layer=NWP_LAYERS[layerKey]||NWP_LAYERS.precipitation;return layer.alias||layerKey;}
function nwpValueAt(hourly,field,idx){
  const values=hourly&&hourly[field];
  if(!Array.isArray(values)||idx<0||idx>=values.length)return null;
  const v=Number(values[idx]);
  return Number.isFinite(v)?v:null;
}
function nwpTimeIndex(hourly){
  const times=(hourly&&hourly.time)||[];
  if(!Array.isArray(times)||!times.length)return 0;
  const now=Date.now();
  let best=0,dist=Infinity;
  times.forEach((t,i)=>{const d=Math.abs(new Date(t).getTime()-now);if(d<dist){dist=d;best=i;}});
  return best;
}
function windVector(speedKmh,dirDeg){
  const s=Number(speedKmh)/3.6,dir=Number(dirDeg)*Math.PI/180;
  if(!Number.isFinite(s)||!Number.isFinite(dir))return null;
  return {u:-s*Math.sin(dir),v:-s*Math.cos(dir)};
}
function nwpDerivedValue(hourly,layerKey,idx){
  if(layerKey!=="shear_0_6km")return nwpValueAt(hourly,nwpFieldName(layerKey),idx);
  const low=windVector(nwpValueAt(hourly,"wind_speed_10m",idx),nwpValueAt(hourly,"wind_direction_10m",idx));
  const high=windVector(nwpValueAt(hourly,"wind_speed_500hPa",idx),nwpValueAt(hourly,"wind_direction_500hPa",idx));
  if(!low||!high)return null;
  return Math.sqrt((high.u-low.u)**2+(high.v-low.v)**2);
}
function nwpColor(value,layerKey){
  const layer=NWP_LAYERS[layerKey]||NWP_LAYERS.precipitation;
  let [lo,hi]=layer.range||[0,1];
  let t=(Number(value)-lo)/((hi-lo)||1);
  if(layerKey==="convective_inhibition")t=1-t;
  t=clamp(t,0,1);
  if(t<.20)return "#5BC8E8";
  if(t<.40)return "#7FD08C";
  if(t<.60)return "#E2C84C";
  if(t<.80)return "#E8943A";
  return "#C13A8A";
}
function nwpFormatValue(value,layerKey){
  const layer=NWP_LAYERS[layerKey]||NWP_LAYERS.precipitation;
  if(value==null)return "—";
  const abs=Math.abs(Number(value));
  const decimals=abs>=100?0:(abs>=10?1:2);
  return `${Number(value).toFixed(decimals)} ${layer.unit}`;
}
function nwpBuildUrl(points,modelKey,layerKey){
  const model=NWP_MODELS[modelKey]||NWP_MODELS.best;
  const layer=NWP_LAYERS[layerKey]||NWP_LAYERS.precipitation;
  const url=new URL(model.endpoint);
  url.searchParams.set("latitude",points.map(p=>p.lat.toFixed(4)).join(","));
  url.searchParams.set("longitude",points.map(p=>p.lon.toFixed(4)).join(","));
  url.searchParams.set("hourly",Array.from(new Set(layer.fields)).join(","));
  url.searchParams.set("forecast_hours","8");
  url.searchParams.set("past_hours","1");
  url.searchParams.set("timezone","Europe/Brussels");
  url.searchParams.set("wind_speed_unit","kmh");
  url.searchParams.set("precipitation_unit","mm");
  return url.toString();
}
function clearModelLayer(){if(MV_MODEL_LAYER&&MV_MAP){MV_MAP.removeLayer(MV_MODEL_LAYER);}MV_MODEL_LAYER=null;}
function renderModelLayer(){
  if(!MV_MODEL_VISIBLE||!MV_MAP||typeof L==="undefined")return;
  if(MV_MODEL_BUSY)return;
  const sourceSel=document.getElementById("modelSource"),layerSel=document.getElementById("modelLayer");
  const modelKey=(sourceSel&&sourceSel.value)||"best",layerKey=(layerSel&&layerSel.value)||"precipitation";
  const model=NWP_MODELS[modelKey]||NWP_MODELS.best,layer=NWP_LAYERS[layerKey]||NWP_LAYERS.precipitation;
  const points=nwpSamplingPoints();
  if(!points.length){setModelStatus("Modèle NWP · aucun point");return;}
  MV_MODEL_BUSY=true;
  setModelStatus(`${model.label} · ${layer.label} · chargement`);
  fetch(nwpBuildUrl(points,modelKey,layerKey),{cache:"no-store"})
    .then(r=>r.ok?r.json():r.text().then(t=>Promise.reject(new Error(t||"nwp_http"))))
    .then(data=>{
      const rows=Array.isArray(data)?data:[data];
      const group=L.layerGroup();
      let count=0,frameText="";
      rows.forEach((row,i)=>{
        const p=points[i]||points[0];
        if(!row||!row.hourly)return;
        const idx=nwpTimeIndex(row.hourly);
        const value=nwpDerivedValue(row.hourly,layerKey,idx);
        if(value==null)return;
        const color=nwpColor(value,layerKey);
        const time=(row.hourly.time||[])[idx]||"";
        frameText=frameText||time;
        const radius=p.type==="grid"?24:18;
        const opacity=p.type==="grid"?.38:.64;
        const marker=L.circleMarker([p.lat,p.lon],{radius:radius,color:"rgba(255,255,255,.45)",weight:.8,fillColor:color,fillOpacity:opacity,pane:"overlayPane"});
        marker.bindPopup(`<div class="model-popup-title">${escTxt(p.name)}</div><div class="model-popup-row"><span>Modèle</span><b>${escTxt(model.label)}</b></div><div class="model-popup-row"><span>Couche</span><b>${escTxt(layer.label)}</b></div><div class="model-popup-row"><span>Valeur</span><b>${escTxt(nwpFormatValue(value,layerKey))}</b></div><div class="model-popup-row"><span>Échéance</span><b>${escTxt(time.replace("T"," "))}</b></div><div class="model-popup-row"><span>Source</span><b>Open-Meteo · champ modèle réel</b></div>`);
        marker.addTo(group);count++;
      });
      clearModelLayer();
      MV_MODEL_LAYER=group;
      if(MV_MODEL_VISIBLE)group.addTo(MV_MAP);
      const stamp=frameText?frameText.replace("T"," "):"échéance proche";
      setModelStatus(count?`${model.label} · ${layer.label} · ${stamp}`:`${model.label} · ${layer.label} indisponible`);
    })
    .catch(()=>{
      clearModelLayer();
      setModelStatus(`${model.label} · ${layer.label} indisponible`);
    })
    .finally(()=>{MV_MODEL_BUSY=false;});
}
function toggleModelLayer(force){
  MV_MODEL_VISIBLE=typeof force==="boolean"?force:!MV_MODEL_VISIBLE;
  const btn=document.getElementById("toggleModel");
  if(btn){
    btn.setAttribute("aria-pressed",String(MV_MODEL_VISIBLE));
    btn.textContent=MV_MODEL_VISIBLE?"Masquer modèle":"Modèle NWP";
  }
  if(!MV_MODEL_VISIBLE){clearModelLayer();setModelStatus("Modèle NWP · masqué");return;}
  renderModelLayer();
}
function modelSelectionChanged(){
  if(!MV_MODEL_VISIBLE){toggleModelLayer(true);return;}
  clearModelLayer();
  renderModelLayer();
}
function fitBelgiumMap(){
  if(!MV_MAP||typeof L==="undefined")return;
  const fixed=L.latLngBounds(BELGIUM_VIEW_BOUNDS);
  const provinceBounds=MV_PROVINCE_LAYER?MV_PROVINCE_LAYER.getBounds():null;
  const target=(provinceBounds&&provinceBounds.isValid())?provinceBounds:fixed;
  MV_MAP.fitBounds(target.pad(.06));
}
function initMap(){
  const target=document.getElementById("leafletMap"); if(!target)return;
  if(typeof L==="undefined"){setMapStatus("Leaflet indisponible · vérifier le chargement CDN");return;}
  if(MV_MAP){setTimeout(()=>MV_MAP.invalidateSize(),80);return;}
  MV_MAP=L.map(target,{zoomControl:true,scrollWheelZoom:true,preferCanvas:true}).setView([50.64,4.67],8);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",{maxZoom:19,attribution:"&copy; OpenStreetMap &copy; CARTO"}).addTo(MV_MAP);
  if(PROVINCES_GEOJSON&&PROVINCES_GEOJSON.type){
    MV_PROVINCE_LAYER=L.geoJSON(PROVINCES_GEOJSON,{style:feature=>({color:cssVar("--accent"),weight:1,opacity:.55,fillColor:cssVar("--accent"),fillOpacity:.055}),onEachFeature:(feature,layer)=>{const p=(feature&&feature.properties&&feature.properties.province)||"Province";layer.bindTooltip(p,{sticky:true});}}).addTo(MV_MAP);
  }
  renderLeafletStations();
  addRainViewerLayer();
  if(!MV_RAIN_REFRESH)MV_RAIN_REFRESH=setInterval(addRainViewerLayer,300000);
  const bounds=L.latLngBounds(stationRecords().map(s=>[s.lat,s.lon]));
  fitBelgiumMap();
  const fit=document.getElementById("fitBelgium"); if(fit)fit.onclick=()=>fitBelgiumMap();
  const toggle=document.getElementById("toggleRain"); if(toggle)toggle.onclick=()=>{MV_RAIN_VISIBLE=!MV_RAIN_VISIBLE;toggle.setAttribute("aria-pressed",String(MV_RAIN_VISIBLE));if(MV_RAIN_LAYER){MV_RAIN_VISIBLE?MV_RAIN_LAYER.addTo(MV_MAP):MV_MAP.removeLayer(MV_RAIN_LAYER);}setMapStatus(MV_RAIN_VISIBLE?"RainViewer · actif":"RainViewer · masqué");};
  const modelToggle=document.getElementById("toggleModel"); if(modelToggle)modelToggle.onclick=()=>toggleModelLayer();
  const modelSource=document.getElementById("modelSource"); if(modelSource)modelSource.onchange=()=>modelSelectionChanged();
  const modelLayer=document.getElementById("modelLayer"); if(modelLayer)modelLayer.onchange=()=>modelSelectionChanged();
  const sel=document.getElementById("locsel"); if(sel)sel.onchange=()=>{const records=stationRecords();const rec=records[Number(sel.value)];if(rec){MV_MAP.setView([rec.lat,rec.lon],10,{animate:true});setTimeout(()=>{MV_STATION_LAYER&&MV_STATION_LAYER.eachLayer(m=>{if(m.mvIndex===Number(sel.value))m.openPopup();});},220);}else fitBelgiumMap();};
  setTimeout(()=>MV_MAP.invalidateSize(),120);
}
function updateLeafletMap(){if(MV_MAP){renderLeafletStations();setTimeout(()=>MV_MAP.invalidateSize(),60);}}
function drawMap(){initMap();updateLeafletMap();}


/* ===== pills statut ===== */
function pillFor(v){
  if(v<0.30)return['stable','Stable'];
  if(v<0.45)return['veille','Veille'];
  if(v<0.65)return['latent','Instable latent'];
  return['actif','Actif'];
}
const NIV={extreme:['actif','Chaleur extrême'],'forte+':['latent','Chaleur très forte'],forte:['veille','Chaleur forte']};

/* ===== contenu statique (rendu une fois) ===== */
function renderStatic(){
  $("#runts").textContent=RUN.slice(11,16)+" "+RUN.slice(0,10);
  heatGauge();sun();drawTimeline();drawHeatCurve();drawMap();
  // 7 composantes
  $("#compGrid").innerHTML=BASE.composantes.map(c=>{const [pc,pl]=pillFor(c.v);return `
    <div class="comp"><div class="top"><span class="ic" style="color:var(--ink-dim)"><svg viewBox="0 0 16 16">${ICONS[c.ic]}</svg></span><span class="cv mono">${c.v.toFixed(2)}</span></div>
      <div class="cn">${c.n}</div>
      <div class="meter"><i style="width:${Math.round(c.v*100)}%;background:${pc==='stable'?'var(--calm)':pc==='veille'?'var(--watch)':pc==='latent'?'var(--latent)':'var(--alert)'}"></i></div>
      <span class="pill ${pc}"><span class="pd"></span>${pl}</span>
      <div class="cd" style="margin-top:9px">${c.d}</div>
      <div>${c.chips.map(x=>`<span class="chip">${x}</span>`).join("")}</div></div>`;}).join("");
  // pourquoi
  $("#whyList").innerHTML=(BASE.why||["aucun moteur n’a renvoyé de signal notable sur la grille suivie."]).map(x=>`<li>${escTxt(x)}</li>`).join("");
  // comfort
  $("#comfort").innerHTML=COMFORT.map((c,i)=>`<div class="comfort-row ${i===BASE.heat.niveau-1?'cur':''}"><span class="sw" style="background:${c.c}"></span><span>${c.name}</span><span class="band">${c.band}</span></div>`).join("");
  // lieux
  $("#lieux").innerHTML=BASE.heat.lieux.map(([n,sub,niv,t,hx,r])=>{const [pc,pl]=NIV[niv];return `<tr><td><div class="place">${n}</div><div class="sub">${sub}</div></td><td><span class="pill ${pc}"><span class="pd"></span>${pl}</span></td><td class="n">${t.toFixed(1)} °C</td><td class="n">${hx}</td><td class="n">${r.toFixed(1)} °C</td></tr>`;}).join("");
  const rw=document.getElementById("regionsWeather"); if(rw){rw.innerHTML=(BASE.heat.regions||[]).map(r=>`<tr><td><div class="place">${escTxt(r.label)}</div><div class="sub">${escTxt(r.severity)}</div></td><td>${escTxt(r.station)}</td><td class="n">${Number(r.temperature||0).toFixed(1)} °C</td><td class="n">${Number(r.humidex||0).toFixed(1)}</td><td class="n">${Number(r.precip||0).toFixed(0)} %</td></tr>`).join("");}
  $("#conseils").innerHTML=BASE.heat.conseils.map(x=>`<li>${x}</li>`).join("");
  $("#heatNote").textContent=BASE.heat.note;
  // stations & provinces
  $("#stationsTbl").innerHTML=BASE.stations.map(s=>{const n=s[0],z=s[1],sc=numVal(s[2]),lab=s[3]||"Élevé",pc=s[4]||"veille",wh=s[5]||"—",sig=s[6]||"";return `<tr><td><div class="place">${escTxt(n)}</div><div class="sub mono">${escTxt(z)}</div></td><td><span class="pill ${pc}"><span class="pd"></span>${escTxt(lab)}</span></td><td class="n">${sc.toFixed(2)}</td><td class="mono" style="font-size:.78rem">${escTxt(wh)}</td><td style="color:var(--ink-dim);font-size:.8rem">${escTxt(sig)}</td></tr>`}).join("");
  $("#provTbl").innerHTML=BASE.provinces.map(p=>{const name=p[0],sc=numVal(p[1]),st=p[2]||"",lab=p[3]||"Élevé",pc=p[4]||"veille";return `<tr><td>${escTxt(name)}</td><td><span class="pill ${pc}"><span class="pd"></span>${escTxt(lab)}</span></td><td class="n">${sc.toFixed(2)}</td><td>${escTxt(st)}</td></tr>`}).join("");
}

/* ===== contenu piloté par l’état réel du run ===== */
function applySignalState(key){
  S=SCN[key];
  document.documentElement.style.setProperty("--accent",S.accent);
  document.documentElement.style.setProperty("--accent-soft",S.soft);
  $("#etatMot").textContent=S.mot;
  $("#etatDesc").textContent=S.etatDesc;
  $("#etatChips").innerHTML=(S.chips||['chaleur marquée','humidex élevé']).map(x=>`<span class="chip">${escTxt(x)}</span>`).join("");
  $("#opeMot").textContent=S.ope;$("#opeDesc").textContent=S.opeDesc;
  ringGauge("#confGauge",S.conf/100,S.conf,"CONFIANCE",S.accent);
  ringGauge("#voidGauge",S.indice,S.indice.toFixed(2),"VOID COLLAPSE",S.accent);
  $("#kScore").textContent=S.score.toFixed(2);$("#kConf").textContent=S.conf;
  $("#retIndice").textContent=S.indice.toFixed(2);$("#retZone").textContent=S.zone;
  drawTrack("#track1","#trackVal1");drawTrack("#track2","#trackVal2");
  // EWS
  $("#varVal").textContent=S.ews.v.toFixed(2);$("#acVal").textContent=S.ews.ac.toFixed(2);$("#flVal").textContent=S.ews.fl;
  spark("#varSpark",S.ews.vs,S.accent);spark("#acSpark",S.ews.acs,S.accent);
  const fl=$("#flick");fl.innerHTML="";for(let i=0;i<8;i++){const b=document.createElement("i");if(i<S.ews.fl){b.className="on";if(S.ews.flA&&i>=S.ews.fl-2)b.className="on fl";}fl.appendChild(b);}
  // confiance bars
  $("#confBars").innerHTML=S.bars.map(([n,p])=>`<div class="bar"><div class="bl"><span>${n}</span><span class="pct">${p}%</span></div><div class="track"><div class="fill" style="width:${p}%;background:${p===0?'var(--ink-faint)':'var(--accent)'}"></div></div></div>`).join("");
  $("#confSummary").textContent=`Score global ${S.conf}% : qualité des sources, cohérence interne, confirmation externe et cohérence spatiale.`;
  drawMap();
}

/* ===== navigation ===== */
function go(v){document.querySelectorAll(".tab").forEach(t=>t.setAttribute("aria-selected",t.dataset.v===v));document.querySelectorAll(".view").forEach(x=>x.classList.toggle("on",x.dataset.view===v));if(v==="carte"){initMap();setTimeout(()=>{if(MV_MAP)MV_MAP.invalidateSize();},180);}window.scrollTo({top:0,behavior:reduced?'auto':'smooth'});}
window.go=go;
document.querySelectorAll(".tab").forEach(t=>t.addEventListener("click",()=>go(t.dataset.v)));
document.querySelectorAll("#subnav button").forEach(b=>b.addEventListener("click",()=>{document.querySelectorAll("#subnav button").forEach(x=>x.setAttribute("aria-pressed","false"));b.setAttribute("aria-pressed","true");document.querySelectorAll(".subview").forEach(x=>x.classList.toggle("on",x.dataset.sv===b.dataset.sv));}));



/* ===== adaptation dynamique depuis le view-model Python ===== */
function sevPill(cls){return {calm:"stable",info:"veille",watch:"veille",elevated:"latent",high:"actif",danger:"actif"}[String(cls||"").toLowerCase()]||"veille";}
function sevAccent(cls){return {calm:"var(--calm)",info:"var(--watch)",watch:"var(--watch)",elevated:"var(--latent)",high:"var(--alert)",danger:"var(--alert)"}[String(cls||"").toLowerCase()]||"var(--accent)";}
function firstNum(...vals){for(const v of vals){const n=Number(v);if(Number.isFinite(n))return n;}return 0;}
function hourNum(h){const m=String(h||"").match(/(\d{1,2})h|T(\d{2}):/);return m?Number(m[1]||m[2]):null;}
function fmtHourFromIso(x){const s=String(x||"");const m=s.match(/T(\d{2}):(\d{2})/);return m?`${Number(m[1])}h`:s.replace(":00","")||"—";}
function scoreToZone(v){if(v<0.30)return "Stable";if(v<0.45)return "Veille";if(v<0.65)return "Latent";return "Transition → Bascule";}
function stateNameFromClass(cls,idx){const r={calm:0,info:1,watch:2,elevated:3,high:4,danger:5}[String(cls||"").toLowerCase()]||0;if(r>=4||idx>=0.72)return "bascule";if(r>=2||idx>=0.45)return "tension";return "stable";}
function iconForBlock(k){return {charge:"flame",declencheur:"bolt",organisation:"layers",couvercle:"lid",observation:"eye",amont:"arrow",void:"target"}[k]||"target";}
function updateScenarioFromVM(vm){
  const s=vm.simple||{},op=vm.operational||{},h=vm.heat||{};
  const level=s.operational_level||s.severity||{};
  const conf=Math.round(clamp01(s.confidence&&s.confidence.score)*100)||0;
  const idx=clamp01(op.void_collapse_signal ?? s.model_score ?? 0);
  const key=stateNameFromClass(level.class,idx);
  const factors=(s.confidence&&s.confidence.factors)||[];
  const bars=factors.length?factors.map(f=>[f.name,Math.round(clamp01(f.value)*100)]):[["Qualité des sources",conf],["Cohérence interne",conf],["Confirmation externe",0],["Cohérence spatiale",0]];
  const chips=[]; if(h.level&&h.level.label)chips.push(h.level.label); if(s.main_zone&&s.main_zone.name)chips.push("zone : "+s.main_zone.name);
  const base={accent:sevAccent(level.class),soft:"rgba(70,197,176,.13)",mot:level.label||"Veille",ope:(op.transition_level&&op.transition_level.label)||level.label||"Stable",zone:scoreToZone(idx),indice:idx,score:firstNum(s.model_score,0),conf:conf,opeDesc:op.interpretation||"Lecture opérationnelle issue du moteur MeteoVoid.",etatDesc:s.synthesis||s.public_wording||"Veille non officielle MeteoVoid.",ews:{v:firstNum(vm.expert&&vm.expert.early_warning&&vm.expert.early_warning.network_early_warning_score,idx),vs:[idx*.45,idx*.52,idx*.60,idx*.70,idx*.82,idx*.92,idx].map(clamp01),ac:Math.max(0.2,Math.min(.96,0.45+idx*.45)),acs:[.35,.42,.50,.58,.66,.74,.82].map(x=>Math.min(.96,x*idx+0.2)),fl:Math.min(8,Math.max(1,Math.round(idx*8))),flA:true},bars:bars,mapZone:key==="bascule"?"alert":key==="tension"?"watch":"calm",chips:chips};
  SCN.stable={...SCN.stable,...base,accent:"var(--calm)",soft:"rgba(70,197,176,.13)"};
  SCN.tension={...SCN.tension,...base,accent:"var(--watch)",soft:"rgba(232,179,57,.14)"};
  SCN.bascule={...SCN.bascule,...base,accent:"var(--alert)",soft:"rgba(240,86,108,.15)"};
  return key;
}
function hydrateFromVM(vm){
  if(!vm||!vm.simple)return "stable";
  const s=vm.simple||{},op=vm.operational||{},heat=vm.heat||{},expert=vm.expert||{},meta=vm.meta||{};
  RUN=String(meta.generated_at||RUN);
  const win=s.critical_window||{};
  document.querySelector('.brand .sub').textContent=`Veille de bascule convective · ${meta.data_mode||'run'}`;
  BASE.composantes=(op.blocks||BASE.composantes).map(b=>({n:b.title||b.n||"Signal",v:clamp01(b.score??b.v),d:b.phrase||b.d||"",chips:b.drivers||b.chips||[],ic:iconForBlock(b.key)}));
  const tl=op.timeline||{}; const hrs=(tl.hours||[]).map(x=>({h:hourNum(x.hour)||hourNum(x.time),s:clamp01(x.max_score??x.mean_score)})).filter(x=>x.h!=null);
  if(hrs.length>=2){BASE.timeline.hours=hrs.map(x=>x.h);BASE.timeline.score=hrs.map(x=>x.s);const peak=hrs.reduce((a,b)=>b.s>a.s?b:a,hrs[0]);BASE.timeline.pic={h:peak.h,v:peak.s};BASE.timeline.sensFrom=hourNum(win.start_hour)||hrs[0].h;BASE.timeline.sensTo=hourNum(win.end_hour)||hrs[hrs.length-1].h;BASE.timeline.events=(tl.narrative||[]).map(x=>[hourNum(x.hour)||BASE.timeline.sensFrom,x.text||"signal",x.kind==="peak"?"var(--alert)":x.kind==="elevated"?"var(--latent)":"var(--watch)"]);}
  BASE.why=((op.alert_explanation&&op.alert_explanation.bullets)||s.headline_signals||BASE.why||[]);
  if(op.alert_explanation&&op.alert_explanation.title)document.getElementById('whyHead').textContent=op.alert_explanation.title;
  if(heat){BASE.heat.niveau=Math.max(1,Math.min(6,(heat.level&&heat.level.rank)||4));const ht=(heat.timeline||[]).filter(x=>x.t!=null||x.hx!=null);if(ht.length>=2){BASE.heat.courbe={h:ht.map(x=>hourNum(x.h)||0),t:ht.map(x=>firstNum(x.t,0)),hx:ht.map(x=>firstNum(x.hx,x.t,0)),pic:hourNum(heat.peak_hour)||hourNum(ht[0].h)||0};}
    BASE.heat.lieux=(heat.hottest||[]).map(x=>[x.name||"—",x.region||"",(x.level&&x.level.class)==="danger"?"extreme":(x.level&&x.level.class)==="high"?"forte+":"forte",firstNum(x.temperature_c,0),Math.round(firstNum(x.humidex,0)),firstNum(x.dew_point_c,0)]);
    BASE.heat.regions=(heat.regional_weather||[]).map(x=>({label:x.label||x.region||"—",station:x.representative_station||"—",temperature:firstNum(x.temperature_c,0),humidex:firstNum(x.humidex,0),precip:firstNum(x.precip_prob_pct,0),severity:(x.severity&&x.severity.label)||"—"}));
    BASE.heat.conseils=heat.advice||BASE.heat.conseils; BASE.heat.note=heat.note||BASE.heat.note;
  }
  BASE.stations=(expert.stations||[]).slice(0,12).map(x=>[x.name||"—",x.region||"",firstNum(x.score,0),((x.severity||{}).label)||"—",sevPill((x.severity||{}).class),fmtHourFromIso(x.worst_time),((x.signals||[]).join(" · "))]);
  BASE.provinces=(expert.provinces||[]).map(x=>[x.province||"—",firstNum(x.max_score,0),x.top_station||"",((x.severity||{}).label)||"—",sevPill((x.severity||{}).class)]);
  const stGeo=(expert.stations||[]).filter(x=>x.lat!=null&&x.lon!=null&&insideBelgiumView(Number(x.lat),Number(x.lon))&&!String(x.region||"").startsWith("approach_")); if(stGeo.length){STATIONS_GEO.length=0;stGeo.forEach(x=>STATIONS_GEO.push([x.name||x.station_id,x.lat,x.lon]));}
  return updateScenarioFromVM(vm);
}
function renderBulletin(vm){
  const b=(vm&&vm.bulletin)||{},lv=b.level||{};
  const headline=document.getElementById('bulletinHeadline'); if(!headline)return;
  headline.textContent=b.headline||"Bulletin MeteoVoid";
  document.getElementById('bulletinSummary').textContent=b.summary||b.public_wording||"Bulletin non officiel généré automatiquement.";
  document.getElementById('bulletinChips').innerHTML=[b.issued_at,b.timezone,b.validity,lv.label].filter(Boolean).map(x=>`<span class="chip">${escTxt(x)}</span>`).join("");
  const sectionHtml=(b.sections||[]).map(sec=>{const items=(sec.items||[]).map(x=>`<li>${escTxt(x)}</li>`).join("");const advice=(sec.advice||[]).map(x=>`<li>${escTxt(x)}</li>`).join("");return `<div class="card"><div class="eyebrow"><span class="d"></span>${escTxt(sec.title||'Section')}</div>${sec.body?`<p style="color:var(--ink-dim);margin-top:12px">${escTxt(sec.body)}</p>`:""}${items?`<ul style="margin:10px 0 0;color:var(--ink)">${items}</ul>`:""}${sec.note?`<div class="note">${escTxt(sec.note)}</div>`:""}${advice?`<ul class="advice">${advice}</ul>`:""}</div>`;}).join("");
  document.getElementById('bulletinSections').innerHTML=sectionHtml+`<div class="note">${escTxt(b.disclaimer||'Prototype technique non officiel.')} Bulletin non officiel : il ne remplace pas l’IRM/KMI ni MeteoAlarm.</div>`;
}
function fieldValueHtml(field){
  if(!field||typeof field!=="object")return "<span class=\"muted\">manquant</span>";
  const available=!!field.available;
  const value=field.value;
  const unit=field.unit||"";
  const status=field.status||"missing";
  const val=(value===null||value===undefined||value==="")?"—":String(value)+(unit&&unit!=="frame"&&unit!=="layer"&&unit!=="impacts"?" "+unit:"");
  const cls=available?"pill stable":"pill veille";
  return `<span class="${cls}"><span class="pd"></span>${escTxt(available?val:status)}</span>`;
}
function renderConvectiveLiveInputs(vm){
  const box=document.getElementById('liveConvectiveInputs'); if(!box)return;
  const live=(vm&&vm.expert&&vm.expert.convective_live_inputs)||{};
  const fields=(live.fields&&typeof live.fields==='object')?live.fields:{};
  const order=['dew_point_c','cape_jkg','cin_jkg','shear_0_6km_ms','surface_convergence_index','pressure_hpa','wind_gust_ms','pwat_mm','temperature_850hpa_c','temperature_700hpa_c','temperature_500hpa_c','radar','lightning','satellite'];
  const rows=order.map(k=>{const f=fields[k]||{};return `<tr><td><div class="place">${escTxt(f.label||k)}</div><div class="sub">${escTxt(f.source||f.basis||'source réelle requise')}</div></td><td>${fieldValueHtml(f)}</td><td>${escTxt(f.station_count??f.sample_count??'—')}</td><td>${escTxt(f.basis||f.status||'—')}</td></tr>`}).join('');
  const avail=Number(live.available_count||0), req=Number(live.required_count||order.length);
  box.innerHTML=`<div class="statline"><span class="b mono">${avail}/${req}</span><span class="t">champs disponibles dans le dernier run réel · aucune valeur simulée</span></div><table style="margin-top:12px"><thead><tr><th>Champ</th><th>Valeur / état</th><th>Stations</th><th>Base</th></tr></thead><tbody>${rows}</tbody></table><div class="note">${escTxt(live.note||'Les champs absents restent absents jusqu’à connexion d’un fournisseur réel.')}</div>`;
}
function renderDynamicLinks(vm){
  const e=(vm&&vm.expert)||{};
  const f=document.getElementById('expertFrameLinks'); if(f){f.innerHTML=(e.frames||[]).slice(0,9).map(x=>`<a class="kpi" href="${escTxt(x.file)}"><div class="name">${escTxt(x.group||'Carte')}</div><div class="foot mono">${escTxt(x.label||x.file)}</div></a>`).join("");}
  const ex=document.getElementById('expertExportLinks'); if(ex){ex.innerHTML=`<div class="row c3">${(e.exports||[]).slice(0,9).map(x=>`<a class="kpi" href="${escTxt(x.file)}"><div class="name">Export</div><div class="foot mono">${escTxt(x.label||x.file)}</div></a>`).join("")}</div>`;}
  renderConvectiveLiveInputs(vm);
}
function renderMap(){drawMap();}
function updateLiveBadges(vm){
  const meta=(vm&&vm.meta)||{};
  const runLabel=meta.run_id||meta.generated_at||RUN||"run actuel";
  const modeLabel=meta.data_mode||"live static";
  const fr=document.getElementById("footerRun"); if(fr)fr.textContent=String(runLabel).slice(0,32);
  const fm=document.getElementById("footerMode"); if(fm)fm.textContent=String(modeLabel).replace(/demo/gi,"run");
  const live=document.getElementById("liveState"); if(live)live.textContent="dernier run publié";
}
function applyLiveModel(vm){
  const state=hydrateFromVM(vm);
  updateLiveBadges(vm);
  renderStatic();
  renderBulletin(vm);
  renderDynamicLinks(vm);
  applySignalState(state);
  updateLeafletMap();
}
function loadLiveModel(){
  if(location.protocol==="file:")return;
  fetch("api/latest.json",{cache:"no-store"})
    .then(r=>r.ok?r.json():Promise.reject(new Error("api_latest_http")))
    .then(latest=>{
      const vm={...FALLBACK,meta:{...(FALLBACK.meta||{}),generated_at:latest.generated_at||FALLBACK.meta?.generated_at,run_id:latest.run_id||FALLBACK.meta?.run_id,data_mode:latest.data_mode||FALLBACK.meta?.data_mode},simple:{...(FALLBACK.simple||{}),operational_level:latest.operational_level||FALLBACK.simple?.operational_level,severity:latest.severity||FALLBACK.simple?.severity,model_score:latest.model_score??FALLBACK.simple?.model_score,score_layers:latest.score_layers||FALLBACK.simple?.score_layers,confidence:latest.confidence||FALLBACK.simple?.confidence,critical_window:latest.critical_window||FALLBACK.simple?.critical_window,main_zone:latest.main_zone||FALLBACK.simple?.main_zone,synthesis:latest.synthesis||FALLBACK.simple?.synthesis,public_wording:latest.public_wording||FALLBACK.simple?.public_wording,official_alert:latest.official_alert??FALLBACK.simple?.official_alert,public_alert_allowed:latest.public_alert_allowed??FALLBACK.simple?.public_alert_allowed,strong_external_confirmation:latest.strong_external_confirmation??FALLBACK.simple?.strong_external_confirmation},operational:{...(FALLBACK.operational||{}),void_collapse_signal:latest.void_collapse_signal??FALLBACK.operational?.void_collapse_signal,transition_level:latest.transition_level||FALLBACK.operational?.transition_level,alert_explanation:latest.alert_explanation||FALLBACK.operational?.alert_explanation}};
      return Promise.allSettled([
        fetch("api/stations.json",{cache:"no-store"}).then(r=>r.ok?r.json():null),
        fetch("api/timeline.json",{cache:"no-store"}).then(r=>r.ok?r.json():null),
        fetch("api/transition.json",{cache:"no-store"}).then(r=>r.ok?r.json():null),
        fetch("api/heat.json",{cache:"no-store"}).then(r=>r.ok?r.json():null),
        fetch("api/sources.json",{cache:"no-store"}).then(r=>r.ok?r.json():null),
        fetch("api/validation.json",{cache:"no-store"}).then(r=>r.ok?r.json():null),
        fetch("api/convective_live.json",{cache:"no-store"}).then(r=>r.ok?r.json():null)
      ]).then(results=>{
        const [stations,timeline,transition,heat,sources,validation,convectiveLive]=results.map(x=>x.status==="fulfilled"?x.value:null);
        if(stations){vm.expert={...(vm.expert||{}),stations:stations.stations||vm.expert?.stations,provinces:stations.provinces||vm.expert?.provinces};}
        if(timeline){vm.operational={...(vm.operational||{}),timeline:{...(vm.operational?.timeline||{}),...timeline}};}
        if(transition){vm.operational={...(vm.operational||{}),...transition};}
        if(heat){vm.heat={...(vm.heat||{}),...heat};}
        if(sources){vm.expert={...(vm.expert||{}),sources:sources.sources||vm.expert?.sources,observation:sources.observation||vm.expert?.observation,watchdog:sources.watchdog||vm.expert?.watchdog};}
        if(validation){vm.expert={...(vm.expert||{}),validation:{...(vm.expert?.validation||{}),...validation}};}
        if(convectiveLive){vm.expert={...(vm.expert||{}),convective_live_inputs:{...(vm.expert?.convective_live_inputs||{}),...convectiveLive}};}
        applyLiveModel(vm);
      });
    })
    .catch(()=>{updateLiveBadges(FALLBACK);});
}

applyLiveModel(FALLBACK);
loadLiveModel();
if(location.protocol!=="file:")setInterval(loadLiveModel,600000);

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
        payload["open_data_stack"] = public_profile_for_country(country)
        payload["source_strategy"] = payload["open_data_stack"].get("strategy")
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
<html lang="fr" data-theme="dark">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>MeteoVoid Europe · Veille radar amont</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#e9edf3;--bg-2:#eef2f7;--panel:#ffffff;--panel-2:#f4f7fb;--inset:#eef3f9;--ink:#0a1322;--ink-2:#43546b;--muted:#82909f;--line:#e1e8f0;--accent:#2f49d8;--accent-soft:#eaedfb;--shadow:0 2px 4px rgba(13,28,55,.05),0 12px 30px rgba(13,28,55,.07);--r:14px;--r-lg:20px;--f-display:'Space Grotesk',ui-sans-serif,system-ui,Segoe UI,sans-serif;--f-body:'Inter',ui-sans-serif,system-ui,Segoe UI,Roboto,Arial,sans-serif;--f-mono:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,monospace;--c-calm:#16a075;--c-info:#3a7ec4;--c-watch:#cf9a1f;--c-elevated:#dd7634;--c-high:#d65238;--c-danger:#cf2e39}
[data-theme="dark"]{--bg:#070b13;--bg-2:#0a101b;--panel:#111826;--panel-2:#0d141f;--inset:#0c121d;--ink:#e9f0fa;--ink-2:#9fb1c8;--muted:#697a92;--line:#1e293b;--accent:#6f84ff;--accent-soft:#1a2240;--shadow:0 2px 6px rgba(0,0,0,.45),0 18px 40px rgba(0,0,0,.5);--c-calm:#1cb98a;--c-info:#5298e0;--c-watch:#e3b13b;--c-elevated:#ef8a4c;--c-high:#ec6a50;--c-danger:#e74752}
*{box-sizing:border-box}html,body{margin:0}body{font-family:var(--f-body);color:var(--ink);line-height:1.5;background:var(--bg);background-image:radial-gradient(1200px 480px at 84% -10%,color-mix(in srgb,var(--accent) 7%,transparent),transparent),linear-gradient(rgba(20,40,80,.035) 1px,transparent 1px),linear-gradient(90deg,rgba(20,40,80,.035) 1px,transparent 1px);background-size:auto,34px 34px,34px 34px;background-attachment:fixed}a{color:var(--accent);text-decoration:none;font-weight:700}a:hover{text-decoration:underline}.cmd{position:sticky;top:0;z-index:20;background:color-mix(in srgb,var(--panel) 86%,transparent);backdrop-filter:blur(14px) saturate(1.3);border-bottom:1px solid var(--line)}.cmd-wrap{max-width:1240px;margin:0 auto;display:flex;align-items:center;gap:18px;padding:12px 24px}.brand{display:flex;align-items:center;gap:12px;min-width:0}.mark{width:40px;height:40px;border-radius:12px;background:linear-gradient(140deg,#1c9f9c,#2f49d8);display:grid;place-items:center;color:#fff;box-shadow:0 6px 18px color-mix(in srgb,var(--accent) 40%,transparent)}.brand h1{font-family:var(--f-display);font-size:17px;font-weight:600;margin:0;letter-spacing:-.02em;line-height:1.1}.brand p{margin:1px 0 0;font-size:11.5px;color:var(--muted)}.cmd-right{margin-left:auto;display:flex;align-items:center;gap:14px}.status-chip{display:flex;align-items:center;gap:9px;border:1px solid var(--line);border-radius:999px;padding:6px 12px;background:var(--panel-2)}.live-dot{width:8px;height:8px;border-radius:50%;background:var(--c-calm)}.st-k{font-family:var(--f-mono);font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}.st-v{font-family:var(--f-mono);font-size:12px;font-weight:700}.tgl{width:38px;height:38px;border-radius:11px;border:1px solid var(--line);background:var(--panel-2);color:var(--ink-2);cursor:pointer}.tabs{max-width:1240px;margin:0 auto;display:flex;gap:2px;padding:0 24px;overflow-x:auto}.tab{position:relative;border:0;background:transparent;color:var(--muted);padding:12px 15px 13px;font-weight:700;cursor:pointer;font-size:13.5px;white-space:nowrap}.tab:after{content:"";position:absolute;left:12px;right:12px;bottom:0;height:2px;background:var(--accent);transform:scaleX(0);transition:.2s}.tab:hover,.tab.active{color:var(--ink)}.tab.active:after{transform:scaleX(1)}main{max-width:1240px;margin:0 auto;padding:26px 24px 16px}.disclaimer{display:flex;gap:10px;border:1px solid color-mix(in srgb,var(--c-watch) 32%,var(--line));border-left:3px solid var(--c-watch);border-radius:10px;padding:11px 14px;font-size:12.5px;color:var(--ink-2);margin-bottom:22px;background:color-mix(in srgb,var(--c-watch) 8%,var(--panel))}.view{display:none}.view.active{display:block}.hero{position:relative;border:1px solid var(--line);border-radius:var(--r-lg);background:var(--panel);box-shadow:var(--shadow);overflow:hidden;padding:28px}.hero:before{content:"";position:absolute;inset:0;background:radial-gradient(620px 280px at 90% -40%,color-mix(in srgb,var(--accent) 12%,transparent),transparent);pointer-events:none}.hero>*{position:relative}.hero-grid{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(290px,.6fr);gap:26px;align-items:center}.eyebrow{font-family:var(--f-mono);font-size:10.5px;text-transform:uppercase;letter-spacing:.14em;color:var(--muted);font-weight:700}.hero h2{font-family:var(--f-display);font-size:clamp(32px,5vw,52px);line-height:1;margin:7px 0 10px;letter-spacing:-.04em}.lead{font-size:15px;color:var(--ink-2);margin:0;max-width:70ch}.hero-tags,.links{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}.pill,.links a{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);border-radius:999px;background:var(--panel-2);padding:7px 11px;font-size:12.5px;color:var(--ink-2)}.links a{color:var(--accent)}.grid{display:grid;gap:14px}.cards2{grid-template-columns:repeat(2,minmax(0,1fr))}.cards3{grid-template-columns:repeat(3,minmax(0,1fr))}.cards4{grid-template-columns:repeat(4,minmax(0,1fr))}.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);box-shadow:var(--shadow);padding:18px}.card h3,.card h2{font-family:var(--f-display);margin:4px 0 8px}.kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px;margin:18px 0}.kpi{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px;box-shadow:var(--shadow)}.kpi .v{font-family:var(--f-display);font-size:30px;font-weight:700;letter-spacing:-.03em}.kpi .k{font-family:var(--f-mono);font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.12em}.section-title{font-family:var(--f-mono);font-size:11px;text-transform:uppercase;letter-spacing:.13em;color:var(--muted);font-weight:700;margin:30px 0 13px;display:flex;align-items:center;gap:10px}.section-title:before{content:"";width:5px;height:5px;border-radius:50%;background:var(--accent)}.muted{color:var(--muted);font-size:13px}.small{font-size:12px}.score{font-family:var(--f-display);font-size:42px;font-weight:700;letter-spacing:-.04em}.ok{color:var(--c-calm)}.watch{color:var(--c-watch)}.danger{color:var(--c-danger)}.bar{height:8px;background:var(--inset);border-radius:999px;overflow:hidden}.bar span{display:block;height:100%;background:linear-gradient(90deg,var(--c-info),var(--c-calm));border-radius:999px}.chain{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:10px}.step{position:relative}.step:after{content:"";position:absolute;top:24px;right:-10px;width:10px;height:1px;background:var(--line)}.step:last-child:after{display:none}.step .n{width:46px;height:46px;border-radius:14px;background:var(--panel-2);border:1px solid var(--line);display:grid;place-items:center;font-family:var(--f-display);font-weight:700}.step h3{font-size:14px}.country-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.country-card{padding:0;overflow:hidden}.country-head{padding:18px;border-bottom:1px solid var(--line);background:linear-gradient(135deg,color-mix(in srgb,var(--accent) 10%,var(--panel)),var(--panel))}.country-body{padding:18px}.country-title{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.badge{font-family:var(--f-mono);font-size:10px;text-transform:uppercase;letter-spacing:.08em;border:1px solid var(--line);border-radius:999px;padding:5px 8px;background:var(--panel-2);color:var(--ink-2)}.badge.ok{border-color:color-mix(in srgb,var(--c-calm) 35%,var(--line));background:color-mix(in srgb,var(--c-calm) 10%,var(--panel));color:var(--c-calm)}.badge.watch{border-color:color-mix(in srgb,var(--c-watch) 35%,var(--line));background:color-mix(in srgb,var(--c-watch) 10%,var(--panel));color:var(--c-watch)}.badge.info{border-color:color-mix(in srgb,var(--c-info) 35%,var(--line));background:color-mix(in srgb,var(--c-info) 10%,var(--panel));color:var(--c-info)}.dl{display:grid;grid-template-columns:1fr auto;gap:12px;border-top:1px solid var(--line);padding:8px 0;font-size:13px}.dl:first-child{border-top:0}.src-list{display:grid;gap:8px;margin-top:10px}.src{border:1px solid var(--line);border-radius:12px;padding:10px;background:var(--panel-2)}.src-top{display:flex;justify-content:space-between;gap:8px}.src b{font-size:13px}.iframe-card{padding:0;overflow:hidden}.iframe-card iframe,.frame{width:100%;height:540px;border:0;background:var(--inset)}table{width:100%;border-collapse:collapse;font-size:13px}th,td{border-bottom:1px solid var(--line);padding:10px;text-align:left;vertical-align:top}th{font-family:var(--f-mono);font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.1em;background:var(--panel-2)}pre{max-height:520px;overflow:auto;background:var(--panel-2);border:1px solid var(--line);border-radius:14px;padding:14px;font-size:12px;color:var(--ink-2)}footer{max-width:1240px;margin:0 auto 20px;padding:0 24px;color:var(--muted);font-size:12px}.live-map{height:620px;min-height:420px;border-radius:14px;overflow:hidden;border:1px solid var(--line);background:var(--inset)}.map-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.map-actions button{border:1px solid var(--line);background:var(--panel-2);color:var(--ink);border-radius:999px;padding:8px 12px;font-weight:700;cursor:pointer}.map-status{font-family:var(--f-mono);font-size:11px;color:var(--muted);margin-top:10px}.leaflet-popup-content-wrapper,.leaflet-popup-tip{background:var(--panel);color:var(--ink);border:1px solid var(--line)}.leaflet-container{font-family:var(--f-body)}@media(max-width:980px){.hero-grid,.cards2,.cards3,.cards4,.country-grid,.chain,.kpis{grid-template-columns:1fr}.cmd-wrap{padding:10px 14px}.tabs{padding:0 14px}main{padding:18px 14px}.iframe-card iframe,.frame{height:420px}}
</style>
</head>
<body>
<header class="cmd"><div class="cmd-wrap"><div class="brand"><div class="mark">EU</div><div><h1>MeteoVoid Europe</h1><p>Page Europe complète · pays disponibles · radar live · Espagne · France · Suisse · Pays-Bas · Allemagne · Danemark · même design que Belgique</p></div></div><div class="cmd-right"><div class="status-chip"><span class="live-dot"></span><div><div class="st-k">run</div><div class="st-v" id="stamp"></div></div></div><button class="tgl" id="theme">◐</button></div></div><nav class="tabs"><button class="tab active" data-view="simple">Vue simple</button><button class="tab" data-view="operational">Opérationnel</button><button class="tab" data-view="radar">Carte Europe</button><button class="tab" data-view="countries">Pays</button><button class="tab" data-view="corridors">Corridors</button><button class="tab" data-view="sources">Sources</button><button class="tab" data-view="expert">Expert</button><a class="tab" href="index.html">Belgique</a><a class="tab" href="methodology.html">Méthodologie</a></nav></header>
<main><div class="disclaimer"><b>Prototype non officiel.</b> Page Europe amont. Les cartes et interfaces ne remplacent pas les services météorologiques nationaux.</div><section class="view active" id="view-simple"></section><section class="view" id="view-operational"></section><section class="view" id="view-radar"></section><section class="view" id="view-countries"></section><section class="view" id="view-corridors"></section><section class="view" id="view-sources"></section><section class="view" id="view-expert"></section></main><footer id="foot"></footer>
<script id="europe-bootstrap" type="application/json">__EUROPE_BOOTSTRAP__</script>
<script>
const M=JSON.parse(document.getElementById('europe-bootstrap').textContent);const esc=s=>String(s==null?'':s).replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));const pct=v=>v==null?'n/a':Math.round(Math.max(0,Math.min(1,Number(v)||0))*100)+'%';const num=v=>v==null?'n/a':(typeof v==='number'?v.toFixed(2):v);const bar=v=>`<div class="bar"><span style="width:${Math.round(Math.max(0,Math.min(1,Number(v)||0))*100)}%"></span></div>`;function badge(txt,kind){return `<span class="badge ${kind||'info'}">${esc(txt)}</span>`}
function kpis(){const s=M.summary||{};return `<div class="kpis"><div class="kpi"><div class="k">Pays suivis</div><div class="v">${esc(s.country_count||0)}</div></div><div class="kpi"><div class="k">Sources radar</div><div class="v">${esc(s.source_count||0)}</div></div><div class="kpi"><div class="k">Interfaces prêtes</div><div class="v">${esc(s.configured_source_count||0)}</div></div><div class="kpi"><div class="k">Preuve machine</div><div class="v">${esc(s.machine_country_count||0)}</div></div><div class="kpi"><div class="k">Clés manquantes</div><div class="v">${esc(s.missing_api_key_count||0)}</div></div></div>`}
function renderSimple(){const s=M.simple||{};return `<div class="hero"><div class="hero-grid"><div><div class="eyebrow">Vue simple Europe</div><h2>Europe amont</h2><p class="eyebrow">Source → radar → métrique → corridor</p><p class="lead">${esc(s.synthesis)}</p><div class="hero-tags"><span class="pill">Espagne</span><span class="pill">France</span><span class="pill">Suisse</span><span class="pill">Pays-Bas</span><span class="pill">RainViewer</span><span class="pill">OPERA ORD</span></div></div><div class="card"><div class="eyebrow">Disponibilité radar</div><div class="score ${s.machine_country_count?'ok':'watch'}">${esc(s.machine_country_count||0)}/${esc(s.country_count||0)}</div><p class="muted">Pays avec métriques machine. Les autres restent en interface prête ou affichage.</p>${bar(s.readiness_score)}</div></div></div>${kpis()}<div class="grid cards3"><div class="card"><h3>Ce que la page Europe ajoute</h3><p class="muted">Une lecture amont par pays, par source radar, par corridor, et par niveau de preuve.</p></div><div class="card"><h3>Ce que cela ne dit pas</h3><p class="muted">Une carte affichée ou un endpoint référencé ne suffit pas. Il faut une trame radar lue pour obtenir une preuve machine.</p></div><div class="card"><h3>Lien Belgique</h3><p class="muted">France et Pays-Bas sont les couloirs les plus directs. Espagne et Suisse enrichissent la lecture dynamique.</p></div></div>`}
function renderOperational(){const chain=(M.operational&&M.operational.chain)||[];return `<div class="section-title">Chaîne de preuve radar</div><div class="chain">${chain.map((x,i)=>`<div class="card step"><div class="n">${i+1}</div><h3>${esc(x.step)}</h3><p class="muted">${esc(x.text)}</p>${bar(x.score)}</div>`).join('')}</div><div class="section-title">Pourquoi ces pays</div><div class="grid cards2">${((M.operational&&M.operational.why_it_matters)||[]).map(x=>`<div class="card"><p>${esc(x)}</p></div>`).join('')}</div>`}
function layerCard(x){return `<div class="card"><div class="eyebrow">${esc(x.evidence_level)}</div><h3>${esc(x.label)}</h3><p class="muted">${esc(x.role)}</p><div class="dl"><span>Statut</span><b>${esc(x.status)}</b></div><div class="dl"><span>Lecture</span><b>${esc(x.meaning)}</b></div><div class="links"><a href="${esc(x.file)}">Ouvrir</a></div></div>`}
function renderRadar(){return `
<style>
.cockpit{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:14px}
.mvmapwrap{position:relative}
#europeMap.live-map{height:640px}
.mvloading{position:absolute;inset:0;display:grid;place-items:center;z-index:1100;background:color-mix(in srgb,var(--bg) 55%,transparent);backdrop-filter:blur(2px);pointer-events:none;opacity:0;transition:.2s;font-family:var(--f-mono);font-size:13px}
.mvloading.on{opacity:1}.mvloading span{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:8px 14px}
.mvlayers{position:absolute;top:12px;left:12px;z-index:1000;background:color-mix(in srgb,var(--panel) 90%,transparent);border:1px solid var(--line);border-radius:12px;padding:9px;backdrop-filter:blur(8px);display:grid;gap:2px;min-width:188px;box-shadow:var(--shadow)}
.mvlayers .h{font-family:var(--f-mono);font-size:10px;text-transform:uppercase;letter-spacing:.12em;color:var(--muted);padding:2px 4px 4px}
.mvlyr{display:flex;align-items:center;gap:8px;padding:5px 7px;border-radius:8px;cursor:pointer;font-size:12.5px}
.mvlyr:hover{background:var(--panel-2)}.mvlyr input{accent-color:var(--accent)}.mvlyr .sw{width:10px;height:10px;border-radius:3px;flex:0 0 auto}
.mvtime{position:absolute;left:12px;right:12px;bottom:12px;z-index:1000;background:color-mix(in srgb,var(--panel) 92%,transparent);border:1px solid var(--line);border-radius:12px;padding:10px 12px;backdrop-filter:blur(8px);box-shadow:var(--shadow)}
.mvtime .row{display:flex;align-items:center;gap:11px}
.mvplay{width:36px;height:36px;border-radius:10px;border:1px solid var(--line);background:var(--panel-2);color:var(--ink);cursor:pointer;font-size:14px;flex:0 0 auto}
.mvtime input[type=range]{flex:1}
.mvtlabel{font-family:var(--f-mono);font-size:12.5px;min-width:150px;text-align:right;white-space:nowrap}
.mvrail{display:flex;flex-direction:column;gap:12px}
.mvdial{position:relative;width:88px;height:88px;flex:0 0 auto}.mvdial svg{transform:rotate(-90deg)}
.mvdial .vv{position:absolute;inset:0;display:grid;place-items:center;text-align:center}
.mvdial .vv b{font-family:var(--f-display);font-size:22px;line-height:1;display:block}.mvdial .vv span{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.1em}
.mvgw{display:flex;gap:14px;align-items:center}
.mvreg{font-family:var(--f-display);font-size:20px;font-weight:700;margin:0}.mvsub{font-size:12px;color:var(--muted);margin-top:2px}
.mvtrack{height:8px;border-radius:99px;margin:13px 0 6px;position:relative;background:linear-gradient(90deg,var(--c-calm),var(--c-info) 36%,var(--c-watch) 68%,var(--c-danger))}
.mvtrack .c{position:absolute;top:50%;width:13px;height:13px;border-radius:50%;background:#fff;border:2px solid var(--panel);transform:translate(-50%,-50%);box-shadow:0 1px 4px rgba(0,0,0,.5)}
.mvtrl{display:flex;justify-content:space-between;font-size:9.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
.mvmet{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.mvm{border:1px solid var(--line);border-radius:10px;padding:8px 10px;background:var(--panel-2)}
.mvm .k{font-size:9.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}.mvm .v{font-family:var(--f-mono);font-size:16px;margin-top:2px}
.mvhot .r{display:flex;align-items:center;gap:8px;font-size:12px;padding:5px 0;border-top:1px solid var(--line)}
.mvhot .r:first-child{border-top:0}.mvhot .r .sw{width:9px;height:9px;border-radius:3px;flex:0 0 auto}.mvhot .r .nm{flex:1}.mvhot .r .sc{font-family:var(--f-mono);color:var(--muted)}
.mvleg{display:grid;gap:6px;font-size:12px}.mvleg .li{display:flex;gap:8px;align-items:center}.mvleg .sw{width:12px;height:12px;border-radius:3px;flex:0 0 auto}
@media(max-width:980px){.cockpit{grid-template-columns:1fr}#europeMap.live-map{height:460px}}
</style>
<div class="section-title">Carte Europe live · surface de bascule (anticipation)</div>
<div class="cockpit">
  <div class="mvmapwrap">
    <div id="europeMap" class="live-map" aria-label="Carte de bascule Europe"></div>
    <div class="mvloading" id="mvLoading"><span id="mvLoadMsg">Lecture des indices convectifs…</span></div>
    <div class="mvlayers"><div class="h">Couches</div>
      <label class="mvlyr"><input type="checkbox" id="mvL-surf" checked><span class="sw" style="background:linear-gradient(90deg,var(--c-calm),var(--c-danger))"></span>Surface de bascule</label>
      <label class="mvlyr"><input type="checkbox" id="mvL-sta" checked><span class="sw" style="background:#fff;border:2px solid var(--accent)"></span>Détecteurs</label>
      <label class="mvlyr"><input type="checkbox" id="mvL-rad" checked><span class="sw" style="background:#3aa0e0"></span>Radar pluie</label>
      <label class="mvlyr"><input type="checkbox" id="mvL-sat"><span class="sw" style="background:#9aa7b5"></span>Satellite IR</label>
      <label class="mvlyr"><input type="checkbox" id="mvL-net"><span class="sw" style="background:#fff;border:2px solid var(--c-watch)"></span>Réseau radar national</label>
      <label class="mvlyr"><input type="checkbox" id="mvL-box" checked><span class="sw" style="background:transparent;border:1px solid var(--muted)"></span>Cadres pays</label>
    </div>
    <div class="mvtime"><div class="row">
      <button class="mvplay" id="mvPlay" aria-label="Lecture">&#9654;</button>
      <input type="range" id="mvTime" min="0" max="17" value="0" step="1" aria-label="Heure">
      <div class="mvtlabel" id="mvTlabel">&mdash;</div>
    </div></div>
  </div>
  <aside class="mvrail">
    <div class="card">
      <div class="eyebrow" style="margin-bottom:8px">Zone</div>
      <select id="mvRegion" style="width:100%;border:1px solid var(--line);background:var(--panel-2);color:var(--ink);border-radius:9px;padding:8px;font:inherit;margin-bottom:12px"></select>
      <div class="mvgw">
        <div class="mvdial"><svg width="88" height="88" viewBox="0 0 88 88"><circle cx="44" cy="44" r="36" fill="none" stroke="var(--line)" stroke-width="8"/><circle id="mvArc" cx="44" cy="44" r="36" fill="none" stroke="var(--c-calm)" stroke-width="8" stroke-linecap="round" stroke-dasharray="226" stroke-dashoffset="226"/></svg><div class="vv"><b id="mvVal">&mdash;</b><span>bascule</span></div></div>
        <div><p class="mvreg" id="mvReg">&hellip;</p><p class="mvsub" id="mvSub">chargement</p></div>
      </div>
      <div class="mvtrack"><div class="c" id="mvCur" style="left:0%"></div></div>
      <div class="mvtrl"><span>Stable</span><span>Latent</span><span>Transition</span><span>Bascule</span></div>
    </div>
    <div class="card"><div class="eyebrow" style="margin-bottom:8px">Ingrédients · zone agrégée</div>
      <div class="mvmet">
        <div class="mvm"><div class="k">CAPE J/kg</div><div class="v" id="mvCape">&mdash;</div></div>
        <div class="mvm"><div class="k">Inhibition</div><div class="v" id="mvCin">&mdash;</div></div>
        <div class="mvm"><div class="k">Soulèvement LI</div><div class="v" id="mvLi">&mdash;</div></div>
        <div class="mvm"><div class="k">Déclenchement</div><div class="v" id="mvTrig">&mdash;</div></div>
      </div>
    </div>
    <div class="card"><div class="eyebrow" style="margin-bottom:8px">Détecteurs les plus exposés</div><div class="mvhot" id="mvHot"></div></div>
    <div class="card mvleg"><div class="eyebrow" style="margin-bottom:4px">Échelle de bascule</div>
      <div class="li"><span class="sw" style="background:var(--c-calm)"></span>Stable &mdash; énergie faible</div>
      <div class="li"><span class="sw" style="background:var(--c-info)"></span>Latent &mdash; énergie qui monte</div>
      <div class="li"><span class="sw" style="background:var(--c-watch)"></span>Transition &mdash; fenêtre sensible</div>
      <div class="li"><span class="sw" style="background:var(--c-danger)"></span>Bascule &mdash; déclenchement probable</div>
    </div>
  </aside>
</div>
<p class="muted small" style="margin-top:10px">La surface de bascule est un proxy d&rsquo;ingrédients (CAPE &middot; inhibition &middot; LI &middot; déclenchement) calculé en direct depuis Open-Meteo &mdash; une anticipation, pas une confirmation radar. Radar, satellite et réseau national restent des couches d&rsquo;affichage.</p>
<div class="section-title">Couches radar et fallback</div><div class="grid cards4">${(M.radar_layers||[]).map(layerCard).join('')}</div>`}
function countryCard(c){const status=c.machine_radar_available?badge('preuve machine','ok'):badge('interface prête','watch');return `<article class="card country-card"><div class="country-head"><div class="country-title"><div><div class="eyebrow">${esc(c.iso2||'')}</div><h2>${esc(c.label)}</h2></div>${status}</div><p class="muted">${esc(c.belgium_relevance||c.upstream_role||'')}</p></div><div class="country-body"><div class="grid cards2"><div>${bar(c.completeness_score)}<p class="muted">Complétude ${pct(c.completeness_score)}</p></div><div>${bar(c.readiness_score)}<p class="muted">Préparation ${pct(c.readiness_score)}</p></div></div><div class="dl"><span>Sources</span><b>${esc(c.source_count)} dont ${esc(c.configured_source_count)} prêtes</b></div><div class="dl"><span>National / display / nowcast / OPERA</span><b>${esc(c.national_source_count)} / ${esc(c.display_source_count)} / ${esc(c.nowcast_source_count)} / ${esc(c.opera_fallback_count)}</b></div><div class="dl"><span>Fichiers lisibles</span><b>${esc(c.readable_file_count)} / ${esc(c.file_count)}</b></div><div class="dl"><span>Corridor</span><b>${esc(c.corridor_family||'')}</b></div><div class="section-title">Zones à suivre</div><div class="hero-tags">${(c.watch_zones||[]).map(z=>`<span class="pill">${esc(z)}</span>`).join('')}</div><div class="section-title">Sources</div><div class="src-list">${(c.sources||[]).map(s=>`<div class="src"><div class="src-top"><b>${esc(s.provider)}</b>${badge(s.bucket||s.evidence_level,s.bucket==='machine'?'ok':(s.bucket==='blocked'?'watch':'info'))}</div><p class="muted small">${esc(s.role)} · ${esc(s.status)} · ${esc(s.expected_format||'')}</p>${s.api_key_env?`<p class="muted small">Clé : ${esc(s.api_key_env)} ${s.api_key_configured?'configurée':'manquante'}</p>`:''}</div>`).join('')}</div><div class="section-title">Blocages</div><ul>${(c.blockers||[]).map(b=>`<li>${esc(b)}</li>`).join('')}</ul></div></article>`}
function renderCountries(){return `<div class="section-title">Pays au même niveau de lecture</div><div class="country-grid">${(M.countries||[]).map(countryCard).join('')}</div>`}
function renderCorridors(){const rows=M.corridors||[];return `<div class="card"><h2>Corridors amont vers la Belgique</h2><p class="muted">Le but n'est pas de surveiller l'Europe pour elle-même, mais de relier les zones radar aux trajectoires possibles vers la Belgique.</p></div><div class="card" style="overflow:auto;margin-top:14px"><table><thead><tr><th>Corridor</th><th>Score</th><th>Source</th><th>Cibles</th><th>Fenêtre</th><th>Lecture</th></tr></thead><tbody>${rows.map(c=>`<tr><td><b>${esc(c.name||c.id)}</b><p class="muted small">${esc(c.id||'')}</p></td><td>${num(c.score)}</td><td>${esc(c.source_region||'')}</td><td>${esc((c.target_zones||[]).join(', '))}</td><td>${esc((c.estimated_arrival_hours||[]).join(' à '))}</td><td>${esc(c.interpretation||'')}</td></tr>`).join('')}</tbody></table></div>`}
function renderSources(){const rows=M.sources||[];return `<div class="section-title">Registre maître · priorité opérationnelle</div><div class="card" style="overflow:auto"><table><thead><tr><th>Pays</th><th>Fournisseur</th><th>Rôle</th><th>Statut</th><th>Preuve</th><th>Format</th><th>Clé</th><th>Référence</th></tr></thead><tbody>${rows.map(s=>`<tr><td><b>${esc(s.country)}</b></td><td>${esc(s.provider)}</td><td>${esc(s.role||'')}</td><td>${esc(s.status||'')}</td><td>${esc(s.evidence_level||'')}</td><td>${esc(s.expected_format||'')}</td><td>${s.api_key_env?esc(s.api_key_env)+(s.api_key_configured?' configurée':' manquante'):'aucune'}</td><td>${s.public_reference?`<a href="${esc(s.public_reference)}">source</a>`:'-'}</td></tr>`).join('')}</tbody></table></div>`}
function renderExpert(){return `<div class="grid cards2"><div class="card"><h2>Exports Europe</h2><div class="links">${(M.exports||[]).map(x=>`<a href="${esc(x.href)}">${esc(x.label)}</a>`).join('')}</div></div><div class="card"><h2>Contrat</h2><p class="muted">${esc(M.page_contract)}</p><p class="muted">Run ${esc(M.run_id)} · ${esc(M.generated_at)} · mode ${esc(M.data_mode)}</p></div></div><div class="section-title">JSON brut</div><pre>${esc(JSON.stringify(M,null,2))}</pre>`}
const BE_PROV={"type":"FeatureCollection","features":[{"type":"Feature","properties":{"province":"Flandre occidentale"},"geometry":{"type":"Polygon","coordinates":[[[2.55,50.72],[3.18,50.72],[3.32,51.12],[2.85,51.38],[2.55,51.15],[2.55,50.72]]]}},{"type":"Feature","properties":{"province":"Flandre orientale"},"geometry":{"type":"Polygon","coordinates":[[[3.18,50.72],[4.05,50.78],[4.18,51.25],[3.32,51.42],[3.18,50.72]]]}},{"type":"Feature","properties":{"province":"Anvers"},"geometry":{"type":"Polygon","coordinates":[[[4.05,51.02],[5.15,51.05],[5.35,51.48],[4.25,51.52],[4.05,51.02]]]}},{"type":"Feature","properties":{"province":"Limbourg"},"geometry":{"type":"Polygon","coordinates":[[[5.15,50.72],[5.98,50.74],[6.2,51.28],[5.35,51.48],[5.15,50.72]]]}},{"type":"Feature","properties":{"province":"Brabant flamand"},"geometry":{"type":"Polygon","coordinates":[[[4.05,50.72],[5.15,50.72],[5.15,51.05],[4.05,51.02],[4.05,50.72]]]}},{"type":"Feature","properties":{"province":"Bruxelles"},"geometry":{"type":"Polygon","coordinates":[[[4.25,50.77],[4.47,50.77],[4.47,50.93],[4.25,50.93],[4.25,50.77]]]}},{"type":"Feature","properties":{"province":"Brabant wallon"},"geometry":{"type":"Polygon","coordinates":[[[4.15,50.55],[4.9,50.55],[5.0,50.75],[4.15,50.75],[4.15,50.55]]]}},{"type":"Feature","properties":{"province":"Hainaut"},"geometry":{"type":"Polygon","coordinates":[[[2.85,49.88],[4.35,49.88],[4.45,50.55],[3.2,50.72],[2.75,50.35],[2.85,49.88]]]}},{"type":"Feature","properties":{"province":"Namur"},"geometry":{"type":"Polygon","coordinates":[[[4.35,49.88],[5.35,49.85],[5.45,50.55],[4.9,50.55],[4.15,50.55],[4.35,49.88]]]}},{"type":"Feature","properties":{"province":"Liège"},"geometry":{"type":"Polygon","coordinates":[[[5.35,49.98],[6.42,50.05],[6.22,50.78],[5.45,50.8],[5.35,49.98]]]}},{"type":"Feature","properties":{"province":"Luxembourg belge"},"geometry":{"type":"Polygon","coordinates":[[[4.98,49.45],[6.18,49.45],[6.42,50.05],[5.35,49.98],[4.98,49.45]]]}}]};
const RADAR_SITES=[["Wideumont (RMI/IRM)",49.914,5.504],["Jabbeke (RMI/IRM)",51.192,3.064],["Zaventem (RMI/IRM)",50.901,4.461],["Den Helder (KNMI)",52.955,4.790],["Herwijnen (KNMI)",51.837,5.138],["Abbeville (MF)",50.136,1.834],["Avesnois (MF)",50.128,3.808],["Nancy (MF)",48.716,6.581],["Essen (DWD)",51.406,6.967],["Neuheilenbach (DWD)",50.110,6.548],["Flechtdorf (DWD)",51.311,8.802],["Albis (MeteoSwiss)",47.284,8.512],["La Dôle (MeteoSwiss)",46.425,6.099],["Clee Hill (UKMO)",52.398,-2.595],["Madrid (AEMET)",40.169,-3.713],["Barcelona (AEMET)",41.408,1.883],["Roma (DPC)",41.940,12.470],["Milano (DPC)",45.470,9.180],["Legionowo (IMGW)",52.405,20.961],["Brdy (CHMI)",49.658,13.818],["Wien (ACG)",48.318,16.532]];
const REGIONS={
 europe:{label:"Europe (vue d ensemble)",center:[49.5,9],zoom:4,bbox:{w:-9,s:36,e:28,n:60},step:3.6,prov:false,stations:[["Bruxelles",50.85,4.35],["Paris",48.857,2.352],["Amsterdam",52.373,4.894],["Berlin",52.52,13.405],["Londres",51.507,-0.128],["Madrid",40.417,-3.704],["Barcelone",41.39,2.17],["Rome",41.903,12.496],["Milan",45.46,9.19],["Vienne",48.21,16.37],["Zurich",47.38,8.54],["Munich",48.14,11.58],["Lyon",45.76,4.84],["Marseille",43.30,5.37],["Hambourg",53.55,9.99],["Francfort",50.11,8.68],["Varsovie",52.23,21.01],["Prague",50.08,14.44],["Copenhague",55.68,12.57],["Dublin",53.35,-6.26],["Lisbonne",38.72,-9.14],["Genève",46.20,6.14],["Cologne",50.94,6.96],["Stuttgart",48.78,9.18]]},
 belgium:{label:"Belgique",center:[50.6,4.6],zoom:8,bbox:{w:2.55,s:49.45,e:6.35,n:51.55},step:0.34,prov:true,stations:[["Uccle / Bruxelles",50.799,4.358],["Jodoigne",50.724,4.870],["Namur",50.467,4.872],["Liège",50.633,5.580],["Charleroi",50.411,4.445],["Mons",50.454,3.957],["Gand",51.054,3.717],["Anvers",51.219,4.403],["Hasselt",50.931,5.333],["Arlon",49.683,5.817],["Coxyde",51.106,2.651],["Bruges",51.209,3.224],["Ostende",51.231,2.917],["Courtrai",50.828,3.265],["Alost",50.939,4.040],["Malines",51.028,4.480],["Louvain",50.879,4.701],["Wavre",50.717,4.607],["Nivelles",50.598,4.328],["La Louvière",50.479,4.187],["Tournai",50.607,3.389],["Dinant",50.258,4.912],["Marche",50.227,5.343],["Bastogne",50.0,5.717],["Verviers",50.589,5.862],["Eupen",50.630,6.039],["Genk",50.965,5.501],["Tongres",50.781,5.464],["Saint-Hubert",50.027,5.374],["Bouillon",49.793,5.067]]},
 france:{label:"France",center:[46.7,2.6],zoom:6,bbox:{w:-4.7,s:42.3,e:8.2,n:51.0},step:1.25,prov:false,stations:[["Paris",48.857,2.352],["Lille",50.629,3.057],["Reims",49.258,4.032],["Strasbourg",48.583,7.745],["Lyon",45.764,4.836],["Clermont-Fd",45.777,3.087],["Bordeaux",44.838,-0.579],["Toulouse",43.605,1.444],["Montpellier",43.611,3.877],["Marseille",43.297,5.370],["Nice",43.710,7.262],["Nantes",47.218,-1.554],["Rennes",48.117,-1.677],["Rouen",49.443,1.099],["Dijon",47.322,5.041],["Brest",48.390,-4.486]]},
 netherlands:{label:"Pays-Bas",center:[52.1,5.3],zoom:7,bbox:{w:3.3,s:50.7,e:7.3,n:53.6},step:0.55,prov:false,stations:[["Amsterdam",52.373,4.894],["Rotterdam",51.924,4.478],["La Haye",52.078,4.310],["Utrecht",52.091,5.121],["Eindhoven",51.442,5.470],["Maastricht",50.851,5.691],["Groningue",53.219,6.567],["Arnhem",51.985,5.899],["Breda",51.586,4.776],["Enschede",52.221,6.896],["Den Helder",52.959,4.760],["Vlissingen",51.443,3.574]]},
 germany:{label:"Allemagne",center:[51.0,10.3],zoom:6,bbox:{w:5.8,s:47.3,e:15.1,n:55.0},step:1.2,prov:false,stations:[["Berlin",52.52,13.405],["Hambourg",53.551,9.993],["Munich",48.137,11.576],["Cologne",50.938,6.960],["Francfort",50.110,8.682],["Stuttgart",48.776,9.183],["Düsseldorf",51.228,6.773],["Leipzig",51.339,12.378],["Dresde",51.050,13.738],["Nuremberg",49.452,11.077],["Hanovre",52.376,9.733],["Brême",53.079,8.802],["Aix-la-Chapelle",50.775,6.084],["Trèves",49.760,6.644],["Fribourg",47.999,7.842]]},
 alps:{label:"Suisse · Autriche · Alpes",center:[47.2,11.0],zoom:6,bbox:{w:5.9,s:45.6,e:17.2,n:49.1},step:1.1,prov:false,stations:[["Zurich",47.377,8.540],["Genève",46.204,6.143],["Bâle",47.560,7.588],["Berne",46.948,7.447],["Lugano",46.005,8.951],["Innsbruck",47.269,11.404],["Vienne",48.208,16.374],["Salzbourg",47.811,13.055],["Graz",47.071,15.439],["Milan",45.464,9.190],["Vérone",45.438,10.992]]},
 iberia:{label:"Espagne · Portugal",center:[40.0,-4.0],zoom:6,bbox:{w:-9.6,s:36.0,e:3.4,n:43.9},step:1.4,prov:false,stations:[["Madrid",40.417,-3.704],["Barcelone",41.390,2.170],["Valence",39.470,-0.376],["Séville",37.389,-5.984],["Bilbao",43.263,-2.935],["Saragosse",41.649,-0.889],["Malaga",36.721,-4.421],["Lisbonne",38.722,-9.139],["Porto",41.158,-8.629],["Murcie",37.987,-1.130],["Valladolid",41.652,-4.724]]},
 italy:{label:"Italie",center:[42.3,12.6],zoom:6,bbox:{w:6.5,s:36.6,e:18.6,n:47.1},step:1.25,prov:false,stations:[["Rome",41.903,12.496],["Milan",45.464,9.190],["Naples",40.852,14.268],["Turin",45.070,7.687],["Bologne",44.494,11.343],["Florence",43.770,11.256],["Venise",45.440,12.316],["Gênes",44.406,8.946],["Bari",41.118,16.871],["Palerme",38.116,13.361],["Cagliari",39.224,9.122]]},
 poland_cz:{label:"Pologne · Tchéquie",center:[51.2,17.5],zoom:6,bbox:{w:12.0,s:48.5,e:24.2,n:54.9},step:1.3,prov:false,stations:[["Varsovie",52.230,21.012],["Cracovie",50.065,19.945],["Wrocław",51.108,17.038],["Poznań",52.407,16.925],["Gdańsk",54.352,18.646],["Łódź",51.759,19.456],["Prague",50.075,14.437],["Brno",49.195,16.608],["Ostrava",49.820,18.263],["Katowice",50.270,19.039],["Szczecin",53.428,14.553]]},
 uk:{label:"Îles Britanniques",center:[53.5,-3.5],zoom:5,bbox:{w:-10.5,s:50.0,e:1.9,n:58.7},step:1.4,prov:false,stations:[["Londres",51.507,-0.128],["Birmingham",52.486,-1.890],["Manchester",53.481,-2.242],["Leeds",53.801,-1.549],["Glasgow",55.864,-4.252],["Édimbourg",55.953,-3.188],["Cardiff",51.481,-3.179],["Belfast",54.597,-5.930],["Dublin",53.350,-6.260],["Bristol",51.455,-2.587],["Plymouth",50.376,-4.143]]}
};
const CLASS=[{col:"--c-calm",name:"Stable",sub:"énergie faible, pas de signal de bascule"},{col:"--c-info",name:"Latent",sub:"l énergie s accumule, couvercle encore tenu"},{col:"--c-watch",name:"Transition",sub:"ingrédients réunis, fenêtre sensible"},{col:"--c-danger",name:"Bascule",sub:"déclenchement probable, surveiller le radar"}];
const mvClamp=v=>Math.max(0,Math.min(1,v));
const mvCss=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
function mvClassOf(r){return r<0.25?0:r<0.5?1:r<0.72?2:3;}
function mvColor(r){return mvCss(CLASS[mvClassOf(r)].col);}
function mvRisk(cape,cin,li,pp,gust){cape=cape||0;cin=cin||0;li=(li==null?4:li);pp=pp||0;gust=gust||0;const charge=mvClamp(cape/2500),liB=mvClamp((4-li)/14),energy=mvClamp(0.6*charge+0.4*liB),cap=mvClamp(1-cin/150),trig=mvClamp(0.55*(pp/100)+0.30*cap+0.15*mvClamp((gust-10)/25));return {r:mvClamp(energy*(0.45+0.55*trig)),trig};}
let MVMAP=null,MVbase=null,MVprov=null,MVsurf=null,MVsta=null,MVrad=null,MVsat=null,MVnet=null,MVbox=null;
let MVcanvas=null;const MVRV={host:"https://tilecache.rainviewer.com",radar:[],sat:[],pastCount:0};
let MVGRID=[],MVSTA=[],MVHOURS=[],MVi=0,MVregion="europe",MVstep=3.6,MVplay=null,MVbooted=false;
function mvBase(){return document.documentElement.dataset.theme==="light"?"https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png":"https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";}
function mvBusy(on,msg){const l=document.getElementById("mvLoading");if(l)l.classList.toggle("on",on);if(msg){const m=document.getElementById("mvLoadMsg");if(m)m.textContent=msg;}}
function mvGrid(b,step){const g=[];for(let la=b.s+step/2;la<b.n;la+=step)for(let lo=b.w+step/2;lo<b.e;lo+=step)g.push([+la.toFixed(3),+lo.toFixed(3)]);return g;}
function mvFrameFor(frames,i){if(!frames.length)return null;if(i===0)return frames[Math.max(0,MVRV.pastCount-1)]||frames[frames.length-1];const fc=frames.slice(MVRV.pastCount);if(fc.length)return fc[Math.min(fc.length-1,i-1)];return frames[frames.length-1];}
function mvShowRadar(){if(MVrad){MVMAP.removeLayer(MVrad);MVrad=null;}if(MVsat){MVMAP.removeLayer(MVsat);MVsat=null;}const cs=document.getElementById("mvL-sat"),cr=document.getElementById("mvL-rad");if(cs&&cs.checked&&MVRV.sat.length){const f=mvFrameFor(MVRV.sat,MVi);if(f)MVsat=L.tileLayer(MVRV.host+f.path+"/256/{z}/{x}/{y}/0/0_0.png",{opacity:.5,zIndex:350,attribution:"RainViewer"}).addTo(MVMAP);}if(cr&&cr.checked&&MVRV.radar.length){const f=mvFrameFor(MVRV.radar,MVi);if(f)MVrad=L.tileLayer(MVRV.host+f.path+"/256/{z}/{x}/{y}/2/1_1.png",{opacity:.66,zIndex:400,attribution:"RainViewer"}).addTo(MVMAP);}}
function mvLoadRV(){fetch("https://api.rainviewer.com/public/weather-maps.json",{cache:"no-store"}).then(r=>r.json()).then(d=>{MVRV.host=d.host||MVRV.host;const past=(d.radar&&d.radar.past)||[],now=(d.radar&&d.radar.nowcast)||[];MVRV.pastCount=past.length;MVRV.radar=past.concat(now);MVRV.sat=(d.satellite&&d.satellite.infrared)||[];mvShowRadar();}).catch(()=>{});}
function mvNetSites(){MVnet.clearLayers();RADAR_SITES.forEach(s=>{const m=L.circleMarker([s[1],s[2]],{renderer:MVcanvas,radius:5,weight:2,color:mvCss("--c-watch"),fillColor:"#fff",fillOpacity:.9});m.bindTooltip("📡 "+esc(s[0])+"<br><span style='color:var(--muted)'>site radar national · emplacement indicatif</span>",{direction:"top"});m.addTo(MVnet);});}
function mvBoxes(){MVbox.clearLayers();(M.countries||[]).forEach(c=>{const b=c.bbox||{};if(b.south==null)return;const col=c.machine_radar_available?mvCss("--c-calm"):mvCss("--c-watch");const rect=L.rectangle([[b.south,b.west],[b.north,b.east]],{color:col,weight:1.4,opacity:.7,fill:false});rect.bindPopup("<b>"+esc(c.label)+"</b><br>Priorité Belgique : "+esc(c.priority_for_belgium||"—")+"<br>Sources : "+esc(c.configured_source_count||0)+"/"+esc(c.source_count||0)+" prêtes<br>Preuve machine : "+(c.machine_radar_available?"oui":"non")+"<br><a href=\""+esc(c.country||"")+".html\">ouvrir la page pays</a>");rect.addTo(MVbox);});}
async function mvLoad(key){MVregion=key;const R=REGIONS[key];MVstep=R.step;mvBusy(true,"Lecture des indices convectifs…");MVMAP.setView(R.center,R.zoom);if(MVprov){MVMAP.removeLayer(MVprov);if(R.prov)MVprov.addTo(MVMAP);}let grid=mvGrid(R.bbox,R.step);MVSTA=R.stations.map(s=>({name:s[0],lat:s[1],lon:s[2]}));const cap=Math.max(8,92-MVSTA.length);if(grid.length>cap){const k=Math.ceil(grid.length/cap);grid=grid.filter((_,i)=>i%k===0);}MVGRID=grid;const pts=MVGRID.concat(MVSTA.map(s=>[s.lat,s.lon]));const url="https://api.open-meteo.com/v1/forecast?latitude="+pts.map(p=>p[0]).join(",")+"&longitude="+pts.map(p=>p[1]).join(",")+"&hourly=cape,convective_inhibition,lifted_index,precipitation_probability,wind_gusts_10m&forecast_days=2&timezone=auto";try{const data=await(await fetch(url,{cache:"no-store"})).json();const arr=Array.isArray(data)?data:[data];const t=arr[0].hourly.time;const nowIso=new Date().toISOString().slice(0,13);let start=t.findIndex(x=>x.slice(0,13)>=nowIso);if(start<0)start=0;MVHOURS=t.slice(start,start+18);const slot=o=>({cape:o.hourly.cape,cin:o.hourly.convective_inhibition,li:o.hourly.lifted_index,pp:o.hourly.precipitation_probability,gust:o.hourly.wind_gusts_10m,off:start});MVGRID.forEach((p,i)=>{p[2]=slot(arr[i]);});MVSTA.forEach((s,i)=>s.d=slot(arr[MVGRID.length+i]));const sl=document.getElementById("mvTime");sl.max=MVHOURS.length-1;MVi=0;sl.value=0;mvRender();mvBusy(false);}catch(e){mvBusy(false);const r=document.getElementById("mvReg");if(r)r.textContent="Indices indisponibles";const s=document.getElementById("mvSub");if(s)s.textContent="réseau Open-Meteo injoignable";}}
function mvAt(slot,i){const o=slot.off+i;return mvRisk(slot.cape[o],slot.cin[o],slot.li[o],slot.pp[o],slot.gust[o]);}
function mvVals(slot,i){const o=slot.off+i;return {cape:slot.cape[o]||0,cin:slot.cin[o]||0,li:slot.li[o],pp:slot.pp[o]||0,gust:slot.gust[o]||0,...mvAt(slot,i)};}
function mvRender(){const i=MVi,iso=MVHOURS[i]||"",dt=new Date(iso);const hh=isNaN(dt)?iso:dt.toLocaleString("fr-BE",{weekday:"short",hour:"2-digit",minute:"2-digit"});const tl=document.getElementById("mvTlabel");if(tl)tl.innerHTML=i===0?"<b>maintenant</b>":"+"+i+" h · "+hh;
 MVsurf.clearLayers();const surfOn=document.getElementById("mvL-surf").checked,h=MVstep/2;if(surfOn)MVGRID.forEach(p=>{const r=mvAt(p[2],i).r;L.rectangle([[p[0]-h,p[1]-h],[p[0]+h,p[1]+h]],{renderer:MVcanvas,stroke:false,fillColor:mvColor(r),fillOpacity:0.10+0.5*r}).addTo(MVsurf);});
 MVsta.clearLayers();const staOn=document.getElementById("mvL-sta").checked,ranked=[];MVSTA.forEach(s=>{const d=mvVals(s.d,i);ranked.push({name:s.name,r:d.r});if(staOn){const m=L.circleMarker([s.lat,s.lon],{renderer:MVcanvas,radius:6,weight:2.5,color:mvColor(d.r),fillColor:"#fff",fillOpacity:.95});m.bindTooltip("<b>"+esc(s.name)+"</b><br>bascule "+d.r.toFixed(2)+" · "+CLASS[mvClassOf(d.r)].name+"<br>CAPE "+Math.round(d.cape)+" J/kg · LI "+(d.li==null?"—":d.li.toFixed(1))+"<br>pluie "+d.pp+"% · rafales "+Math.round(d.gust)+" km/h",{direction:"top"});m.addTo(MVsta);}});
 mvShowRadar();
 const rs=MVGRID.map(p=>mvAt(p[2],i).r);const agg=rs.length?Math.max(...rs)*0.6+(rs.reduce((a,b)=>a+b,0)/rs.length)*0.4:0;const arc=document.getElementById("mvArc");if(arc){arc.style.strokeDashoffset=(226*(1-agg)).toFixed(1);arc.setAttribute("stroke",mvColor(agg));}document.getElementById("mvVal").textContent=agg.toFixed(2);const c=CLASS[mvClassOf(agg)];document.getElementById("mvReg").textContent=REGIONS[MVregion].label+" — "+c.name;document.getElementById("mvSub").textContent=c.sub;document.getElementById("mvCur").style.left=(agg*100)+"%";
 const vs=MVGRID.map(p=>mvVals(p[2],i)),mean=k=>vs.length?vs.reduce((a,b)=>a+(b[k]||0),0)/vs.length:0;document.getElementById("mvCape").textContent=Math.round(mean("cape"));document.getElementById("mvCin").textContent=Math.round(mean("cin"));const li=mean("li");document.getElementById("mvLi").textContent=isFinite(li)?li.toFixed(1):"—";document.getElementById("mvTrig").textContent=(mean("trig")*100|0)+"%";
 ranked.sort((a,b)=>b.r-a.r);document.getElementById("mvHot").innerHTML=ranked.slice(0,6).map(x=>'<div class="r"><span class="sw" style="background:'+mvColor(x.r)+'"></span><span class="nm">'+esc(x.name)+'</span><span class="sc">'+x.r.toFixed(2)+'</span></div>').join("")||'<div class="r"><span class="nm" style="color:var(--muted)">—</span></div>';}
function mvPlayToggle(){const sl=document.getElementById("mvTime"),btn=document.getElementById("mvPlay");if(MVplay){clearInterval(MVplay);MVplay=null;btn.innerHTML="&#9654;";return;}btn.innerHTML="&#10074;&#10074;";MVplay=setInterval(()=>{MVi=(MVi+1)%(MVHOURS.length||1);sl.value=MVi;mvRender();},900);}
function initEuropeMap(){const target=document.getElementById("europeMap");if(!target)return;if(typeof L==="undefined"){mvBusy(true,"Leaflet indisponible · vérifier le CDN");return;}
 if(!MVbooted){MVbooted=true;MVcanvas=L.canvas({padding:.5});MVMAP=L.map(target,{zoomControl:true,preferCanvas:true,worldCopyJump:true});MVbase=L.tileLayer(mvBase(),{subdomains:"abcd",maxZoom:19,attribution:"&copy; OpenStreetMap &copy; CARTO"}).addTo(MVMAP);MVsurf=L.layerGroup().addTo(MVMAP);MVsta=L.layerGroup().addTo(MVMAP);MVnet=L.layerGroup();MVbox=L.layerGroup().addTo(MVMAP);MVprov=L.geoJSON(BE_PROV,{style:{color:mvCss("--muted"),weight:1,opacity:.55,dashArray:"3 4",fill:false}});
  const sel=document.getElementById("mvRegion");Object.entries(REGIONS).forEach(([k,v])=>{const o=document.createElement("option");o.value=k;o.textContent=v.label;sel.appendChild(o);});sel.value="europe";sel.addEventListener("change",()=>{if(MVplay)mvPlayToggle();mvLoad(sel.value);});
  document.getElementById("mvTime").addEventListener("input",e=>{MVi=+e.target.value;mvRender();});
  document.getElementById("mvPlay").addEventListener("click",mvPlayToggle);
  ["mvL-surf","mvL-sta"].forEach(id=>document.getElementById(id).addEventListener("change",mvRender));
  document.getElementById("mvL-rad").addEventListener("change",mvShowRadar);
  document.getElementById("mvL-sat").addEventListener("change",mvShowRadar);
  document.getElementById("mvL-net").addEventListener("change",e=>{if(e.target.checked){mvNetSites();MVnet.addTo(MVMAP);}else MVMAP.removeLayer(MVnet);});
  document.getElementById("mvL-box").addEventListener("change",e=>{if(e.target.checked){mvBoxes();MVbox.addTo(MVMAP);}else MVMAP.removeLayer(MVbox);});
  mvBoxes();mvLoadRV();mvLoad("europe");
 }
 setTimeout(()=>{try{MVMAP.invalidateSize();}catch(e){}},120);}
function paint(){document.getElementById('stamp').textContent=M.generated_at||'n/a';document.getElementById('view-simple').innerHTML=renderSimple();document.getElementById('view-operational').innerHTML=renderOperational();document.getElementById('view-radar').innerHTML=renderRadar();document.getElementById('view-countries').innerHTML=renderCountries();document.getElementById('view-corridors').innerHTML=renderCorridors();document.getElementById('view-sources').innerHTML=renderSources();document.getElementById('view-expert').innerHTML=renderExpert();document.getElementById('foot').innerHTML=`MeteoVoid Europe · ${esc(M.generated_at||'')} · <a href="index.html">Belgique</a> · <a href="api/europe.json">API Europe</a>`}
document.querySelectorAll('.tab[data-view]').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));b.classList.add('active');document.querySelectorAll('.view').forEach(v=>v.classList.toggle('active',v.id==='view-'+b.dataset.view));if(b.dataset.view==='radar')setTimeout(initEuropeMap,80);scrollTo({top:0,behavior:'smooth'})}));document.getElementById('theme').onclick=()=>{document.documentElement.dataset.theme=document.documentElement.dataset.theme==='dark'?'light':'dark'};paint();
</script>
</body>
</html>"""


def _write_europe_page(site_dir: Path, model: dict[str, Any]) -> None:
    bootstrap = json.dumps(model, ensure_ascii=False).replace("</", "<\\/")
    page = EUROPE_MAX_TEMPLATE.replace("__EUROPE_BOOTSTRAP__", bootstrap)
    (site_dir / "europe.html").write_text(page, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the three-level MeteoVoid Belgium public site and JSON API."
    )
    parser.add_argument("--report-dir", required=True, type=Path)
    parser.add_argument("--site-dir", required=True, type=Path)
    parser.add_argument("--live-smoke-dir", required=False, type=Path, default=None)
    parser.add_argument("--opera-ord-dir", required=False, type=Path, default=None)
    args = parser.parse_args()
    build_index(args.report_dir, args.site_dir, args.live_smoke_dir, args.opera_ord_dir)


if __name__ == "__main__":
    main()
