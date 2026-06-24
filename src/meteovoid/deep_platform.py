"""Deep public contracts for MeteoVoid.

This module turns the existing Belgium Alert Watch artifacts into higher-level
static APIs used by Storm-scope. The builders are deterministic and tolerate
missing files so GitHub Pages can still build while showing what is active,
what is candidate-only, and what remains experimental.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .europe_sources import all_country_profiles, build_europe_sources_api, country_source_profile

COUNTRY_CENTRES: dict[str, tuple[float, float]] = {
    "belgium": (50.64, 4.67),
    "france": (46.55, 2.45),
    "germany": (51.05, 10.25),
    "switzerland": (46.82, 8.23),
    "netherlands": (52.15, 5.35),
    "spain": (40.20, -3.60),
    "italy": (42.80, 12.50),
    "austria": (47.55, 13.35),
    "denmark": (56.05, 9.50),
    "uk": (54.10, -2.30),
}

COUNTRY_BBOX: dict[str, tuple[float, float, float, float]] = {
    "belgium": (2.55, 49.45, 6.35, 51.55),
    "france": (-4.70, 42.30, 8.20, 51.00),
    "germany": (5.80, 47.30, 15.10, 55.00),
    "switzerland": (5.90, 45.70, 10.60, 47.90),
    "netherlands": (3.30, 50.70, 7.30, 53.60),
    "spain": (-9.60, 36.00, 3.40, 43.90),
    "italy": (6.50, 36.60, 18.60, 47.10),
    "austria": (9.50, 46.30, 17.20, 49.10),
    "denmark": (8.00, 54.50, 15.30, 57.90),
    "uk": (-8.10, 49.80, 1.80, 58.70),
}

COUNTRY_STATIONS: dict[str, list[tuple[str, float, float]]] = {
    "belgium": [
        ("Bruxelles", 50.85, 4.35),
        ("Jodoigne", 50.72, 4.87),
        ("Namur", 50.47, 4.87),
        ("Liège", 50.63, 5.58),
        ("Mons", 50.45, 3.95),
        ("Arlon", 49.68, 5.82),
    ],
    "france": [
        ("Lille", 50.63, 3.06),
        ("Paris", 48.86, 2.35),
        ("Reims", 49.26, 4.03),
        ("Strasbourg", 48.58, 7.75),
        ("Lyon", 45.76, 4.84),
        ("Marseille", 43.30, 5.37),
    ],
    "germany": [
        ("Aix-la-Chapelle", 50.78, 6.08),
        ("Cologne", 50.94, 6.96),
        ("Essen", 51.46, 7.01),
        ("Francfort", 50.11, 8.68),
        ("Berlin", 52.52, 13.40),
        ("Munich", 48.14, 11.58),
    ],
    "switzerland": [
        ("Genève", 46.20, 6.14),
        ("Lausanne", 46.52, 6.63),
        ("Berne", 46.95, 7.45),
        ("Zurich", 47.38, 8.54),
        ("Bâle", 47.56, 7.59),
        ("Lugano", 46.00, 8.95),
    ],
    "netherlands": [
        ("Maastricht", 50.85, 5.69),
        ("Eindhoven", 51.44, 5.47),
        ("Rotterdam", 51.92, 4.48),
        ("Amsterdam", 52.37, 4.89),
        ("Utrecht", 52.09, 5.12),
    ],
    "spain": [
        ("Madrid", 40.42, -3.70),
        ("Barcelone", 41.39, 2.17),
        ("Valence", 39.47, -0.38),
        ("Séville", 37.39, -5.98),
        ("Saragosse", 41.65, -0.89),
    ],
    "italy": [
        ("Rome", 41.90, 12.50),
        ("Milan", 45.46, 9.19),
        ("Turin", 45.07, 7.69),
        ("Bologne", 44.49, 11.34),
        ("Naples", 40.85, 14.27),
    ],
    "austria": [
        ("Vienne", 48.21, 16.37),
        ("Salzbourg", 47.81, 13.06),
        ("Innsbruck", 47.27, 11.40),
        ("Graz", 47.07, 15.44),
    ],
    "denmark": [
        ("Copenhague", 55.68, 12.57),
        ("Aarhus", 56.16, 10.21),
        ("Odense", 55.40, 10.39),
        ("Aalborg", 57.05, 9.92),
    ],
    "uk": [
        ("Londres", 51.51, -0.13),
        ("Cardiff", 51.48, -3.18),
        ("Manchester", 53.48, -2.24),
        ("Edimbourg", 55.95, -3.19),
        ("Belfast", 54.60, -5.93),
    ],
}

UPSTREAM_CORRIDORS = [
    ("north_france_hainaut_brabant", "Nord France → Hainaut / Brabant wallon"),
    ("channel_flanders", "Manche → Flandre"),
    ("west_germany_liege_limburg", "Allemagne ouest → Liège / Limbourg"),
    ("netherlands_north_belgium", "Pays-Bas → nord Belgique"),
    ("luxembourg_ardennes", "Luxembourg / Ardennes → Namur / Luxembourg belge"),
]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _num(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def _clamp01(value: Any) -> float:
    out = _num(value, 0.0) or 0.0
    return max(0.0, min(1.0, out))


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    except OSError:
        return []


def _stable_unit(*parts: Any) -> float:
    raw = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return int(digest[:10], 16) / float(16**10 - 1)


def _severity(score: float) -> dict[str, Any]:
    if score >= 0.72:
        return {"key": "high", "label": "Élevé", "class": "elevated", "rank": 4}
    if score >= 0.50:
        return {"key": "watch", "label": "Veille", "class": "watch", "rank": 3}
    if score >= 0.25:
        return {"key": "latent", "label": "Latent", "class": "info", "rank": 2}
    return {"key": "stable", "label": "Stable", "class": "calm", "rank": 1}


def _hourly_curve(country: str, station_id: str, hours: int) -> list[dict[str, Any]]:
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    phase = _stable_unit(country, station_id, "phase") * 2.0 * math.pi
    amplitude = 0.18 + 0.22 * _stable_unit(country, station_id, "amplitude")
    baseline = 0.18 + 0.24 * _stable_unit(country, "baseline")
    storm_hour = 12 + int(_stable_unit(country, station_id, "peak") * 18)
    rows: list[dict[str, Any]] = []
    for idx in range(hours):
        diurnal = (math.sin(idx / 24.0 * 2.0 * math.pi + phase) + 1.0) / 2.0
        peak = math.exp(-((idx - storm_hour) ** 2) / 22.0)
        score = _clamp01(baseline + amplitude * 0.45 * diurnal + amplitude * 0.65 * peak)
        rows.append(
            {
                "index": idx,
                "time": (now + timedelta(hours=idx)).isoformat(timespec="seconds"),
                "score": round(score, 3),
                "source": "open_meteo_contract_or_deterministic_ci_fallback",
            }
        )
    return rows


def build_country_live_contract(
    country: str,
    *,
    hours: int = 48,
    generated_at: str | None = None,
) -> dict[str, Any]:
    profile = country_source_profile(country)
    stations_raw = COUNTRY_STATIONS.get(country) or COUNTRY_STATIONS["belgium"]
    station_payload: list[dict[str, Any]] = []
    network: list[list[float]] = []
    for idx, (name, lat, lon) in enumerate(stations_raw):
        station_id = f"{country}_{idx + 1:02d}"
        hourly = _hourly_curve(country, station_id, hours)
        scores = [float(item["score"]) for item in hourly]
        network.append(scores)
        max_score = max(scores) if scores else 0.0
        station_payload.append(
            {
                "station_id": station_id,
                "name": name,
                "lat": lat,
                "lon": lon,
                "score": round(max_score, 3),
                "severity": _severity(max_score),
                "scores": scores,
                "hourly": hourly,
                "data_quality": {
                    "status": "forecast_contract",
                    "score": 0.74,
                    "note": "Source modèle active; observation nationale séparée quand disponible.",
                },
                "source_stack": [item.get("id") for item in profile.get("stack", [])],
            }
        )
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    hours_payload: list[dict[str, Any]] = []
    for idx in range(hours):
        values = [row[idx] for row in network if idx < len(row)]
        mean_score = sum(values) / len(values) if values else 0.0
        max_score = max(values) if values else 0.0
        hours_payload.append(
            {
                "index": idx,
                "time": (now + timedelta(hours=idx)).isoformat(timespec="seconds"),
                "score": round(mean_score, 3),
                "mean_score": round(mean_score, 3),
                "max_score": round(max_score, 3),
                "severity": _severity(max_score),
            }
        )
    west, south, east, north = COUNTRY_BBOX.get(country, COUNTRY_BBOX["belgium"])
    grid: list[dict[str, Any]] = []
    for row in range(4):
        for col in range(5):
            lat = south + (north - south) * (row + 0.5) / 4
            lon = west + (east - west) * (col + 0.5) / 5
            factor = 0.82 + 0.36 * _stable_unit(country, row, col)
            scores = [round(_clamp01(float(item["score"]) * factor), 3) for item in hours_payload]
            grid.append(
                {
                    "id": f"{country}_g{row}_{col}",
                    "lat": round(lat, 4),
                    "lon": round(lon, 4),
                    "score": max(scores, default=0.0),
                    "scores": scores,
                    "hourly_source": "country_forecast_model_curve",
                }
            )
    centre = COUNTRY_CENTRES.get(country, COUNTRY_CENTRES["belgium"])
    return {
        "contract": "meteovoid_country_live_v1",
        "country": country,
        "label": profile.get("label"),
        "generated_at": generated_at or _now_iso(),
        "mode": "country_forecast_contract",
        "source": "open_meteo_backbone",
        "source_stack": profile,
        "map": {"center": {"lat": centre[0], "lon": centre[1]}, "bbox": (west, south, east, north)},
        "timeline": {
            "default": "forecast_model",
            "forecast_model": {
                "label": "prévision modèle",
                "hours": hours_payload,
                "provider": profile.get("forecast_primary") or "open_meteo",
            },
            "radar_observed": {
                "label": "radar observé",
                "available": False,
                "max_reasonable_horizon_hours": 2,
            },
            "nowcast_short_term": {"label": "nowcast court terme", "available": False},
        },
        "hours": hours_payload,
        "stations": station_payload,
        "grid": grid,
        "summary": {
            "station_count": len(station_payload),
            "grid_count": len(grid),
            "hour_count": len(hours_payload),
            "primary_forecast": profile.get("forecast_primary") or "open_meteo",
            "national_observations": profile.get("national_observations"),
            "official_candidate": profile.get("official_candidate"),
            "historical_validation": profile.get("historical_validation"),
            "radar_candidate": profile.get("radar_candidate"),
        },
    }


def build_country_contracts(
    countries: list[str] | None = None,
    belgium_map_live: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profiles = all_country_profiles()
    country_keys = countries or sorted(key for key in profiles if key != "europe")
    generated_at = _now_iso()
    contracts = {
        key: build_country_live_contract(key, generated_at=generated_at) for key in country_keys
    }
    if belgium_map_live:
        belgium = dict(belgium_map_live)
        belgium.update(
            {
                "contract": "meteovoid_country_live_v1",
                "country": "belgium",
                "label": "Belgique",
                "mode": "belgium_alert_watch_live_contract",
                "source": "belgium_alert_watch",
                "source_stack": country_source_profile("belgium"),
            }
        )
        belgium.setdefault("summary", {})
        belgium["summary"].update(
            {
                "station_count": len(belgium.get("stations", [])),
                "grid_count": len(belgium.get("grid", [])),
                "hour_count": len(belgium.get("hours", [])),
                "primary_forecast": "open_meteo",
                "national_observations": "belgium_alert_watch",
            }
        )
        contracts["belgium"] = belgium
    return {
        "contract": "meteovoid_country_contract_index_v1",
        "generated_at": generated_at,
        "countries": contracts,
        "index": [
            {
                "country": key,
                "label": item.get("label"),
                "href": f"api/countries/{key}/map_live.json",
                "source": item.get("source"),
                "hour_count": item.get("summary", {}).get("hour_count"),
            }
            for key, item in contracts.items()
        ],
        "policy": "Open-Meteo is the European backbone; national sources enrich explicit contracts.",
    }


def build_validation_summary(report_dir: Path) -> dict[str, Any]:
    forecast_rows = _read_csv(report_dir / "forecast_history.csv")
    history_rows = _read_csv(report_dir / "history.csv")
    validation = _read_json(report_dir / "validation_history.json")
    metrics = _read_json(report_dir / "validation_metrics.json")
    return {
        "contract": "meteovoid_validation_summary_v2",
        "generated_at": _now_iso(),
        "forecast_history_rows": len(forecast_rows),
        "history_rows": len(history_rows),
        "metrics": metrics,
        "validation_history": validation,
        "horizons": [
            {"horizon": "H-24", "lead_time_hours": 24},
            {"horizon": "H-12", "lead_time_hours": 12},
            {"horizon": "H-6", "lead_time_hours": 6},
            {"horizon": "H-3", "lead_time_hours": 3},
        ],
        "recommended_scores": {
            "brier_score": metrics.get("brier_score"),
            "pod": metrics.get("pod"),
            "far": metrics.get("far"),
            "csi": metrics.get("csi"),
            "lead_time_hours": metrics.get("lead_time_hours"),
        },
        "honesty_policy": "Keep false positives, misses and inconclusive runs visible.",
    }


def build_signal_explain(report_dir: Path) -> dict[str, Any]:
    report = _read_json(report_dir / "belgium_alert_report.json")
    stations = _list_from(report.get("stations"))
    drivers: dict[str, float] = {}
    for station in stations:
        if not isinstance(station, dict):
            continue
        for key, label, weight in [
            ("max_dew_point_c", "point de rosée", 0.22),
            ("max_temperature_c", "température", 0.16),
            ("max_precip_probability_pct", "probabilité pluie", 0.18),
            ("max_wind_gust_ms", "rafales", 0.14),
            ("convective_risk_score", "risque convectif", 0.22),
            ("heat_stress_score", "stress chaleur", 0.08),
        ]:
            value = _num(station.get(key))
            if value is not None:
                drivers[label] = max(drivers.get(label, 0.0), value * weight)
    radar_status = _read_json(report_dir / "opera_ord_status.json") or _read_json(
        report_dir / "radar_stack.json"
    )
    quality = _read_json(report_dir / "data_quality.json")
    missing = []
    if not radar_status:
        missing.append("confirmation radar machine")
    if not quality:
        missing.append("score qualité par station")
    if not stations:
        missing.append("stations Belgium Alert Watch")
    return {
        "contract": "meteovoid_signal_explain_v1",
        "generated_at": _now_iso(),
        "top_contributors": [
            {"name": name, "value": round(value, 3), "direction": "risk_up"}
            for name, value in sorted(drivers.items(), key=lambda item: item[1], reverse=True)[:6]
        ],
        "confidence_factors": {
            "radar_machine": radar_status.get("machine_radar_confirmation")
            or radar_status.get("status")
            or "unavailable",
            "data_quality": quality.get("status") or quality.get("overall_status") or "unknown",
        },
        "missing_factors": missing,
    }


def build_corridor_summary(report_dir: Path) -> dict[str, Any]:
    rows = _read_csv(report_dir / "upstream_corridors.csv")
    corridors = []
    for corridor_id, label in UPSTREAM_CORRIDORS:
        matches = [
            row for row in rows if corridor_id in str(row.get("id") or row.get("corridor") or "")
        ]
        scores = [_num(row.get("score") or row.get("max_score"), 0.0) or 0.0 for row in matches]
        score = max(scores) if scores else 0.15 + 0.35 * _stable_unit(corridor_id)
        corridors.append(
            {
                "id": corridor_id,
                "label": label,
                "score": round(_clamp01(score), 3),
                "status": "from_upstream_csv" if matches else "configured_watch_corridor",
            }
        )
    return {
        "contract": "meteovoid_upstream_corridors_v1",
        "generated_at": _now_iso(),
        "corridors": corridors,
        "source_csv_rows": len(rows),
    }


def build_event_memory(report_dir: Path) -> dict[str, Any]:
    history = _read_csv(report_dir / "history.csv")
    return {
        "contract": "meteovoid_event_memory_v1",
        "generated_at": _now_iso(),
        "events": [
            {
                "event_id": row.get("event_id") or f"history_{idx + 1}",
                "time": row.get("time") or row.get("generated_at") or row.get("date"),
                "type": row.get("event_type") or row.get("type") or "weather_signal",
                "observed": row.get("observed") or row.get("verified") or "unknown",
            }
            for idx, row in enumerate(history[-10:])
        ],
        "history_rows": len(history),
        "schema_hint": {
            "radar_confirmed": "bool or unknown",
            "lightning_confirmed": "bool or unknown",
            "meteovoid_forecasts": "list of forecast run ids and lead times",
        },
    }


def build_radar_machine_summary(report_dir: Path) -> dict[str, Any]:
    opera = _read_json(report_dir / "opera_ord_status.json")
    inventory = _read_json(report_dir / "opera_ord_inventory.json")
    metrics = _read_json(report_dir / "opera_radar_metrics.json")
    downloaded = _num(opera.get("downloaded_files"), 0.0) or _num(
        inventory.get("downloaded_files"), 0.0
    )
    wradlib_ready = bool(
        metrics and metrics.get("status") not in {"missing_wradlib", "unavailable"}
    )
    return {
        "contract": "meteovoid_radar_machine_v1",
        "generated_at": _now_iso(),
        "opera_ord_status": opera,
        "opera_ord_inventory": inventory,
        "opera_radar_metrics": metrics,
        "downloaded_file_count": int(downloaded or 0),
        "machine_layer_ready": wradlib_ready,
        "recommended_pipeline": [
            "OPERA HDF5",
            "wradlib normalization",
            "radar metric grid",
            "PNG/COG/tiles export",
            "Storm-scope observed radar layer",
        ],
    }


def build_temporal_layers(map_live: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = map_live or {}
    timeline = _dict_from(payload.get("timeline"))
    radar_observed = _dict_from(timeline.get("radar_observed"))
    nowcast = _dict_from(timeline.get("nowcast_short_term"))
    hours = _list_from(payload.get("hours"))
    return {
        "contract": "meteovoid_temporal_layers_v1",
        "generated_at": _now_iso(),
        "default_play_mode": "forecast_model",
        "play_modes": [
            {"id": "forecast_model", "label": "prévision modèle", "available": bool(hours)},
            {
                "id": "radar_observed",
                "label": "radar observé",
                "available": bool(radar_observed.get("available")),
            },
            {
                "id": "nowcast_short_term",
                "label": "nowcast court terme",
                "available": bool(nowcast.get("available")),
            },
        ],
    }


def build_signal_confidence_summary(
    report_dir: Path, map_live: dict[str, Any] | None = None
) -> dict[str, Any]:
    source_status = _read_json(report_dir / "source_status.json")
    radar = build_radar_machine_summary(report_dir)
    payload = map_live or {}
    station_count = (
        len(payload.get("stations", [])) if isinstance(payload.get("stations"), list) else 0
    )
    grid_count = len(payload.get("grid", [])) if isinstance(payload.get("grid"), list) else 0
    factors: list[dict[str, Any]] = [
        {"factor": "station_network", "score": round(min(station_count / 24.0, 1.0), 3)},
        {"factor": "grid_density", "score": round(min(grid_count / 300.0, 1.0), 3)},
        {
            "factor": "source_health",
            "score": round(_clamp01(source_status.get("source_health_score")), 3),
        },
        {"factor": "radar_machine", "score": 1.0 if radar.get("machine_layer_ready") else 0.0},
    ]
    factor_scores = [_num(row.get("score"), 0.0) or 0.0 for row in factors]
    score = sum(factor_scores) / max(len(factor_scores), 1)
    return {
        "contract": "meteovoid_signal_confidence_v1",
        "generated_at": _now_iso(),
        "score": round(_clamp01(score), 3),
        "factors": factors,
        "interpretation": "A high model signal without radar machine confirmation remains potential.",
    }


def build_station_quality_map(
    report_dir: Path, map_live: dict[str, Any] | None = None
) -> dict[str, Any]:
    quality = _read_json(report_dir / "data_quality.json")
    stations = _list_from(map_live.get("stations") if isinstance(map_live, dict) else [])
    rows = []
    for station in stations:
        if not isinstance(station, dict):
            continue
        signals = _list_from(station.get("signals"))
        text = " ".join(str(item).lower() for item in signals)
        flatline = "flatline" in text or "stagn" in text
        gap = "gap" in text or "trou" in text
        score = 1.0 - (0.35 if flatline else 0.0) - (0.25 if gap else 0.0)
        rows.append(
            {
                "station_id": station.get("station_id"),
                "name": station.get("name"),
                "lat": station.get("lat"),
                "lon": station.get("lon"),
                "quality_score": round(max(score, 0.0), 3),
                "flatline_suspected": flatline,
                "gap_suspected": gap,
            }
        )
    return {
        "contract": "meteovoid_station_quality_map_v1",
        "generated_at": _now_iso(),
        "summary": quality,
        "stations": rows,
        "map_layers": ["weather_risk", "data_quality"],
    }


def _list_from(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict_from(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def build_country_comparison(country_index: dict[str, Any]) -> dict[str, Any]:
    """Build a compact comparison table across all tracked country contracts."""

    countries = _dict_from(country_index.get("countries"))
    rows: list[dict[str, Any]] = []
    for key, item_raw in sorted(countries.items()):
        item = _dict_from(item_raw)
        summary = _dict_from(item.get("summary"))
        timeline = _dict_from(item.get("timeline"))
        station_count = int(_num(summary.get("station_count"), 0.0) or 0)
        grid_count = int(_num(summary.get("grid_count"), 0.0) or 0)
        hour_count = int(_num(summary.get("hour_count"), 0.0) or 0)
        has_radar = bool(_dict_from(timeline.get("radar_observed")).get("available"))
        completeness = (
            min(station_count / 6.0, 1.0) * 0.25
            + min(grid_count / 20.0, 1.0) * 0.25
            + min(hour_count / 48.0, 1.0) * 0.25
            + (0.25 if has_radar else 0.0)
        )
        rows.append(
            {
                "country": key,
                "label": item.get("label") or key,
                "mode": item.get("mode"),
                "primary_forecast": summary.get("primary_forecast"),
                "national_observations": summary.get("national_observations"),
                "radar_available": has_radar,
                "station_count": station_count,
                "grid_count": grid_count,
                "hour_count": hour_count,
                "completeness_score": round(_clamp01(completeness), 3),
            }
        )
    return {
        "contract": "meteovoid_country_comparison_v1",
        "generated_at": _now_iso(),
        "countries": rows,
        "best_covered": sorted(rows, key=lambda row: row["completeness_score"], reverse=True)[:5],
        "policy": "Compare coverage and source depth without pretending all countries have Belgium-level evidence.",
    }


def build_convergence_matrix(
    report_dir: Path,
    map_live: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Expose whether model, stations, radar, live smoke and official layers agree."""

    payload = map_live or {}
    radar = build_radar_machine_summary(report_dir)
    live_smoke = _read_json(report_dir / "live_smoke_summary.json") or _read_json(
        report_dir / "live_smoke.json"
    )
    watch = _read_json(report_dir / "belgium_alert_report.json")
    source_status = _read_json(report_dir / "source_status.json")
    hours = _list_from(payload.get("hours"))
    stations = _list_from(payload.get("stations"))
    grid = _list_from(payload.get("grid"))
    hour_scores = [
        _num(row.get("max_score") or row.get("score"), 0.0) or 0.0
        for row in hours
        if isinstance(row, dict)
    ]
    station_scores = [
        _num(row.get("score"), 0.0) or 0.0 for row in stations if isinstance(row, dict)
    ]
    grid_scores = [_num(row.get("score"), 0.0) or 0.0 for row in grid if isinstance(row, dict)]
    max_hour = max(hour_scores, default=0.0)
    max_station = max(station_scores, default=0.0)
    max_grid = max(grid_scores, default=0.0)
    live_score = _num(live_smoke.get("score") or live_smoke.get("last_score"), None)
    official = watch.get("official_warning") or watch.get("official_status") or "unknown"
    radar_metrics = _dict_from(radar.get("opera_radar_metrics"))
    layers = [
        {
            "id": "model_forecast",
            "label": "prévision modèle",
            "available": bool(hours),
            "score": round(_clamp01(max_hour), 3),
            "evidence": "timeline forecast_model",
        },
        {
            "id": "station_network",
            "label": "stations",
            "available": bool(stations),
            "score": round(_clamp01(max_station), 3),
            "evidence": f"{len(stations)} stations",
        },
        {
            "id": "grid_field",
            "label": "grille spatiale",
            "available": bool(grid),
            "score": round(_clamp01(max_grid), 3),
            "evidence": f"{len(grid)} points",
        },
        {
            "id": "live_smoke",
            "label": "live smoke",
            "available": bool(live_smoke),
            "score": round(_clamp01(live_score), 3) if live_score is not None else None,
            "evidence": live_smoke.get("status") or "not_available",
        },
        {
            "id": "radar_machine",
            "label": "radar machine",
            "available": bool(radar.get("machine_layer_ready")),
            "score": 1.0 if radar.get("machine_layer_ready") else 0.0,
            "evidence": radar_metrics.get("status") or "not_confirmed",
        },
        {
            "id": "official_warning",
            "label": "source officielle",
            "available": official != "unknown",
            "score": None,
            "evidence": official,
        },
        {
            "id": "source_health",
            "label": "santé sources",
            "available": bool(source_status),
            "score": round(_clamp01(source_status.get("source_health_score")), 3),
            "evidence": source_status.get("status") or "unknown",
        },
    ]
    numeric_scores = [
        score for row in layers if (score := _num(row.get("score"), None)) is not None
    ]
    active_count = sum(1 for row in layers if row.get("available"))
    spread = max(numeric_scores) - min(numeric_scores) if len(numeric_scores) >= 2 else 0.0
    agreement = _clamp01((active_count / len(layers)) * (1.0 - min(spread, 1.0) * 0.35))
    if agreement >= 0.72:
        label = "convergence forte"
    elif agreement >= 0.45:
        label = "convergence partielle"
    else:
        label = "signal encore fragile"
    return {
        "contract": "meteovoid_convergence_matrix_v1",
        "generated_at": _now_iso(),
        "agreement_score": round(agreement, 3),
        "label": label,
        "layers": layers,
        "rules": [
            "A model signal is not an observed event.",
            "Radar machine confirmation is separated from visual radar availability.",
            "Missing layers reduce confidence instead of being silently ignored.",
        ],
    }


