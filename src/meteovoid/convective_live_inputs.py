"""Real-only convective input helpers for MeteoVoid public pages.

The goal of this module is to keep the severe-weather ingredient table honest:
values are published only when they come from a live/real upstream data source
or from a deterministic calculation applied to those real upstream fields.  No
synthetic value is generated here.
"""

from __future__ import annotations

import math
from typing import Any

REAL_INPUT_CONTRACT = "meteovoid_real_convective_inputs_v1"

OPEN_METEO_REQUIRED_HOURLY_VARIABLES: tuple[str, ...] = (
    "temperature_2m",
    "relative_humidity_2m",
    "dew_point_2m",
    "precipitation_probability",
    "precipitation",
    "rain",
    "showers",
    "weather_code",
    "pressure_msl",
    "surface_pressure",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "cloud_cover",
    "cape",
    "lifted_index",
    "convective_inhibition",
    "freezing_level_height",
    "boundary_layer_height",
    "total_column_integrated_water_vapour",
    "thunderstorm_probability",
    "temperature_850hPa",
    "temperature_700hPa",
    "temperature_500hPa",
    "wind_speed_1000hPa",
    "wind_direction_1000hPa",
    "wind_speed_500hPa",
    "wind_direction_500hPa",
    "wind_speed_475hPa",
    "wind_direction_475hPa",
    "vertical_velocity_1000hPa",
    "vertical_velocity_925hPa",
)

FIELD_SPECS: tuple[dict[str, str], ...] = (
    {
        "key": "dew_point_c",
        "label": "Point de rosée",
        "unit": "°C",
        "family": "surface",
        "source": "Open-Meteo Forecast API",
    },
    {
        "key": "cape_jkg",
        "label": "CAPE",
        "unit": "J/kg",
        "family": "instability",
        "source": "Open-Meteo model field",
    },
    {
        "key": "cin_jkg",
        "label": "CIN",
        "unit": "J/kg",
        "family": "cap",
        "source": "Open-Meteo model field",
    },
    {
        "key": "shear_0_6km_ms",
        "label": "Cisaillement 0–6 km",
        "unit": "m/s",
        "family": "organization",
        "source": "derived from Open-Meteo pressure-level wind vectors",
    },
    {
        "key": "surface_convergence_index",
        "label": "Convergence au sol",
        "unit": "10⁻⁴ s⁻¹",
        "family": "forcing",
        "source": "derived from real 10 m wind field when spatial wind vectors are available",
    },
    {
        "key": "pressure_hpa",
        "label": "Pression",
        "unit": "hPa",
        "family": "surface",
        "source": "Open-Meteo pressure field",
    },
    {
        "key": "wind_gust_ms",
        "label": "Rafales",
        "unit": "m/s",
        "family": "surface",
        "source": "Open-Meteo wind gust field",
    },
    {
        "key": "pwat_mm",
        "label": "PWAT / eau précipitable",
        "unit": "mm",
        "family": "moisture",
        "source": "Open-Meteo total column integrated water vapour",
    },
    {
        "key": "temperature_850hpa_c",
        "label": "Température 850 hPa",
        "unit": "°C",
        "family": "aloft",
        "source": "Open-Meteo pressure-level temperature",
    },
    {
        "key": "temperature_700hpa_c",
        "label": "Température 700 hPa",
        "unit": "°C",
        "family": "aloft",
        "source": "Open-Meteo pressure-level temperature",
    },
    {
        "key": "temperature_500hpa_c",
        "label": "Température 500 hPa",
        "unit": "°C",
        "family": "aloft",
        "source": "Open-Meteo pressure-level temperature",
    },
    {
        "key": "radar",
        "label": "Radar",
        "unit": "frame",
        "family": "observation",
        "source": "RainViewer / national radar / OPERA ORD when configured",
    },
    {
        "key": "lightning",
        "label": "Foudre",
        "unit": "impacts",
        "family": "observation",
        "source": "configured lightning provider only",
    },
    {
        "key": "satellite",
        "label": "Satellite",
        "unit": "layer",
        "family": "observation",
        "source": "configured satellite WMS/tile provider only",
    },
)

