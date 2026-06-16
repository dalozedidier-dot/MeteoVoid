from __future__ import annotations

import csv
import json
import math
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import yaml  # type: ignore[import-untyped]

OPEN_METEO_ENDPOINT = "https://api.open-meteo.com/v1/forecast"
DEFAULT_TIMEZONE = "Europe/Brussels"

SURFACE_VARIABLES = [
    "temperature_2m",
    "dew_point_2m",
    "relative_humidity_2m",
    "precipitation_probability",
    "precipitation",
    "showers",
    "weather_code",
    "pressure_msl",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "cape",
]
PRESSURE_LEVELS = [925, 850, 700, 500, 300]
PRESSURE_VARIABLES = [
    f"{name}_{level}hPa"
    for level in PRESSURE_LEVELS
    for name in (
        "temperature",
        "dew_point",
        "relative_humidity",
        "wind_speed",
        "wind_direction",
        "geopotential_height",
    )
]
OPEN_METEO_UPSTREAM_VARIABLES = SURFACE_VARIABLES + PRESSURE_VARIABLES


@dataclass(frozen=True, slots=True)
class RegionProbe:
    region_id: str
    name: str
    lat: float
    lon: float
    role: str
    weight: float
    station_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CorridorSpec:
    corridor_id: str
    name: str
    source_region: str
    target_region: str
    target_zones: tuple[str, ...]
    expected_bearing_deg: float
    distance_km: float
    lead_time_hours: tuple[float, float]
    weight: float


@dataclass(frozen=True, slots=True)
class RegionDiagnostic:
    region_id: str
    name: str
    lat: float
    lon: float
    data_mode: str
    source_status: str
    upstream_activity_score: float
    moisture_feed_score: float
    instability_score: float
    organization_score: float
    cap_break_score: float
    radar_confirmation_score: float
    lightning_confirmation_score: float
    mean_motion_to_deg: float | None
    mean_motion_speed_ms: float | None
    indices: dict[str, float | None]
    evidence: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CorridorDiagnostic:
    corridor_id: str
    name: str
    source_region: str
    target_region: str
    target_zones: tuple[str, ...]
    corridor_score: float
    upstream_activity_score: float
    moisture_feed_score: float
    motion_alignment_score: float
    organization_score: float
    radar_confirmation_score: float
    lightning_confirmation_score: float
    estimated_arrival_hours: tuple[float, float]
    confidence: str
    interpretation: str


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        out = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(out) or math.isinf(out):
        return default
    return out


def _clamp01(value: float | None) -> float:
    if value is None:
        return 0.0
    return max(0.0, min(1.0, float(value)))


def _ramp(value: float | None, low: float, high: float) -> float:
    if value is None:
        return 0.0
    if high == low:
        return 1.0 if value >= high else 0.0
    return _clamp01((value - low) / (high - low))


def _inverse_ramp(value: float | None, high_risk_value: float, low_risk_value: float) -> float:
    if value is None:
        return 0.0
    if low_risk_value == high_risk_value:
        return 1.0 if value <= high_risk_value else 0.0
    return _clamp01((low_risk_value - value) / (low_risk_value - high_risk_value))


def _max_float(values: Any) -> float | None:
    if not isinstance(values, list):
        return None
    finite = [_safe_float(value) for value in values]
    nums = [value for value in finite if value is not None]
    return max(nums) if nums else None


def _min_float(values: Any) -> float | None:
    if not isinstance(values, list):
        return None
    finite = [_safe_float(value) for value in values]
    nums = [value for value in finite if value is not None]
    return min(nums) if nums else None


def _mean_float(values: Any) -> float | None:
    if not isinstance(values, list):
        return None
    finite = [_safe_float(value) for value in values]
    nums = [value for value in finite if value is not None]
    return sum(nums) / len(nums) if nums else None


