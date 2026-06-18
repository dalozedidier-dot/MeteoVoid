from __future__ import annotations

import math
from typing import Any


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        value_f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(value_f) or math.isinf(value_f):
        return None
    return value_f


def _max_number(values: Any) -> float | None:
    if not isinstance(values, list):
        return None
    nums = [_safe_float(v) for v in values]
    finite = [v for v in nums if v is not None]
    return max(finite) if finite else None


def _min_number(values: Any) -> float | None:
    if not isinstance(values, list):
        return None
    nums = [_safe_float(v) for v in values]
    finite = [v for v in nums if v is not None]
    return min(finite) if finite else None


def _clamp01(value: float | None) -> float:
    if value is None:
        return 0.0
    return max(0.0, min(1.0, float(value)))


def _ramp(value: float | None, low: float, high: float) -> float:
    if value is None:
        return 0.0
    if high == low:
        return 1.0 if value >= high else 0.0
    return _clamp01((float(value) - low) / (high - low))


def _inverse_ramp(value: float | None, high_risk_value: float, low_risk_value: float) -> float:
    if value is None:
        return 0.0
    if low_risk_value == high_risk_value:
        return 1.0 if value <= high_risk_value else 0.0
    return _clamp01((low_risk_value - float(value)) / (low_risk_value - high_risk_value))


NATIVE_CONVECTIVE_ALIASES: dict[str, tuple[str, ...]] = {
    "cape_j_kg": ("cape_j_kg", "cape", "CAPE", "convective_available_potential_energy"),
    "cin_j_kg": ("cin_j_kg", "cin", "CIN", "convective_inhibition"),
    "lifted_index_c": ("lifted_index_c", "lifted_index", "LI"),
    "k_index_c": ("k_index_c", "k_index", "K_index"),
    "total_totals_index": ("total_totals_index", "total_totals", "TT"),
    "precipitable_water_mm": ("precipitable_water_mm", "pwat_mm", "pwat", "PWAT"),
    "lightning_potential_index": (
        "lightning_potential_index",
        "lightning_potential",
        "lpi",
        "LPI",
    ),
    "freezing_level_height_m": ("freezing_level_height_m", "freezing_level_height"),
    "boundary_layer_height_m": (
        "boundary_layer_height_m",
        "boundary_layer_height",
        "pbl_height",
    ),
    "shear_0_6km_ms": ("shear_0_6km_ms", "bulk_shear_0_6km_ms", "deep_layer_shear_ms"),
    "shear_0_3km_ms": ("shear_0_3km_ms", "bulk_shear_0_3km_ms"),
    "srh_0_1km_m2_s2": ("srh_0_1km_m2_s2", "srh_0_1km_m2s2", "srh_0_1km"),
    "srh_0_3km_m2_s2": ("srh_0_3km_m2_s2", "srh_0_3km_m2s2", "srh_0_3km"),
    "lcl_m": ("lcl_m", "lifted_condensation_level_m"),
    "lfc_m": ("lfc_m", "level_free_convection_m"),
    "theta_e_850k": ("theta_e_850k", "theta_e_850", "equivalent_potential_temperature_850hPa"),
    "lapse_rate_700_500_c_km": (
        "lapse_rate_700_500_c_km",
        "lapse_rate_700_500",
        "mid_level_lapse_rate_c_km",
    ),
}


