"""Open-Meteo multi-model comparison contracts for MeteoVoid.

The direct GRIB pipelines for ECMWF, AROME and ICON are intentionally not run
from the static site build. This module exposes the lightweight Open-Meteo
connection layer first, plus an explicit roadmap for future GRIB ingestion.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

OPEN_METEO_MODELS: list[dict[str, Any]] = [
    {
        "id": "best_match",
        "label": "Open-Meteo best match",
        "family": "open_meteo",
        "provider": "Open-Meteo",
        "endpoint": "https://api.open-meteo.com/v1/forecast",
        "model": "best_match",
        "status": "active_browser_fetch",
        "role": "socle Europe et repli général",
    },
    {
        "id": "ecmwf_ifs025",
        "label": "ECMWF IFS 0.25°",
        "family": "ecmwf",
        "provider": "ECMWF via Open-Meteo",
        "endpoint": "https://api.open-meteo.com/v1/ecmwf",
        "model": "ecmwf_ifs025",
        "status": "active_browser_fetch",
        "role": "modèle global synoptique",
    },
    {
        "id": "ecmwf_aifs025",
        "label": "ECMWF AIFS 0.25°",
        "family": "ecmwf",
        "provider": "ECMWF via Open-Meteo",
        "endpoint": "https://api.open-meteo.com/v1/ecmwf",
        "model": "ecmwf_aifs025",
        "status": "candidate_browser_fetch",
        "role": "comparaison IA / global",
    },
    {
        "id": "meteofrance_arome_france",
        "label": "Météo-France AROME",
        "family": "arome",
        "provider": "Météo-France via Open-Meteo",
        "endpoint": "https://api.open-meteo.com/v1/meteofrance",
        "model": "meteofrance_arome_france",
        "status": "active_browser_fetch",
        "role": "maillage fin France / amont Belgique",
    },
    {
        "id": "meteofrance_arpege_europe",
        "label": "Météo-France ARPEGE Europe",
        "family": "arome",
        "provider": "Météo-France via Open-Meteo",
        "endpoint": "https://api.open-meteo.com/v1/meteofrance",
        "model": "meteofrance_arpege_europe",
        "status": "active_browser_fetch",
        "role": "Europe occidentale, contexte large",
    },
    {
        "id": "dwd_icon_eu",
        "label": "DWD ICON-EU",
        "family": "icon",
        "provider": "DWD via Open-Meteo",
        "endpoint": "https://api.open-meteo.com/v1/dwd-icon",
        "model": "icon_eu",
        "status": "active_browser_fetch",
        "role": "Europe centrale et Benelux",
    },
    {
        "id": "dwd_icon_d2",
        "label": "DWD ICON-D2",
        "family": "icon",
        "provider": "DWD via Open-Meteo",
        "endpoint": "https://api.open-meteo.com/v1/dwd-icon",
        "model": "icon_d2",
        "status": "candidate_browser_fetch",
        "role": "haute résolution zone DWD si disponible",
    },
]

GRIB_DIRECT_ROADMAP: list[dict[str, str]] = [
    {
        "id": "ecmwf_grib_direct",
        "label": "ECMWF Open Data GRIB2",
        "status": "future_backend_pipeline",
        "next_step": "télécharger run récent, extraire Belgique/Europe, convertir en JSON compact",
    },
    {
        "id": "arome_grib_direct",
        "label": "Météo-France AROME GRIB2",
        "status": "future_backend_pipeline",
        "next_step": (
            "ajouter credentials/open-data si requis, extraire variables convectives, "
            "produire grille locale"
        ),
    },
    {
        "id": "icon_grib_direct",
        "label": "DWD ICON / ICON-EU GRIB2",
        "status": "future_backend_pipeline",
        "next_step": "récupérer DWD open data, décoder GRIB, comparer avec Open-Meteo ICON",
    },
]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _num(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def _clamp01(value: Any) -> float:
    return max(0.0, min(1.0, _num(value)))


def _base_score_from_map_live(map_live: dict[str, Any] | None) -> float | None:
    if not map_live:
        return None
    hours = map_live.get("hours")
    if isinstance(hours, list) and hours:
        first = hours[0]
        if isinstance(first, dict):
            for key in ("score", "mean_score", "max_score"):
                if first.get(key) is not None:
                    return _clamp01(first.get(key))
    stations = map_live.get("stations")
    if isinstance(stations, list) and stations:
        vals = [_clamp01(item.get("score")) for item in stations if isinstance(item, dict)]
        if vals:
            return sum(vals) / len(vals)
    return None


def _synthetic_score(model_id: str, base: float | None) -> float:
    """Deterministic CI fallback, not a forecast.

    The browser panel replaces this with live Open-Meteo fetches when the site is
    served with network access. Keeping a deterministic fallback makes static CI
    builds auditable and prevents empty panels.
    """
    baseline = 0.38 if base is None else _clamp01(base)
    offsets = {
        "best_match": 0.00,
        "ecmwf_ifs025": -0.06,
        "ecmwf_aifs025": -0.02,
        "meteofrance_arome_france": 0.08,
        "meteofrance_arpege_europe": 0.02,
        "dwd_icon_eu": 0.05,
        "dwd_icon_d2": 0.10,
    }
    return round(_clamp01(baseline + offsets.get(model_id, 0.0)), 3)


def _agreement(scores: list[float]) -> dict[str, Any]:
    if not scores:
        return {"mean": None, "spread": None, "label": "non disponible"}
    mean = sum(scores) / len(scores)
    spread = max(scores) - min(scores) if len(scores) > 1 else 0.0
    if spread <= 0.12:
        label = "accord fort"
    elif spread <= 0.28:
        label = "accord partiel"
    else:
        label = "désaccord marqué"
    return {"mean": round(mean, 3), "spread": round(spread, 3), "label": label}


def build_model_compare_api(
    map_live: dict[str, Any] | None = None,
    *,
    generated_at: str | None = None,
    region: str = "belgium",
) -> dict[str, Any]:
    base = _base_score_from_map_live(map_live)
    models: list[dict[str, Any]] = []
    for item in OPEN_METEO_MODELS:
        score = _synthetic_score(str(item["id"]), base)
        models.append(
            {
                **item,
                "fallback_score": score,
                "live_score": None,
                "score_source": "static_ci_fallback_until_browser_fetch",
            }
        )
    scores = [float(item["fallback_score"]) for item in models]
    aggressive = max(models, key=lambda item: float(item["fallback_score"])) if models else None
    conservative = min(models, key=lambda item: float(item["fallback_score"])) if models else None
    return {
        "contract": "meteovoid_open_meteo_model_compare_v1",
        "generated_at": generated_at or _now_iso(),
        "region": region,
        "center": {"lat": 50.64, "lon": 4.67, "label": "Belgique"},
        "strategy": (
            "Open-Meteo multi-modèles en premier; GRIB direct ECMWF/AROME/ICON "
            "plus tard côté backend."
        ),
        "variables": [
            "cape",
            "convective_inhibition",
            "lifted_index",
            "precipitation_probability",
            "wind_gusts_10m",
        ],
        "models": models,
        "agreement": _agreement(scores),
        "most_aggressive": aggressive and aggressive["id"],
        "most_conservative": conservative and conservative["id"],
        "grib_direct_roadmap": GRIB_DIRECT_ROADMAP,
        "limits": [
            "Les scores statiques servent de repli CI, pas de prévision officielle.",
            (
                "Le panneau navigateur remplace ces scores par les fetchs Open-Meteo "
                "quand le réseau est disponible."
            ),
            (
                "Les connexions GRIB directes restent séparées pour éviter de charger "
                "la CI avec du GRIB2."
            ),
        ],
    }