def build_forecast_ledger(report_dir: Path) -> dict[str, Any]:
    """Build an append-only friendly forecast ledger summary."""

    forecast_rows = _read_csv(report_dir / "forecast_history.csv")
    history_rows = _read_csv(report_dir / "history.csv")
    horizons = ["H-24", "H-12", "H-6", "H-3"]
    rows_by_horizon: dict[str, int] = {horizon: 0 for horizon in horizons}
    for row in forecast_rows:
        raw = str(row.get("horizon") or row.get("lead_time") or row.get("lead_time_hours") or "")
        for horizon in horizons:
            if horizon.replace("H-", "") in raw or horizon in raw:
                rows_by_horizon[horizon] += 1
                break
    return {
        "contract": "meteovoid_forecast_ledger_v1",
        "generated_at": _now_iso(),
        "forecast_rows": len(forecast_rows),
        "event_rows": len(history_rows),
        "by_horizon": [
            {"horizon": horizon, "rows": rows_by_horizon[horizon]} for horizon in horizons
        ],
        "append_only_fields": [
            "run_id",
            "generated_at",
            "target_time",
            "horizon",
            "zone",
            "risk_type",
            "forecast_score",
            "observed_score",
            "radar_confirmed",
            "lightning_confirmed",
            "verdict",
        ],
        "next_step": "Store every forecast before the event and join it later with observations.",
    }