def native_convective_indices_from_hourly(hourly: dict[str, Any]) -> dict[str, Any]:
    raw: dict[str, float | None] = {}
    for canonical, aliases in NATIVE_CONVECTIVE_ALIASES.items():
        value: float | None = None
        for alias in aliases:
            if alias not in hourly:
                continue
            if canonical in {"cin_j_kg", "lifted_index_c", "lcl_m", "lfc_m"}:
                value = _min_number(hourly.get(alias))
            else:
                value = _max_number(hourly.get(alias))
            if value is not None:
                break
        raw[canonical] = value

    normalized = {
        "cape": _ramp(raw["cape_j_kg"], 500.0, 2500.0),
        "cin_erosion": _clamp01((float(raw["cin_j_kg"] or -200.0) + 175.0) / 175.0),
        "lifted_index": _inverse_ramp(raw["lifted_index_c"], -6.0, 0.0),
        "k_index": _ramp(raw["k_index_c"], 25.0, 40.0),
        "total_totals": _ramp(raw["total_totals_index"], 44.0, 52.0),
        "precipitable_water": _ramp(raw["precipitable_water_mm"], 25.0, 45.0),
        "lightning_potential": _ramp(raw["lightning_potential_index"], 1.0, 8.0),
        "freezing_level": _ramp(raw["freezing_level_height_m"], 2800.0, 4200.0),
        "boundary_layer": _ramp(raw["boundary_layer_height_m"], 800.0, 2200.0),
        "shear_0_6km": _ramp(raw["shear_0_6km_ms"], 10.0, 25.0),
        "shear_0_3km": _ramp(raw["shear_0_3km_ms"], 7.0, 18.0),
        "srh_0_1km": _ramp(raw["srh_0_1km_m2_s2"], 50.0, 150.0),
        "srh_0_3km": _ramp(raw["srh_0_3km_m2_s2"], 100.0, 250.0),
        "lcl": _inverse_ramp(raw["lcl_m"], 800.0, 1600.0),
        "lfc": _inverse_ramp(raw["lfc_m"], 1200.0, 3000.0),
        "theta_e_850": _ramp(raw["theta_e_850k"], 320.0, 350.0),
        "lapse_rate_700_500": _ramp(raw["lapse_rate_700_500_c_km"], 6.5, 8.5),
    }
    available = [key for key, value in raw.items() if value is not None]
    if available:
        instability = _clamp01(
            0.30 * normalized["cape"]
            + 0.20 * normalized["lifted_index"]
            + 0.14 * normalized["k_index"]
            + 0.12 * normalized["total_totals"]
            + 0.10 * normalized["precipitable_water"]
            + 0.08 * normalized["theta_e_850"]
            + 0.06 * normalized["lightning_potential"]
            + 0.04 * normalized["boundary_layer"]
        )
        organization = _clamp01(
            0.36 * normalized["shear_0_6km"]
            + 0.20 * normalized["shear_0_3km"]
            + 0.22 * normalized["srh_0_1km"]
            + 0.22 * normalized["srh_0_3km"]
        )
        cap_break = _clamp01(
            0.42 * normalized["cin_erosion"]
            + 0.26 * normalized["lcl"]
            + 0.20 * normalized["lfc"]
            + 0.08 * normalized["lapse_rate_700_500"]
            + 0.04 * normalized["freezing_level"]
        )
        native_score = _clamp01(0.45 * instability + 0.30 * organization + 0.25 * cap_break)
    else:
        instability = organization = cap_break = native_score = None

    return {
        "available": bool(available),
        "available_fields": available,
        "raw": {k: (round(v, 6) if v is not None else None) for k, v in raw.items()},
        "normalized": {k: round(v, 6) for k, v in normalized.items()},
        "instability_index": round(instability, 6) if instability is not None else None,
        "organization_index": round(organization, 6) if organization is not None else None,
        "cap_break_index": round(cap_break, 6) if cap_break is not None else None,
        "native_convective_score": round(native_score, 6) if native_score is not None else None,
        "source_contract": "native_convective_fields_optional_v1",
    }


def build_score_layers(
    components: dict[str, float], native_convective_indices: dict[str, Any] | None = None
) -> dict[str, Any]:
    heat = _clamp01(components.get("heat"))
    moisture = _clamp01(components.get("moisture"))
    precipitation = _clamp01(components.get("precipitation"))
    wind_gust = _clamp01(components.get("wind_gust"))
    pressure_drop = _clamp01(components.get("pressure_drop"))
    weather_code = _clamp01(components.get("weather_code"))

    heat_stress_score = _clamp01(0.72 * heat + 0.28 * moisture)
    proxy_convective_score = _clamp01(
        0.22 * moisture
        + 0.25 * precipitation
        + 0.17 * pressure_drop
        + 0.18 * weather_code
        + 0.10 * wind_gust
        + 0.08 * heat
    )
    native_score = None
    if isinstance(native_convective_indices, dict):
        native_score = _safe_float(native_convective_indices.get("native_convective_score"))

    if native_score is None:
        convective_risk_score = proxy_convective_score
        mode = "proxy_only"
    else:
        convective_risk_score = _clamp01(0.45 * proxy_convective_score + 0.55 * native_score)
        mode = "proxy_plus_native"

    return {
        "heat_stress_score": round(heat_stress_score, 6),
        "convective_proxy_score": round(proxy_convective_score, 6),
        "native_convective_score": round(native_score, 6) if native_score is not None else None,
        "convective_risk_score": round(convective_risk_score, 6),
        "mode": mode,
        "contract": "heat_vs_convective_score_layers_v1",
    }