def _angle_diff_deg(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _bearing_similarity(motion_to_deg: float | None, expected_bearing_deg: float) -> float:
    if motion_to_deg is None:
        return 0.0
    diff = _angle_diff_deg(motion_to_deg, expected_bearing_deg)
    return _clamp01(1.0 - diff / 90.0)


def _wind_to_uv(
    speed_ms: float | None, direction_from_deg: float | None
) -> tuple[float, float] | None:
    if speed_ms is None or direction_from_deg is None:
        return None
    radians = math.radians(direction_from_deg)
    u = -speed_ms * math.sin(radians)
    v = -speed_ms * math.cos(radians)
    return (u, v)


def _motion_to_from_wind(direction_from_deg: float | None) -> float | None:
    if direction_from_deg is None:
        return None
    return (direction_from_deg + 180.0) % 360.0


def _vector_shear_ms(
    speed_a: float | None,
    dir_a: float | None,
    speed_b: float | None,
    dir_b: float | None,
) -> float | None:
    va = _wind_to_uv(speed_a, dir_a)
    vb = _wind_to_uv(speed_b, dir_b)
    if va is None or vb is None:
        return None
    return math.hypot(vb[0] - va[0], vb[1] - va[1])


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def load_upstream_config(path: str | Path) -> dict[str, Any]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("upstream config must be a mapping")
    return payload


def _as_float(value: Any, default: float = 0.0) -> float:
    out = _safe_float(value)
    return float(default) if out is None else out


def _as_str(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _regions_from_config(config: dict[str, Any]) -> list[RegionProbe]:
    regions_raw = config.get("regions", [])
    if not isinstance(regions_raw, list):
        return []
    regions: list[RegionProbe] = []
    for item in regions_raw:
        if not isinstance(item, dict):
            continue
        region_id = _as_str(item.get("id")).strip()
        if not region_id:
            continue
        probe = item.get("probe") if isinstance(item.get("probe"), dict) else {}
        station_ids_raw = item.get("station_ids", [])
        station_ids = (
            tuple(
                str(station_id).strip() for station_id in station_ids_raw if str(station_id).strip()
            )
            if isinstance(station_ids_raw, list)
            else ()
        )
        regions.append(
            RegionProbe(
                region_id=region_id,
                name=_as_str(item.get("name"), region_id).strip() or region_id,
                lat=_as_float(probe.get("lat") if isinstance(probe, dict) else None),
                lon=_as_float(probe.get("lon") if isinstance(probe, dict) else None),
                role=_as_str(item.get("role", "upstream")).strip() or "upstream",
                weight=max(0.0, _as_float(item.get("weight"), 1.0)),
                station_ids=station_ids,
            )
        )
    return regions


def _corridors_from_config(config: dict[str, Any]) -> list[CorridorSpec]:
    corridors_raw = config.get("corridors", [])
    if not isinstance(corridors_raw, list):
        return []
    corridors: list[CorridorSpec] = []
    for item in corridors_raw:
        if not isinstance(item, dict):
            continue
        corridor_id = _as_str(item.get("id")).strip()
        source_region = _as_str(item.get("source_region")).strip()
        target_region = _as_str(item.get("target_region")).strip()
        if not corridor_id or not source_region or not target_region:
            continue
        zones_raw = item.get("target_zones", [])
        zones = tuple(str(zone) for zone in zones_raw) if isinstance(zones_raw, list) else ()
        lead_raw = item.get("lead_time_hours", [2.0, 6.0])
        if isinstance(lead_raw, list) and len(lead_raw) >= 2:
            lead = (_as_float(lead_raw[0], 2.0), _as_float(lead_raw[1], 6.0))
        else:
            lead = (2.0, 6.0)
        corridors.append(
            CorridorSpec(
                corridor_id=corridor_id,
                name=_as_str(item.get("name"), corridor_id).strip() or corridor_id,
                source_region=source_region,
                target_region=target_region,
                target_zones=zones,
                expected_bearing_deg=_as_float(item.get("expected_bearing_deg"), 45.0) % 360.0,
                distance_km=max(0.0, _as_float(item.get("distance_km"), 180.0)),
                lead_time_hours=(min(lead), max(lead)),
                weight=max(0.0, _as_float(item.get("weight"), 1.0)),
            )
        )
    return corridors


def build_openmeteo_upstream_url(
    lat: float,
    lon: float,
    *,
    forecast_hours: int = 12,
    timezone_name: str = DEFAULT_TIMEZONE,
    models: str = "best_match",
) -> str:
    params = {
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "hourly": ",".join(OPEN_METEO_UPSTREAM_VARIABLES),
        "forecast_hours": str(max(1, int(forecast_hours))),
        "timezone": timezone_name,
        "wind_speed_unit": "ms",
        "models": models,
    }
    return f"{OPEN_METEO_ENDPOINT}?{urlencode(params)}"


def _http_json(url: str, *, timeout_s: float) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": "MeteoVoid-UpstreamWatch/1.0"})
    with urlopen(request, timeout=timeout_s) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("HTTP JSON response must be an object")
    return payload


def _extract_indices_from_openmeteo(payload: dict[str, Any]) -> dict[str, float | None]:
    hourly_any = payload.get("hourly")
    hourly: dict[str, Any] = hourly_any if isinstance(hourly_any, dict) else {}
    t850 = _mean_float(hourly.get("temperature_850hPa"))
    td850 = _mean_float(hourly.get("dew_point_850hPa"))
    t700 = _mean_float(hourly.get("temperature_700hPa"))
    td700 = _mean_float(hourly.get("dew_point_700hPa"))
    t500 = _mean_float(hourly.get("temperature_500hPa"))
    z700 = _mean_float(hourly.get("geopotential_height_700hPa"))
    z500 = _mean_float(hourly.get("geopotential_height_500hPa"))
    depth_km = None
    if z700 is not None and z500 is not None and abs(z500 - z700) > 250.0:
        depth_km = abs(z500 - z700) / 1000.0
    lapse_rate = None
    if t700 is not None and t500 is not None and depth_km is not None:
        lapse_rate = (t700 - t500) / depth_km
    elif t700 is not None and t500 is not None:
        lapse_rate = (t700 - t500) / 2.6

    total_totals = None
    if t850 is not None and td850 is not None and t500 is not None:
        total_totals = t850 + td850 - 2.0 * t500
    k_index = None
    if (
        t850 is not None
        and td850 is not None
        and t700 is not None
        and td700 is not None
        and t500 is not None
    ):
        k_index = (t850 - t500) + td850 - (t700 - td700)

    shear_850_500 = _vector_shear_ms(
        _mean_float(hourly.get("wind_speed_850hPa")),
        _mean_float(hourly.get("wind_direction_850hPa")),
        _mean_float(hourly.get("wind_speed_500hPa")),
        _mean_float(hourly.get("wind_direction_500hPa")),
    )
    shear_850_300 = _vector_shear_ms(
        _mean_float(hourly.get("wind_speed_850hPa")),
        _mean_float(hourly.get("wind_direction_850hPa")),
        _mean_float(hourly.get("wind_speed_300hPa")),
        _mean_float(hourly.get("wind_direction_300hPa")),
    )
    motion_dir = _motion_to_from_wind(_mean_float(hourly.get("wind_direction_700hPa")))
    motion_speed = _mean_float(hourly.get("wind_speed_700hPa"))
    moisture_850 = _max_float(hourly.get("relative_humidity_850hPa"))
    moisture_925 = _max_float(hourly.get("relative_humidity_925hPa"))
    dewpoint_850 = _max_float(hourly.get("dew_point_850hPa"))

    return {
        "cape_j_kg": _max_float(hourly.get("cape")),
        "precipitation_probability_pct": _max_float(hourly.get("precipitation_probability")),
        "precipitation_mm": _max_float(hourly.get("precipitation")),
        "showers_mm": _max_float(hourly.get("showers")),
        "wind_gusts_10m_ms": _max_float(hourly.get("wind_gusts_10m")),
        "weather_code_max": _max_float(hourly.get("weather_code")),
        "dew_point_2m_c": _max_float(hourly.get("dew_point_2m")),
        "relative_humidity_2m_pct": _max_float(hourly.get("relative_humidity_2m")),
        "relative_humidity_850hpa_pct": moisture_850,
        "relative_humidity_925hpa_pct": moisture_925,
        "dew_point_850hpa_c": dewpoint_850,
        "total_totals_index_proxy": total_totals,
        "k_index_proxy_c": k_index,
        "lapse_rate_700_500_c_km": lapse_rate,
        "shear_850_500_ms_proxy": shear_850_500,
        "shear_850_300_ms_proxy": shear_850_300,
        "mean_motion_to_deg": motion_dir,
        "mean_motion_speed_ms": motion_speed,
    }


def _diagnostic_from_indices(
    region: RegionProbe, indices: dict[str, float | None], *, source_status: str
) -> RegionDiagnostic:
    cape = indices.get("cape_j_kg")
    precipitation_prob = indices.get("precipitation_probability_pct")
    precipitation = indices.get("precipitation_mm")
    showers = indices.get("showers_mm")
    weather_code = indices.get("weather_code_max")
    dew2m = indices.get("dew_point_2m_c")
    rh850 = indices.get("relative_humidity_850hpa_pct")
    rh925 = indices.get("relative_humidity_925hpa_pct")
    td850 = indices.get("dew_point_850hpa_c")
    total_totals = indices.get("total_totals_index_proxy")
    k_index = indices.get("k_index_proxy_c")
    lapse = indices.get("lapse_rate_700_500_c_km")
    shear500 = indices.get("shear_850_500_ms_proxy")
    shear300 = indices.get("shear_850_300_ms_proxy")

    thunder_code = 1.0 if weather_code is not None and weather_code >= 95.0 else 0.0
    shower_code = 0.6 if weather_code is not None and 80.0 <= weather_code < 90.0 else 0.0
    instability = _clamp01(
        0.34 * _ramp(cape, 400.0, 2200.0)
        + 0.18 * _ramp(total_totals, 44.0, 52.0)
        + 0.16 * _ramp(k_index, 24.0, 38.0)
        + 0.14 * _ramp(lapse, 6.3, 8.4)
        + 0.18 * max(thunder_code, shower_code)
    )
    moisture = _clamp01(
        0.34 * _ramp(dew2m, 15.0, 22.0)
        + 0.24 * _ramp(td850, 8.0, 16.0)
        + 0.22 * _ramp(rh850, 55.0, 88.0)
        + 0.20 * _ramp(rh925, 60.0, 92.0)
    )
    organization = _clamp01(
        0.48 * _ramp(shear500, 8.0, 22.0)
        + 0.32 * _ramp(shear300, 18.0, 42.0)
        + 0.20 * _ramp(indices.get("wind_gusts_10m_ms"), 12.0, 25.0)
    )
    cap_break = _clamp01(
        0.42 * _ramp(precipitation_prob, 30.0, 80.0)
        + 0.30 * _ramp(showers, 0.2, 8.0)
        + 0.18 * _ramp(precipitation, 1.0, 12.0)
        + 0.10 * max(thunder_code, shower_code)
    )

    # When no pressure-level fallback is available, the integrated Belgium report can still
    # provide a transparent surface proxy. This keeps the corridor layer useful in CI/offline
    # mode without pretending to have radar or upper-air data.
    surface_activity = indices.get("surface_station_score_proxy")
    surface_moisture = indices.get("surface_moisture_proxy")
    surface_convective = indices.get("surface_convective_proxy")
    if surface_activity is not None or surface_convective is not None:
        surface_signal = max(surface_activity or 0.0, surface_convective or 0.0)
        instability = max(instability, _clamp01(surface_convective))
        moisture = max(moisture, _clamp01(surface_moisture))
        cap_break = max(cap_break, _clamp01(surface_convective))
        organization = max(organization, 0.35 * _clamp01(surface_signal))

    upstream_activity = _clamp01(
        0.32 * instability + 0.26 * moisture + 0.22 * cap_break + 0.20 * organization
    )
    if surface_activity is not None or surface_convective is not None:
        upstream_activity = max(
            upstream_activity, _clamp01(max(surface_activity or 0.0, surface_convective or 0.0))
        )
    return RegionDiagnostic(
        region_id=region.region_id,
        name=region.name,
        lat=region.lat,
        lon=region.lon,
        data_mode="openmeteo_fallback" if source_status == "ok" else "surface_or_config_fallback",
        source_status=source_status,
        upstream_activity_score=round(upstream_activity, 6),
        moisture_feed_score=round(moisture, 6),
        instability_score=round(instability, 6),
        organization_score=round(organization, 6),
        cap_break_score=round(cap_break, 6),
        radar_confirmation_score=0.0,
        lightning_confirmation_score=0.0,
        mean_motion_to_deg=indices.get("mean_motion_to_deg"),
        mean_motion_speed_ms=indices.get("mean_motion_speed_ms"),
        indices={k: (round(v, 6) if v is not None else None) for k, v in indices.items()},
        evidence={
            "method": (
                "openmeteo_pressure_level_diagnostics"
                if source_status == "ok"
                else "belgium_report_surface_proxy"
            ),
            "pressure_level_note": "Shear and kinematic fields are pressure-level proxies, not dual-pol radar retrievals.",
        },
    )


def _diagnostic_from_report_stations(
    region: RegionProbe, report: dict[str, Any]
) -> RegionDiagnostic:
    stations_raw = report.get("stations", [])
    stations = (
        [s for s in stations_raw if isinstance(s, dict)] if isinstance(stations_raw, list) else []
    )
    tokens = [region.region_id.lower(), region.name.lower()]
    configured_ids = {station_id.lower() for station_id in region.station_ids}
    matched = [
        station
        for station in stations
        if str(station.get("station_id", "")).lower() in configured_ids
    ]
    if not matched:
        for station in stations:
            station_text = " ".join(
                str(station.get(key, "")).lower() for key in ("station_id", "name", "region")
            )
            if any(token and token.replace("_", " ") in station_text for token in tokens):
                matched.append(station)
    if not matched and region.region_id.startswith("BE_"):
        wanted = region.region_id.removeprefix("BE_")
        matched = [s for s in stations if wanted.lower() in str(s.get("station_id", "")).lower()]
    if not matched and region.role == "target":
        matched = stations[:]

    score_values = [_safe_float(s.get("score")) for s in matched]
    moisture_values = [_safe_float(s.get("components", {}).get("moisture")) for s in matched]
    convective_values = [_safe_float(s.get("convective_risk_score")) for s in matched]
    heat_values = [_safe_float(s.get("heat_stress_score")) for s in matched]
    activity = max([v for v in score_values if v is not None], default=0.0)
    moisture = max([v for v in moisture_values if v is not None], default=0.0)
    convective = max([v for v in convective_values if v is not None], default=activity)
    heat = max([v for v in heat_values if v is not None], default=0.0)
    indices = {
        "surface_station_score_proxy": activity,
        "surface_moisture_proxy": moisture,
        "surface_convective_proxy": convective,
        "surface_heat_proxy": heat,
        "mean_motion_to_deg": None,
        "mean_motion_speed_ms": None,
    }
    return _diagnostic_from_indices(region, indices, source_status="fallback_from_belgium_report")


def _fetch_region_diagnostic(
    region: RegionProbe,
    *,
    report: dict[str, Any],
    openmeteo_enabled: bool,
    forecast_hours: int,
    timezone_name: str,
    timeout_s: float,
    models: str,
) -> RegionDiagnostic:
    if not openmeteo_enabled:
        return _diagnostic_from_report_stations(region, report)
    try:
        url = build_openmeteo_upstream_url(
            region.lat,
            region.lon,
            forecast_hours=forecast_hours,
            timezone_name=timezone_name,
            models=models,
        )
        payload = _http_json(url, timeout_s=timeout_s)
        if bool(payload.get("error")):
            return _diagnostic_from_report_stations(region, report)
        diag = _diagnostic_from_indices(
            region, _extract_indices_from_openmeteo(payload), source_status="ok"
        )
        diag.evidence["openmeteo_url"] = url
        return diag
    except (OSError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return _diagnostic_from_report_stations(region, report)


def _confidence(
    score: float, source_statuses: list[str], radar_score: float, lightning_score: float
) -> str:
    ok_count = sum(1 for status in source_statuses if status == "ok")
    if score >= 0.72 and (ok_count > 0 or radar_score > 0.0 or lightning_score > 0.0):
        return "high"
    if score >= 0.46:
        return "medium"
    if score >= 0.28:
        return "low"
    return "very_low"


def _interpretation(corridor: CorridorSpec, score: float, confidence: str) -> str:
    if score >= 0.72:
        level = "signal amont fort"
    elif score >= 0.46:
        level = "signal amont à surveiller"
    elif score >= 0.28:
        level = "signal faible ou incomplet"
    else:
        level = "pas de signal amont structuré"
    return (
        f"{level} sur {corridor.name}. Fenêtre indicative "
        f"{corridor.lead_time_hours[0]:.0f}-{corridor.lead_time_hours[1]:.0f} h, "
        f"confiance {confidence}."
    )


def _corridor_diagnostic(
    corridor: CorridorSpec,
    regions: dict[str, RegionDiagnostic],
    radar_score: float,
    lightning_score: float,
) -> CorridorDiagnostic:
    source = regions.get(corridor.source_region)
    target = regions.get(corridor.target_region)
    source_activity = source.upstream_activity_score if source is not None else 0.0
    source_moisture = source.moisture_feed_score if source is not None else 0.0
    organization = source.organization_score if source is not None else 0.0
    target_activity = target.upstream_activity_score if target is not None else 0.0
    motion_to = source.mean_motion_to_deg if source is not None else None
    motion_alignment = _bearing_similarity(motion_to, corridor.expected_bearing_deg)
    score = _clamp01(
        0.34 * source_activity
        + 0.20 * source_moisture
        + 0.18 * motion_alignment
        + 0.12 * organization
        + 0.06 * target_activity
        + 0.06 * radar_score
        + 0.04 * lightning_score
    )
    statuses = []
    if source is not None:
        statuses.append(source.source_status)
    if target is not None:
        statuses.append(target.source_status)
    conf = _confidence(score, statuses, radar_score, lightning_score)
    return CorridorDiagnostic(
        corridor_id=corridor.corridor_id,
        name=corridor.name,
        source_region=corridor.source_region,
        target_region=corridor.target_region,
        target_zones=corridor.target_zones,
        corridor_score=round(score, 6),
        upstream_activity_score=round(source_activity, 6),
        moisture_feed_score=round(source_moisture, 6),
        motion_alignment_score=round(motion_alignment, 6),
        organization_score=round(organization, 6),
        radar_confirmation_score=round(radar_score, 6),
        lightning_confirmation_score=round(lightning_score, 6),
        estimated_arrival_hours=corridor.lead_time_hours,
        confidence=conf,
        interpretation=_interpretation(corridor, score, conf),
    )


def _load_radar_sources(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {"sources": []}
    p = Path(path)
    if not p.exists():
        return {"sources": []}
    payload = yaml.safe_load(p.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {"sources": []}


def _score_confirmation(value: str) -> float:
    mapping = {
        "none": 0.0,
        "unknown": 0.0,
        "weak": 0.25,
        "nearby": 0.35,
        "moderate": 0.55,
        "confirmed": 0.75,
        "strong": 0.9,
        "severe": 1.0,
    }
    return mapping.get(value.lower().strip(), 0.0)


def inspect_radar_interfaces(path: str | Path | None, *, timeout_s: float = 5.0) -> dict[str, Any]:
    config = _load_radar_sources(path)
    sources_raw = config.get("sources", [])
    sources = (
        [item for item in sources_raw if isinstance(item, dict)]
        if isinstance(sources_raw, list)
        else []
    )
    statuses: list[dict[str, Any]] = []
    best_radar = 0.0
    best_lightning = 0.0
    for source in sources:
        name = _as_str(source.get("name"), "unnamed")
        kind = _as_str(source.get("kind"), "radar")
        endpoint_env = _as_str(source.get("endpoint_env"))
        endpoint_url = _as_str(source.get("endpoint_url")) or os.getenv(endpoint_env, "")
        status = {
            "name": name,
            "kind": kind,
            "configured": bool(endpoint_url),
            "status": "interface_only_unconfigured",
            "public_info_url": _as_str(source.get("public_info_url")),
            "endpoint_env": endpoint_env,
            "license_note": _as_str(source.get("license_note")),
            "detail": "No endpoint configured; no radar value is invented.",
            "confirmation_score": 0.0,
        }
        if endpoint_url:
            try:
                payload = _http_json(endpoint_url, timeout_s=timeout_s)
                value = str(
                    payload.get("confirmation")
                    or payload.get("radar_confirmation")
                    or payload.get("lightning_confirmation")
                    or payload.get("status")
                    or "unknown"
                )
                score = _score_confirmation(value)
                status.update(
                    {
                        "status": "ok",
                        "detail": value,
                        "confirmation_score": score,
                        "last_update": payload.get("last_update") or payload.get("generated_at"),
                        "product": payload.get("product"),
                    }
                )
            except (OSError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
                status.update({"status": "error", "detail": str(exc)[:180]})
        score = _safe_float(status.get("confirmation_score"), 0.0) or 0.0
        if kind == "lightning":
            best_lightning = max(best_lightning, score)
        else:
            best_radar = max(best_radar, score)
        statuses.append(status)
    return {
        "contract": "european_radar_interface_optional_v1",
        "radar_confirmation_score": round(best_radar, 6),
        "lightning_confirmation_score": round(best_lightning, 6),
        "sources": statuses,
        "limits": [
            "No European radar value is synthesized when no licensed endpoint is configured.",
            "OPERA/national radar products require access and licence checks before operational use.",
        ],
    }


def _region_to_dict(diag: RegionDiagnostic) -> dict[str, Any]:
    return {
        "region_id": diag.region_id,
        "name": diag.name,
        "lat": diag.lat,
        "lon": diag.lon,
        "data_mode": diag.data_mode,
        "source_status": diag.source_status,
        "upstream_activity_score": diag.upstream_activity_score,
        "moisture_feed_score": diag.moisture_feed_score,
        "instability_score": diag.instability_score,
        "organization_score": diag.organization_score,
        "cap_break_score": diag.cap_break_score,
        "radar_confirmation_score": diag.radar_confirmation_score,
        "lightning_confirmation_score": diag.lightning_confirmation_score,
        "mean_motion_to_deg": diag.mean_motion_to_deg,
        "mean_motion_speed_ms": diag.mean_motion_speed_ms,
        "indices": diag.indices,
        "evidence": diag.evidence,
    }


def _corridor_to_dict(diag: CorridorDiagnostic) -> dict[str, Any]:
    return {
        "corridor_id": diag.corridor_id,
        "name": diag.name,
        "source_region": diag.source_region,
        "target_region": diag.target_region,
        "target_zones": list(diag.target_zones),
        "corridor_score": diag.corridor_score,
        "upstream_activity_score": diag.upstream_activity_score,
        "moisture_feed_score": diag.moisture_feed_score,
        "motion_alignment_score": diag.motion_alignment_score,
        "organization_score": diag.organization_score,
        "radar_confirmation_score": diag.radar_confirmation_score,
        "lightning_confirmation_score": diag.lightning_confirmation_score,
        "estimated_arrival_hours": list(diag.estimated_arrival_hours),
        "confidence": diag.confidence,
        "interpretation": diag.interpretation,
    }


def build_upstream_watch(
    report: dict[str, Any],
    *,
    upstream_config_path: str | Path = "config/upstream_regions.yaml",
    radar_sources_config_path: str | Path | None = "config/european_radar_sources.yaml",
    openmeteo_enabled: bool = False,
    forecast_hours: int = 12,
    timezone_name: str = DEFAULT_TIMEZONE,
    timeout_s: float = 8.0,
    models: str = "best_match",
) -> dict[str, Any]:
    config = load_upstream_config(upstream_config_path)
    regions = _regions_from_config(config)
    corridors = _corridors_from_config(config)
    radar = inspect_radar_interfaces(radar_sources_config_path, timeout_s=timeout_s)
    radar_score = _safe_float(radar.get("radar_confirmation_score"), 0.0) or 0.0
    lightning_score = _safe_float(radar.get("lightning_confirmation_score"), 0.0) or 0.0
    region_diagnostics = [
        _fetch_region_diagnostic(
            region,
            report=report,
            openmeteo_enabled=openmeteo_enabled,
            forecast_hours=forecast_hours,
            timezone_name=timezone_name,
            timeout_s=timeout_s,
            models=models,
        )
        for region in regions
    ]
    region_by_id = {diag.region_id: diag for diag in region_diagnostics}
    corridor_diagnostics = [
        _corridor_diagnostic(corridor, region_by_id, radar_score, lightning_score)
        for corridor in corridors
    ]
    max_corridor = max((c.corridor_score for c in corridor_diagnostics), default=0.0)
    top = sorted(corridor_diagnostics, key=lambda c: c.corridor_score, reverse=True)[:5]
    data_modes = sorted({diag.data_mode for diag in region_diagnostics})
    generated_at = datetime.now(UTC).astimezone().isoformat(timespec="seconds")
    return {
        "contract": "european_upstream_watch_v1",
        "generated_at": generated_at,
        "target_window": report.get("target_window"),
        "data_mode": (
            "openmeteo_fallback_enabled" if openmeteo_enabled else "report_surface_fallback_only"
        ),
        "openmeteo": {
            "enabled": bool(openmeteo_enabled),
            "forecast_hours": int(forecast_hours),
            "timezone": timezone_name,
            "models": models,
            "variables": OPEN_METEO_UPSTREAM_VARIABLES,
            "documentation_note": "Uses documented Open-Meteo hourly and pressure-level variables when live fallback is enabled.",
        },
        "radar_interface": radar,
        "summary": {
            "max_corridor_score": round(max_corridor, 6),
            "top_corridors": [_corridor_to_dict(c) for c in top],
            "region_count": len(region_diagnostics),
            "corridor_count": len(corridor_diagnostics),
            "data_modes": data_modes,
            "limits": [
                "This is an upstream diagnostic, not an official warning.",
                "Radar/foudre are only used when configured; otherwise no confirmation is invented.",
                "Open-Meteo pressure-level fields improve airflow diagnostics but do not replace radar velocity products.",
            ],
        },
        "regions": [_region_to_dict(diag) for diag in region_diagnostics],
        "corridors": [_corridor_to_dict(diag) for diag in corridor_diagnostics],
    }


def _score_color(score: float) -> str:
    if score >= 0.72:
        return "#d4332f"
    if score >= 0.46:
        return "#e2741f"
    if score >= 0.28:
        return "#e0a31a"
    return "#2f6fd0"


def _map_project(lat: float, lon: float) -> tuple[float, float]:
    lon_min, lon_max = -5.5, 11.0
    lat_min, lat_max = 43.0, 55.8
    x = (lon - lon_min) / (lon_max - lon_min) * 1000.0
    y = (lat_max - lat) / (lat_max - lat_min) * 760.0
    return (max(0.0, min(1000.0, x)), max(0.0, min(760.0, y)))


def _write_html_map(watch: dict[str, Any], path: Path) -> None:
    regions = [r for r in watch.get("regions", []) if isinstance(r, dict)]
    corridors = [c for c in watch.get("corridors", []) if isinstance(c, dict)]
    region_lookup = {str(r.get("region_id")): r for r in regions}
    lines = []
    circles = []
    labels = []
    for corridor in corridors:
        source = region_lookup.get(str(corridor.get("source_region")))
        target = region_lookup.get(str(corridor.get("target_region")))
        if not source or not target:
            continue
        sx, sy = _map_project(_as_float(source.get("lat")), _as_float(source.get("lon")))
        tx, ty = _map_project(_as_float(target.get("lat")), _as_float(target.get("lon")))
        score = _as_float(corridor.get("corridor_score"))
        color = _score_color(score)
        width = 2.0 + 5.0 * _clamp01(score)
        lines.append(
            f'<line x1="{sx:.1f}" y1="{sy:.1f}" x2="{tx:.1f}" y2="{ty:.1f}" '
            f'stroke="{color}" stroke-width="{width:.1f}" stroke-opacity="0.72" />'
        )
    for region in regions:
        x, y = _map_project(_as_float(region.get("lat")), _as_float(region.get("lon")))
        score = _as_float(region.get("upstream_activity_score"))
        color = _score_color(score)
        radius = 6.0 + 11.0 * _clamp01(score)
        name = str(region.get("name") or region.get("region_id") or "")
        circles.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" fill="{color}" '
            f'fill-opacity="0.84"><title>{name} · score {score:.2f}</title></circle>'
        )
        labels.append(
            f'<text x="{x + 10:.1f}" y="{y - 8:.1f}" font-size="12" fill="#162033">'
            f"{name}</text>"
        )
    top = (
        watch.get("summary", {}).get("top_corridors", [])
        if isinstance(watch.get("summary"), dict)
        else []
    )
    top_items = []
    for item in top[:5] if isinstance(top, list) else []:
        if isinstance(item, dict):
            top_items.append(
                f"<li><strong>{item.get('name')}</strong> — score "
                f"{_as_float(item.get('corridor_score')):.2f}, confiance {item.get('confidence')}</li>"
            )
    html = f"""<!doctype html>
<html lang=\"fr\">
<head>
<meta charset=\"utf-8\" />
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
<title>MeteoVoid · Europe amont</title>
<style>
body{{margin:0;font-family:Inter,Segoe UI,Arial,sans-serif;background:#eef3f8;color:#162033}}
main{{max-width:1180px;margin:0 auto;padding:24px}}
.card{{background:white;border:1px solid #d9e3ef;border-radius:18px;padding:18px;margin:14px 0;box-shadow:0 12px 30px rgba(13,32,60,.08)}}
svg{{width:100%;height:auto;background:linear-gradient(180deg,#dfefff,#f7fbff);border-radius:18px;border:1px solid #cfdcec}}
.muted{{color:#607086}}
.grid{{display:grid;grid-template-columns:2fr 1fr;gap:18px}}
@media(max-width:900px){{.grid{{grid-template-columns:1fr}}}}
</style>
</head>
<body><main>
<h1>Europe amont · Upstream Watch</h1>
<p class=\"muted\">Carte diagnostique : régions sources, couloirs vers la Belgique, score de corridor. Les données radar fines ne sont pas inventées : elles ne sont utilisées que si une interface configurée les fournit.</p>
<div class=\"grid\"><div class=\"card\">
<svg viewBox=\"0 0 1000 760\" role=\"img\" aria-label=\"Carte Europe amont\">
<rect x=\"0\" y=\"0\" width=\"1000\" height=\"760\" fill=\"#f7fbff\" />
<text x=\"40\" y=\"70\" font-size=\"24\" fill=\"#8aa0b8\">Atlantique / Manche</text>
<text x=\"395\" y=\"420\" font-size=\"28\" fill=\"#b0bdc9\">France</text>
<text x=\"590\" y=\"250\" font-size=\"22\" fill=\"#9aaec3\">Belgique</text>
<text x=\"700\" y=\"355\" font-size=\"22\" fill=\"#a8b6c5\">Allemagne</text>
{''.join(lines)}
{''.join(circles)}
{''.join(labels)}
</svg></div>
<div class=\"card\"><h2>Couloirs prioritaires</h2><ol>{''.join(top_items)}</ol><p class=\"muted\">Rouge/orange = signal amont plus structuré. Bleu = signal faible ou incomplet.</p></div></div>
<div class=\"card\"><h2>Limites</h2><p>Cette carte combine régions amont, scores de corridor, flux Open‑Meteo si activé et interfaces radar/foudre si configurées. Elle ne remplace pas OPERA, IRM/KMI, MeteoAlarm ou un produit radar national.</p></div>
</main></body></html>"""
    path.write_text(html, encoding="utf-8")


def _write_markdown_report(watch: dict[str, Any], path: Path) -> None:
    summary_any = watch.get("summary")
    summary: dict[str, Any] = summary_any if isinstance(summary_any, dict) else {}
    lines = [
        "# MeteoVoid · European Upstream Watch",
        "",
        "Diagnostic amont expérimental. Ce rapport ne constitue pas une alerte officielle.",
        "",
        f"- Généré : `{watch.get('generated_at')}`",
        f"- Mode données : `{watch.get('data_mode')}`",
        f"- Score corridor max : `{_as_float(summary.get('max_corridor_score')):.3f}`",
        "",
        "## Couloirs prioritaires",
        "",
    ]
    top = summary.get("top_corridors", [])
    if isinstance(top, list) and top:
        for item in top:
            if isinstance(item, dict):
                lines.append(
                    f"- **{item.get('name')}** : score `{_as_float(item.get('corridor_score')):.3f}`, "
                    f"confiance `{item.get('confidence')}` — {item.get('interpretation')}"
                )
    else:
        lines.append("- Aucun couloir structuré détecté.")
    lines.extend(
        [
            "",
            "## Radar européen / foudre",
            "",
            "Les interfaces radar/foudre sont optionnelles. Si aucun endpoint licencié n’est configuré, aucun signal radar n’est simulé.",
            "",
            "## Limites",
            "",
            "- Les variables Open‑Meteo de pression améliorent la lecture des flux, mais ne remplacent pas les vitesses Doppler radar.",
            "- Les indices calculés depuis les niveaux de pression sont des diagnostics/proxys lorsque l’indice natif n’est pas livré.",
            "- La décision publique doit rester alignée sur les sources officielles.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_corridor_csv(watch: dict[str, Any], path: Path) -> None:
    corridors = [c for c in watch.get("corridors", []) if isinstance(c, dict)]
    fields = [
        "corridor_id",
        "name",
        "source_region",
        "target_region",
        "corridor_score",
        "upstream_activity_score",
        "moisture_feed_score",
        "motion_alignment_score",
        "organization_score",
        "radar_confirmation_score",
        "lightning_confirmation_score",
        "confidence",
        "interpretation",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in corridors:
            writer.writerow({field: row.get(field) for field in fields})


def write_upstream_watch_outputs(
    report: dict[str, Any],
    out_dir: str | Path,
    *,
    upstream_config_path: str | Path = "config/upstream_regions.yaml",
    radar_sources_config_path: str | Path | None = "config/european_radar_sources.yaml",
    openmeteo_enabled: bool = False,
    forecast_hours: int = 12,
    timezone_name: str = DEFAULT_TIMEZONE,
    timeout_s: float = 8.0,
    models: str = "best_match",
) -> dict[str, Any]:
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    watch = build_upstream_watch(
        report,
        upstream_config_path=upstream_config_path,
        radar_sources_config_path=radar_sources_config_path,
        openmeteo_enabled=openmeteo_enabled,
        forecast_hours=forecast_hours,
        timezone_name=timezone_name,
        timeout_s=timeout_s,
        models=models,
    )
    (root / "upstream_watch.json").write_text(_json_dumps(watch), encoding="utf-8")
    (root / "european_radar_sources_status.json").write_text(
        _json_dumps(watch.get("radar_interface", {})), encoding="utf-8"
    )
    _write_markdown_report(watch, root / "upstream_watch_report.md")
    _write_html_map(watch, root / "european_upstream_map.html")
    _write_corridor_csv(watch, root / "upstream_corridors.csv")
    return watch