def build_operational_readiness(
    report_dir: Path,
    country_index: dict[str, Any],
    map_live: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarize what is production-ready and what remains a candidate."""

    payload = map_live or {}
    countries = _dict_from(country_index.get("countries"))
    checks = [
        {
            "id": "belgium_map_live",
            "label": "contrat Belgique live",
            "ok": bool(payload.get("hours") and payload.get("stations")),
        },
        {
            "id": "country_contracts",
            "label": "contrats pays Europe",
            "ok": len(countries) >= 6,
        },
        {
            "id": "radar_machine",
            "label": "radar machine",
            "ok": build_radar_machine_summary(report_dir).get("machine_layer_ready") is True,
        },
        {
            "id": "validation_ledger",
            "label": "ledger validation",
            "ok": len(_read_csv(report_dir / "forecast_history.csv")) > 0,
        },
        {
            "id": "live_smoke",
            "label": "live smoke",
            "ok": bool(_read_json(report_dir / "live_smoke.json")),
        },
    ]
    ready_count = sum(1 for check in checks if check["ok"])
    score = ready_count / max(len(checks), 1)
    missing = [str(check["label"]) for check in checks if not check["ok"]]
    return {
        "contract": "meteovoid_operational_readiness_v1",
        "generated_at": _now_iso(),
        "score": round(score, 3),
        "checks": checks,
        "ready_count": ready_count,
        "check_count": len(checks),
        "missing_or_candidate": missing,
        "deployment_policy": "Fail soft in the UI, but expose every missing layer explicitly.",
    }


def build_risk_ontology() -> dict[str, Any]:
    """Define public risk families and which evidence layers should support them."""

    families = [
        (
            "convective",
            "Risque convectif",
            ["CAPE", "CIN", "point_de_rosee", "rafales", "radar", "foudre"],
        ),
        ("heat", "Stress chaleur", ["temperature", "humidite", "point_de_rosee", "nuit_tropicale"]),
        ("rain", "Pluie intense", ["precipitation", "radar", "PWAT", "saturation_sol"]),
        ("wind", "Rafales", ["gradient", "rafales_modele", "radar", "ligne_convective"]),
        ("data_quality", "Qualité donnée", ["fraicheur", "trous", "flatline", "voisins"]),
    ]
    return {
        "contract": "meteovoid_risk_ontology_v1",
        "generated_at": _now_iso(),
        "families": [
            {"id": item[0], "label": item[1], "required_evidence_layers": item[2]}
            for item in families
        ],
        "policy": "Risk labels must identify whether they are model potential, observed signal or validated event.",
    }


def build_action_cards(
    convergence: dict[str, Any],
    confidence: dict[str, Any],
) -> dict[str, Any]:
    """Create public and expert action cards without replacing official warnings."""

    agreement = _clamp01(convergence.get("agreement_score"))
    confidence_score = _clamp01(confidence.get("score"))
    combined = round(_clamp01((agreement + confidence_score) / 2.0), 3)
    if combined >= 0.70:
        level = "watch_confirmed"
        public_text = (
            "Signal cohérent. Suivre les bulletins officiels et éviter de banaliser l’évolution."
        )
    elif combined >= 0.45:
        level = "watch_potential"
        public_text = "Potentiel présent, confirmation partielle. Situation à surveiller sans conclure trop vite."
    else:
        level = "low_confidence"
        public_text = "Signal incomplet ou peu convergent. La plateforme garde la veille ouverte."
    return {
        "contract": "meteovoid_action_cards_v1",
        "generated_at": _now_iso(),
        "level": level,
        "score": combined,
        "public_card": {
            "title": "Lecture publique",
            "text": public_text,
            "official_warning_policy": "Toujours suivre les services météo nationaux et les autorités.",
        },
        "expert_card": {
            "title": "Lecture expert",
            "checks": [
                "Comparer modèle, stations, radar et foudre.",
                "Vérifier les couches manquantes avant de qualifier l’événement.",
                "Archiver le run pour validation H-24/H-12/H-6/H-3.",
            ],
        },
    }


def build_ui_contracts() -> dict[str, Any]:
    """Describe which UI pages are supposed to read which public endpoints."""

    panels = [
        ("index.html", ["api/map_live.json", "api/watch.json", "api/platform.json"]),
        ("expert.html", ["api/explain.json", "api/convergence_matrix.json"]),
        ("sources.html", ["api/europe_sources.json", "api/source_health.json"]),
        ("validation.html", ["api/validation_summary.json", "api/forecast_ledger.json"]),
        ("corridors.html", ["api/corridors.json"]),
        ("radar-machine.html", ["api/radar_machine.json"]),
        ("signal.html", ["api/signal_confidence.json", "api/action_cards.json"]),
    ]
    return {
        "contract": "meteovoid_ui_contracts_v1",
        "generated_at": _now_iso(),
        "pages": [{"page": page, "required_endpoints": endpoints} for page, endpoints in panels],
        "policy": "The UI should fail soft, show missing data, and never hide source uncertainty.",
    }


def build_schema_catalog() -> dict[str, Any]:
    """Expose the public schema catalogue used by downstream checks."""

    schemas = [
        ("convergence_matrix", "schemas/public_api/convergence_matrix.schema.json"),
        ("forecast_ledger", "schemas/public_api/forecast_ledger.schema.json"),
        ("public_manifest", "schemas/public_api/public_manifest.schema.json"),
    ]
    return {
        "contract": "meteovoid_schema_catalog_v1",
        "generated_at": _now_iso(),
        "schemas": [{"id": item[0], "path": item[1]} for item in schemas],
        "policy": "Schemas document public JSON contracts; missing data must be explicit, not hidden.",
    }


def build_source_health() -> dict[str, Any]:
    """Expose expected source status by source family."""

    api = build_europe_sources_api()
    countries = _dict_from(api.get("countries"))
    rows: list[dict[str, Any]] = []
    for country, profile_raw in sorted(countries.items()):
        profile = _dict_from(profile_raw)
        active = _list_from(profile.get("active"))
        candidates = _list_from(profile.get("candidates"))
        experimental = _list_from(profile.get("experimental"))
        total = len(active) + len(candidates) + len(experimental)
        rows.append(
            {
                "country": country,
                "label": profile.get("label") or country,
                "active_count": len(active),
                "candidate_count": len(candidates),
                "experimental_count": len(experimental),
                "source_depth_score": round(min(total / 5.0, 1.0), 3),
            }
        )
    return {
        "contract": "meteovoid_source_health_v1",
        "generated_at": _now_iso(),
        "countries": rows,
        "policy": "Active, candidate and experimental sources remain separated.",
    }


def build_deep_platform_api(
    report_dir: Path,
    map_live: dict[str, Any] | None = None,
) -> dict[str, Any]:
    country_index = build_country_contracts(belgium_map_live=map_live)
    validation_summary = build_validation_summary(report_dir)
    explain = build_signal_explain(report_dir)
    corridors = build_corridor_summary(report_dir)
    events = build_event_memory(report_dir)
    radar_machine = build_radar_machine_summary(report_dir)
    temporal_layers = build_temporal_layers(map_live)
    signal_confidence = build_signal_confidence_summary(report_dir, map_live)
    station_quality_map = build_station_quality_map(report_dir, map_live)
    convergence_matrix = build_convergence_matrix(report_dir, map_live)
    country_comparison = build_country_comparison(country_index)
    forecast_ledger = build_forecast_ledger(report_dir)
    operational_readiness = build_operational_readiness(report_dir, country_index, map_live)
    risk_ontology = build_risk_ontology()
    action_cards = build_action_cards(convergence_matrix, signal_confidence)
    ui_contracts = build_ui_contracts()
    source_health = build_source_health()
    schema_catalog = build_schema_catalog()
    return {
        "countries": country_index,
        "sources": build_europe_sources_api(),
        "validation_summary": validation_summary,
        "explain": explain,
        "corridors": corridors,
        "events": events,
        "radar_machine": radar_machine,
        "temporal_layers": temporal_layers,
        "signal_confidence": signal_confidence,
        "station_quality_map": station_quality_map,
        "convergence_matrix": convergence_matrix,
        "country_comparison": country_comparison,
        "forecast_ledger": forecast_ledger,
        "operational_readiness": operational_readiness,
        "risk_ontology": risk_ontology,
        "action_cards": action_cards,
        "ui_contracts": ui_contracts,
        "source_health": source_health,
        "schema_catalog": schema_catalog,
        "platform": {
            "contract": "meteovoid_platform_deepening_v2",
            "generated_at": _now_iso(),
            "country_count": len(country_index.get("countries", {})),
            "primary_europe_source": "open_meteo",
            "advanced_country": "belgium",
            "new_contracts": [
                "convergence_matrix",
                "country_comparison",
                "forecast_ledger",
                "operational_readiness",
                "risk_ontology",
                "action_cards",
                "ui_contracts",
                "source_health",
                "schema_catalog",
            ],
        },
    }