ALIAS_MAP: dict[str, tuple[str, ...]] = {
    "dew_point_c": ("dew_point_2m", "dewpoint_2m", "dew_point_c"),
    "cape_jkg": ("cape", "cape_j_kg", "cape_jkg"),
    "cin_jkg": ("convective_inhibition", "cin", "cin_j_kg", "cin_jkg"),
    "pressure_hpa": ("surface_pressure", "pressure_msl", "pressure_hpa"),
    "wind_gust_ms": ("wind_gusts_10m", "wind_gust_ms"),
    "pwat_mm": (
        "total_column_integrated_water_vapour",
        "precipitable_water_mm",
        "pwat_mm",
        "pwat",
    ),
    "temperature_850hpa_c": ("temperature_850hPa", "temperature_850hpa_c"),
    "temperature_700hpa_c": ("temperature_700hPa", "temperature_700hpa_c"),
    "temperature_500hpa_c": ("temperature_500hPa", "temperature_500hpa_c"),
    "thunderstorm_probability_pct": ("thunderstorm_probability",),
}

MIN_AGG_KEYS = {
    "cin_jkg",
    "pressure_hpa",
    "temperature_850hpa_c",
    "temperature_700hpa_c",
    "temperature_500hpa_c",
}


def safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        out = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def list_floats(values: Any) -> list[float]:
    if not isinstance(values, list):
        return []
    out: list[float] = []
    for value in values:
        item = safe_float(value)
        if item is not None:
            out.append(item)
    return out


def _series(hourly: dict[str, Any], *keys: str) -> list[float]:
    for key in keys:
        values = list_floats(hourly.get(key))
        if values:
            return values
    return []


def _wind_components(speed_ms: float, direction_deg: float) -> tuple[float, float]:
    """Convert meteorological wind direction/speed to u/v components.

    Direction is where the wind blows *from*, the convention used in weather
    APIs. Returned components are the vector toward which the air moves.
    """
    rad = math.radians(direction_deg)
    u = -speed_ms * math.sin(rad)
    v = -speed_ms * math.cos(rad)
    return u, v


def _vector_shear(
    low_speed: list[float],
    low_dir: list[float],
    high_speed: list[float],
    high_dir: list[float],
) -> list[float]:
    n = min(len(low_speed), len(low_dir), len(high_speed), len(high_dir))
    out: list[float] = []
    for i in range(n):
        u0, v0 = _wind_components(low_speed[i], low_dir[i])
        u1, v1 = _wind_components(high_speed[i], high_dir[i])
        out.append(math.hypot(u1 - u0, v1 - v0))
    return out


def augment_hourly_with_real_derived_fields(hourly: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``hourly`` with derived real-only fields.

    The function derives shear only from real pressure-level wind vectors. It
    never inserts synthetic CAPE/CIN/PWAT/etc.
    """
    out = dict(hourly)

    if "precipitable_water_mm" not in out and "total_column_integrated_water_vapour" in out:
        out["precipitable_water_mm"] = out["total_column_integrated_water_vapour"]

    low_speed = _series(out, "wind_speed_1000hPa", "wind_speed_925hPa")
    low_dir = _series(out, "wind_direction_1000hPa", "wind_direction_925hPa")
    high_speed = _series(out, "wind_speed_475hPa", "wind_speed_500hPa")
    high_dir = _series(out, "wind_direction_475hPa", "wind_direction_500hPa")
    shear = _vector_shear(low_speed, low_dir, high_speed, high_dir)
    if shear:
        out["shear_0_6km_ms"] = [round(v, 3) for v in shear]
        out["bulk_shear_0_6km_ms"] = out["shear_0_6km_ms"]

    return out


def _field_values(hourly: dict[str, Any], key: str) -> list[float]:
    if key == "shear_0_6km_ms":
        return _series(hourly, "shear_0_6km_ms", "bulk_shear_0_6km_ms")
    aliases = ALIAS_MAP.get(key, (key,))
    return _series(hourly, *aliases)


def _aggregate_values(values: list[float], key: str) -> float | None:
    if not values:
        return None
    value = min(values) if key in MIN_AGG_KEYS else max(values)
    return round(value, 3)


def station_real_input_summary(
    hourly: dict[str, Any],
    *,
    source_mode: str,
    source_name: str = "Open-Meteo Forecast API",
) -> dict[str, Any]:
    augmented = augment_hourly_with_real_derived_fields(hourly)
    is_real = source_mode != "offline_demo"
    fields: dict[str, Any] = {}
    for spec in FIELD_SPECS:
        key = spec["key"]
        if key in {"radar", "lightning", "satellite", "surface_convergence_index"}:
            fields[key] = {
                **spec,
                "available": False,
                "status": "external_provider_required" if is_real else "demo_disabled",
                "value": None,
                "basis": "not_populated_by_station_forecast",
            }
            continue
        values = _field_values(augmented, key)
        value = _aggregate_values(values, key)
        fields[key] = {
            **spec,
            "available": bool(is_real and value is not None),
            "status": (
                "real" if is_real and value is not None else ("missing" if is_real else "demo_only")
            ),
            "value": value if is_real else None,
            "basis": source_name if is_real and value is not None else source_mode,
            "sample_count": len(values),
        }

    # Surface wind components are kept for later network convergence estimation.
    wind_speed = _series(augmented, "wind_speed_10m")
    wind_dir = _series(augmented, "wind_direction_10m")
    if is_real and wind_speed and wind_dir:
        idx = min(range(min(len(wind_speed), len(wind_dir))), key=lambda i: -wind_speed[i])
        u, v = _wind_components(wind_speed[idx], wind_dir[idx])
        fields["surface_wind_vector"] = {
            "key": "surface_wind_vector",
            "label": "Vent 10 m vectoriel",
            "unit": "m/s",
            "family": "surface",
            "source": source_name,
            "available": True,
            "status": "real",
            "speed_ms": round(wind_speed[idx], 3),
            "direction_deg": round(wind_dir[idx], 1),
            "u_ms": round(u, 3),
            "v_ms": round(v, 3),
            "basis": source_name,
        }

    available = [key for key, field in fields.items() if field.get("available")]
    return {
        "contract": REAL_INPUT_CONTRACT,
        "source_mode": source_mode,
        "source_name": source_name,
        "real_data": is_real,
        "available_count": len(available),
        "required_count": len(FIELD_SPECS),
        "available_fields": available,
        "missing_fields": [spec["key"] for spec in FIELD_SPECS if spec["key"] not in available],
        "fields": fields,
        "note": (
            "Aucune valeur synthétique n'est publiée dans ce contrat. "
            "Les champs absents restent absents jusqu'à connexion d'un fournisseur réel."
        ),
    }


def _regression_slope(points: list[tuple[float, float]]) -> float | None:
    if len(points) < 2:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    denom = sum((x - mx) ** 2 for x in xs)
    if abs(denom) < 1e-12:
        return None
    return sum((x - mx) * (y - my) for x, y in points) / denom


def _latlon_to_km(lat: float, lon: float, ref_lat: float) -> tuple[float, float]:
    x = lon * 111.32 * math.cos(math.radians(ref_lat))
    y = lat * 110.57
    return x, y


def estimate_network_surface_convergence(stations: list[dict[str, Any]]) -> dict[str, Any]:
    """Estimate low-level convergence from real station wind vectors.

    This is not a synthetic forecast. It is a diagnostic derived from the same
    real 10 m wind vectors used by the station pages. If the vectors are not
    available, the field is explicitly marked unavailable.
    """
    rows: list[tuple[float, float, float, float]] = []
    lats: list[float] = []
    for station in stations:
        lat = safe_float(station.get("lat"))
        lon = safe_float(station.get("lon"))
        fields = ((station.get("live_convective_inputs") or {}).get("fields")) or {}
        vec = fields.get("surface_wind_vector") if isinstance(fields, dict) else None
        if not isinstance(vec, dict) or lat is None or lon is None:
            continue
        u = safe_float(vec.get("u_ms"))
        v = safe_float(vec.get("v_ms"))
        if u is None or v is None:
            continue
        lats.append(lat)
        rows.append((lat, lon, u, v))
    if len(rows) < 3 or not lats:
        return {
            "key": "surface_convergence_index",
            "label": "Convergence au sol",
            "unit": "10⁻⁴ s⁻¹",
            "available": False,
            "status": "missing_wind_vectors",
            "value": None,
            "basis": "requires at least 3 real 10 m wind vectors",
        }
    ref_lat = sum(lats) / len(lats)
    u_points: list[tuple[float, float]] = []
    v_points: list[tuple[float, float]] = []
    for lat, lon, u, v in rows:
        x_km, y_km = _latlon_to_km(lat, lon, ref_lat)
        u_points.append((x_km * 1000.0, u))
        v_points.append((y_km * 1000.0, v))
    du_dx = _regression_slope(u_points)
    dv_dy = _regression_slope(v_points)
    if du_dx is None or dv_dy is None:
        return {
            "key": "surface_convergence_index",
            "label": "Convergence au sol",
            "unit": "10⁻⁴ s⁻¹",
            "available": False,
            "status": "insufficient_geometry",
            "value": None,
            "basis": "real wind vectors could not produce a stable spatial gradient",
        }
    convergence_s = -(du_dx + dv_dy)
    convergence_1e4 = convergence_s * 10000.0
    return {
        "key": "surface_convergence_index",
        "label": "Convergence au sol",
        "unit": "10⁻⁴ s⁻¹",
        "available": True,
        "status": "derived_real",
        "value": round(convergence_1e4, 4),
        "basis": "least-squares gradient from real 10 m wind vectors over the station network",
        "station_count": len(rows),
    }


def aggregate_real_input_summary(
    stations: list[dict[str, Any]],
    *,
    external: dict[str, Any] | None = None,
) -> dict[str, Any]:
    field_out: dict[str, Any] = {}
    for spec in FIELD_SPECS:
        key = spec["key"]
        available_values: list[float] = []
        source_statuses: set[str] = set()
        for station in stations:
            live = station.get("live_convective_inputs") if isinstance(station, dict) else None
            fields = (live or {}).get("fields") if isinstance(live, dict) else None
            field = fields.get(key) if isinstance(fields, dict) else None
            if not isinstance(field, dict):
                continue
            source_statuses.add(str(field.get("status") or "unknown"))
            value = safe_float(field.get("value"))
            if field.get("available") and value is not None:
                available_values.append(value)
        value = _aggregate_values(available_values, key)
        field_out[key] = {
            **spec,
            "available": bool(available_values),
            "status": (
                "real"
                if available_values
                else (next(iter(source_statuses)) if source_statuses else "missing")
            ),
            "value": value,
            "station_count": len(available_values),
        }

    convergence = estimate_network_surface_convergence(stations)
    field_out["surface_convergence_index"] = {
        **field_out.get("surface_convergence_index", {}),
        **convergence,
    }

    external = external if isinstance(external, dict) else {}
    for key in ("radar", "lightning", "satellite"):
        if key in external:
            ext = external[key] if isinstance(external[key], dict) else {}
            field_out[key] = {**field_out.get(key, {}), **ext}

    available = [key for key, field in field_out.items() if field.get("available")]
    return {
        "contract": REAL_INPUT_CONTRACT,
        "real_only": True,
        "required_count": len(FIELD_SPECS),
        "available_count": len(available),
        "available_fields": available,
        "missing_fields": [spec["key"] for spec in FIELD_SPECS if spec["key"] not in available],
        "fields": field_out,
        "note": (
            "Tableau des ingrédients convectifs réels. Les champs CAPE/CIN/PWAT/températures "
            "en altitude proviennent de champs de modèles météo live ; radar/foudre/satellite "
            "ne sont promus que si un fournisseur réel est connecté. Aucun champ n'est simulé."
        ),
    }
