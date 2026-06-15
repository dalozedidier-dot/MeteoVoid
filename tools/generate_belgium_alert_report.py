from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import shutil
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src") if (_ROOT / "src").exists() else str(_ROOT))

from meteovoid.stations_config import StationSpec, load_stations_config  # noqa: E402

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
DEFAULT_TIMEZONE = "Europe/Brussels"
HOURLY_VARIABLES = [
    "temperature_2m",
    "relative_humidity_2m",
    "dew_point_2m",
    "precipitation_probability",
    "precipitation",
    "rain",
    "showers",
    "weather_code",
    "pressure_msl",
    "wind_speed_10m",
    "wind_gusts_10m",
]
THUNDERSTORM_CODES = {95, 96, 99}
SHOWER_CODES = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82}
SEVERITY_RANK = {"normal": 0, "watch": 1, "medium": 2, "high": 3, "alert": 4}
SEVERITY_COLORS = {
    "normal": "#6BA36B",
    "watch": "#C4B54B",
    "medium": "#E5933A",
    "high": "#D85646",
    "alert": "#6E3FA0",
}
BE_OUTLINE_LON_LAT = [
    (2.56, 51.09),
    (3.25, 51.37),
    (4.25, 51.50),
    (5.25, 51.34),
    (6.42, 50.75),
    (6.13, 49.50),
    (5.10, 49.48),
    (4.15, 49.77),
    (3.20, 49.95),
    (2.55, 50.73),
]


@dataclass(frozen=True)
class TargetWindow:
    start: date
    end: date
    label: str


@dataclass(frozen=True)
class StationRisk:
    station_id: str
    name: str
    region: str
    lat: float
    lon: float
    worst_time: str | None
    score: float
    severity: str
    max_temperature_c: float | None
    max_dew_point_c: float | None
    max_relative_humidity_pct: float | None
    max_precip_probability_pct: float | None
    max_precipitation_mm_h: float | None
    max_wind_gust_ms: float | None
    max_pressure_drop_6h_hpa: float | None
    thunderstorm_code_seen: bool
    shower_code_seen: bool
    components: dict[str, float]
    signals: list[str]
    source_ok: bool
    error: str | None = None


def _today() -> date:
    return datetime.now().date()


def _next_weekday(start: date, weekday: int) -> date:
    delta = (weekday - start.weekday()) % 7
    return start + timedelta(days=delta)


def _parse_target_window(raw: str, *, horizon_days: int) -> TargetWindow:
    value = raw.strip().lower()
    today = _today()
    if value == "auto":
        end = today + timedelta(days=max(0, int(horizon_days) - 1))
        return TargetWindow(
            start=today, end=end, label=f"auto_{today.isoformat()}_{end.isoformat()}"
        )
    if value == "today":
        return TargetWindow(start=today, end=today, label=today.isoformat())
    if value == "tomorrow":
        tomorrow = today + timedelta(days=1)
        return TargetWindow(start=tomorrow, end=tomorrow, label=tomorrow.isoformat())
    if value in {"next-friday", "friday", "vendredi"}:
        friday = _next_weekday(today, 4)
        return TargetWindow(start=friday, end=friday, label=friday.isoformat())
    try:
        exact = date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"Invalid --target-date value: {raw}") from exc
    return TargetWindow(start=exact, end=exact, label=exact.isoformat())


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _max_number(values: list[Any]) -> float | None:
    nums = [_safe_float(v) for v in values]
    finite = [v for v in nums if v is not None]
    return max(finite) if finite else None


def _min_number(values: list[Any]) -> float | None:
    nums = [_safe_float(v) for v in values]
    finite = [v for v in nums if v is not None]
    return min(finite) if finite else None


def _clamp01(value: float) -> float:
    if value <= 0.0:
        return 0.0
    if value >= 1.0:
        return 1.0
    return float(value)


def _ramp(value: float | None, watch: float, alert: float) -> float:
    if value is None:
        return 0.0
    if alert <= watch:
        return 1.0 if value >= alert else 0.0
    return _clamp01((float(value) - float(watch)) / (float(alert) - float(watch)))


def _pressure_drop_6h(values: list[Any]) -> float | None:
    nums = [_safe_float(v) for v in values]
    series = [v for v in nums if v is not None]
    if len(series) < 7:
        return None
    drops: list[float] = []
    for i in range(6, len(series)):
        drops.append(float(series[i - 6] - series[i]))
    positive = [x for x in drops if x > 0]
    return max(positive) if positive else 0.0


def _http_json(url: str, *, timeout_s: float) -> dict[str, Any]:
    req = Request(
        url, headers={"Accept": "application/json", "User-Agent": "MeteoVoid/BelgiumAlert"}
    )
    with urlopen(req, timeout=timeout_s) as response:  # noqa: S310
        text = response.read().decode("utf-8", errors="replace")
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("Open-Meteo response is not a JSON object")
    if payload.get("error") is True:
        reason = payload.get("reason")
        raise ValueError(str(reason) if reason else "Open-Meteo returned an error")
    return payload


def _build_openmeteo_forecast_url(
    station: StationSpec,
    *,
    target: TargetWindow,
    timezone: str,
) -> str:
    params = {
        "latitude": f"{station.lat:.6f}",
        "longitude": f"{station.lon:.6f}",
        "hourly": ",".join(HOURLY_VARIABLES),
        "wind_speed_unit": "ms",
        "temperature_unit": "celsius",
        "precipitation_unit": "mm",
        "timezone": timezone,
        "start_date": target.start.isoformat(),
        "end_date": target.end.isoformat(),
    }
    return OPEN_METEO_URL + "?" + urlencode(params)


def _offline_payload(station: StationSpec, *, target: TargetWindow) -> dict[str, Any]:
    times: list[str] = []
    temp: list[float] = []
    humidity: list[float] = []
    dew: list[float] = []
    precip_prob: list[float] = []
    precip: list[float] = []
    rain: list[float] = []
    showers: list[float] = []
    weather: list[int] = []
    pressure: list[float] = []
    wind: list[float] = []
    gust: list[float] = []

    cur = target.start
    while cur <= target.end:
        for hour in range(24):
            times.append(f"{cur.isoformat()}T{hour:02d}:00")
            diurnal = 1.0 if 13 <= hour <= 19 else 0.0
            unstable = 1.0 if 15 <= hour <= 21 else 0.0
            approach_bonus = 1.5 if station.region.startswith("approach") else 0.0
            temp.append(24.0 + 8.0 * diurnal + approach_bonus)
            humidity.append(58.0 + 22.0 * unstable)
            dew.append(15.0 + 5.0 * unstable)
            precip_prob.append(18.0 + 55.0 * unstable)
            precip.append(0.2 + 7.0 * unstable)
            rain.append(0.1 + 5.0 * unstable)
            showers.append(0.0 + 6.0 * unstable)
            weather.append(95 if unstable else 3)
            pressure.append(1014.0 - (hour * 0.9 if 10 <= hour <= 19 else hour * 0.1))
            wind.append(4.0 + 3.0 * unstable)
            gust.append(9.0 + 10.0 * unstable + approach_bonus)
        cur += timedelta(days=1)

    return {
        "hourly": {
            "time": times,
            "temperature_2m": temp,
            "relative_humidity_2m": humidity,
            "dew_point_2m": dew,
            "precipitation_probability": precip_prob,
            "precipitation": precip,
            "rain": rain,
            "showers": showers,
            "weather_code": weather,
            "pressure_msl": pressure,
            "wind_speed_10m": wind,
            "wind_gusts_10m": gust,
        }
    }


def _station_risk_from_payload(station: StationSpec, payload: dict[str, Any]) -> StationRisk:
    hourly_any = payload.get("hourly")
    if not isinstance(hourly_any, dict):
        raise ValueError("Missing hourly forecast in response")

    times_any = hourly_any.get("time")
    times = [str(x) for x in times_any] if isinstance(times_any, list) else []
    temperatures = hourly_any.get("temperature_2m", [])
    humidity = hourly_any.get("relative_humidity_2m", [])
    dew_points = hourly_any.get("dew_point_2m", [])
    precipitation_probability = hourly_any.get("precipitation_probability", [])
    precipitation = hourly_any.get("precipitation", [])
    rain = hourly_any.get("rain", [])
    showers = hourly_any.get("showers", [])
    weather_codes_any = hourly_any.get("weather_code", [])
    pressure = hourly_any.get("pressure_msl", [])
    wind_gusts = hourly_any.get("wind_gusts_10m", [])

    max_temp = _max_number(temperatures if isinstance(temperatures, list) else [])
    max_humidity = _max_number(humidity if isinstance(humidity, list) else [])
    max_dew = _max_number(dew_points if isinstance(dew_points, list) else [])
    max_precip_prob = _max_number(
        precipitation_probability if isinstance(precipitation_probability, list) else []
    )
    max_precip = max(
        _max_number(precipitation if isinstance(precipitation, list) else []) or 0.0,
        _max_number(rain if isinstance(rain, list) else []) or 0.0,
        _max_number(showers if isinstance(showers, list) else []) or 0.0,
    )
    max_gust = _max_number(wind_gusts if isinstance(wind_gusts, list) else [])
    pressure_drop = _pressure_drop_6h(pressure if isinstance(pressure, list) else [])
    weather_codes = (
        [_safe_int(v) for v in weather_codes_any] if isinstance(weather_codes_any, list) else []
    )
    codes = {v for v in weather_codes if v is not None}
    thunderstorm = bool(codes & THUNDERSTORM_CODES)
    showers_seen = bool(codes & SHOWER_CODES)

    components = {
        "heat": _ramp(max_temp, 28.0, 34.0),
        "moisture": max(_ramp(max_dew, 16.0, 21.0), _ramp(max_humidity, 65.0, 90.0) * 0.75),
        "precipitation": max(_ramp(max_precip_prob, 35.0, 75.0), _ramp(max_precip, 4.0, 18.0)),
        "wind_gust": _ramp(max_gust, 15.0, 25.0),
        "pressure_drop": _ramp(pressure_drop, 3.0, 8.0),
        "weather_code": 1.0 if thunderstorm else (0.45 if showers_seen else 0.0),
    }
    weights = {
        "heat": 0.18,
        "moisture": 0.17,
        "precipitation": 0.20,
        "wind_gust": 0.15,
        "pressure_drop": 0.15,
        "weather_code": 0.15,
    }
    score = sum(components[k] * weights[k] for k in weights)
    score = round(_clamp01(score), 6)
    severity = _severity_from_score(score)
    signals = _signals_from_components(
        components=components,
        max_temp=max_temp,
        max_dew=max_dew,
        max_precip_prob=max_precip_prob,
        max_precip=max_precip,
        max_gust=max_gust,
        pressure_drop=pressure_drop,
        thunderstorm=thunderstorm,
        showers_seen=showers_seen,
    )

    worst_time = _worst_time(
        times=times,
        temperatures=temperatures if isinstance(temperatures, list) else [],
        dew_points=dew_points if isinstance(dew_points, list) else [],
        precipitation_probability=(
            precipitation_probability if isinstance(precipitation_probability, list) else []
        ),
        wind_gusts=wind_gusts if isinstance(wind_gusts, list) else [],
        weather_codes=weather_codes_any if isinstance(weather_codes_any, list) else [],
    )

    return StationRisk(
        station_id=station.station_id,
        name=station.name,
        region=station.region,
        lat=float(station.lat),
        lon=float(station.lon),
        worst_time=worst_time,
        score=score,
        severity=severity,
        max_temperature_c=max_temp,
        max_dew_point_c=max_dew,
        max_relative_humidity_pct=max_humidity,
        max_precip_probability_pct=max_precip_prob,
        max_precipitation_mm_h=max_precip,
        max_wind_gust_ms=max_gust,
        max_pressure_drop_6h_hpa=pressure_drop,
        thunderstorm_code_seen=thunderstorm,
        shower_code_seen=showers_seen,
        components={k: round(v, 6) for k, v in components.items()},
        signals=signals,
        source_ok=True,
    )


def _severity_from_score(score: float) -> str:
    if score >= 0.78:
        return "alert"
    if score >= 0.65:
        return "high"
    if score >= 0.50:
        return "medium"
    if score >= 0.35:
        return "watch"
    return "normal"


def _signals_from_components(
    *,
    components: dict[str, float],
    max_temp: float | None,
    max_dew: float | None,
    max_precip_prob: float | None,
    max_precip: float | None,
    max_gust: float | None,
    pressure_drop: float | None,
    thunderstorm: bool,
    showers_seen: bool,
) -> list[str]:
    signals: list[str] = []
    if components["heat"] >= 0.5:
        signals.append(
            f"chaleur marquée, Tmax {max_temp:.1f} °C" if max_temp else "chaleur marquée"
        )
    if components["moisture"] >= 0.5:
        signals.append(
            f"humidité lourde, point de rosée {max_dew:.1f} °C" if max_dew else "humidité lourde"
        )
    if components["precipitation"] >= 0.5:
        if max_precip_prob is not None:
            signals.append(f"probabilité de précipitation {max_precip_prob:.0f} %")
        elif max_precip is not None:
            signals.append(f"précipitation horaire possible {max_precip:.1f} mm")
    if components["wind_gust"] >= 0.5:
        signals.append(f"rafales possibles {max_gust:.1f} m/s" if max_gust else "rafales possibles")
    if components["pressure_drop"] >= 0.5:
        signals.append(
            f"baisse de pression sur 6 h {pressure_drop:.1f} hPa"
            if pressure_drop is not None
            else "baisse de pression"
        )
    if thunderstorm:
        signals.append("code météo Open-Meteo orageux")
    elif showers_seen:
        signals.append("code météo averses/pluie convective")
    if not signals:
        signals.append("aucun signal fort dans les variables disponibles")
    return signals


def _worst_time(
    *,
    times: list[str],
    temperatures: list[Any],
    dew_points: list[Any],
    precipitation_probability: list[Any],
    wind_gusts: list[Any],
    weather_codes: list[Any],
) -> str | None:
    if not times:
        return None
    best_idx = 0
    best_score = -1.0
    n = len(times)
    for i in range(n):
        temp = _safe_float(temperatures[i]) if i < len(temperatures) else None
        dew = _safe_float(dew_points[i]) if i < len(dew_points) else None
        prob = (
            _safe_float(precipitation_probability[i])
            if i < len(precipitation_probability)
            else None
        )
        gust = _safe_float(wind_gusts[i]) if i < len(wind_gusts) else None
        code = _safe_int(weather_codes[i]) if i < len(weather_codes) else None
        score = (
            _ramp(temp, 28.0, 34.0) * 0.20
            + _ramp(dew, 16.0, 21.0) * 0.20
            + _ramp(prob, 35.0, 75.0) * 0.25
            + _ramp(gust, 15.0, 25.0) * 0.15
            + (1.0 if code in THUNDERSTORM_CODES else 0.0) * 0.20
        )
        if score > best_score:
            best_idx = i
            best_score = score
    return times[best_idx]


def _failed_station(station: StationSpec, error: str) -> StationRisk:
    return StationRisk(
        station_id=station.station_id,
        name=station.name,
        region=station.region,
        lat=float(station.lat),
        lon=float(station.lon),
        worst_time=None,
        score=0.0,
        severity="normal",
        max_temperature_c=None,
        max_dew_point_c=None,
        max_relative_humidity_pct=None,
        max_precip_probability_pct=None,
        max_precipitation_mm_h=None,
        max_wind_gust_ms=None,
        max_pressure_drop_6h_hpa=None,
        thunderstorm_code_seen=False,
        shower_code_seen=False,
        components={},
        signals=[],
        source_ok=False,
        error=error,
    )


def _aggregate_risk(stations: list[StationRisk]) -> dict[str, Any]:
    ok = [s for s in stations if s.source_ok]
    if not ok:
        return {
            "score": 0.0,
            "severity": "normal",
            "source_ok_count": 0,
            "source_error_count": len(stations),
            "top_stations": [],
        }
    ordered = sorted(ok, key=lambda x: x.score, reverse=True)
    top = ordered[:5]
    max_score = top[0].score
    mean_top = sum(s.score for s in top) / len(top)
    score = round(_clamp01(max_score * 0.65 + mean_top * 0.35), 6)
    severity = _severity_from_score(score)
    return {
        "score": score,
        "severity": severity,
        "source_ok_count": len(ok),
        "source_error_count": len(stations) - len(ok),
        "top_stations": [s.station_id for s in top],
    }


def _fmt(value: Any, digits: int = 1) -> str:
    number = _safe_float(value)
    if number is None:
        return "n/a"
    return f"{number:.{digits}f}"


def _severity_color(severity: str) -> str:
    return SEVERITY_COLORS.get(str(severity), "#999999")


def _map_bounds(stations: list[dict[str, Any]]) -> tuple[float, float, float, float]:
    lons = [_safe_float(s.get("lon")) for s in stations]
    lats = [_safe_float(s.get("lat")) for s in stations]
    finite_lons = [x for x in lons if x is not None]
    finite_lats = [x for x in lats if x is not None]
    if not finite_lons or not finite_lats:
        return (2.4, 6.3, 49.4, 51.6)
    min_lon = min(finite_lons)
    max_lon = max(finite_lons)
    min_lat = min(finite_lats)
    max_lat = max(finite_lats)
    lon_pad = max(0.25, (max_lon - min_lon) * 0.10)
    lat_pad = max(0.18, (max_lat - min_lat) * 0.10)
    return (min_lon - lon_pad, max_lon + lon_pad, min_lat - lat_pad, max_lat + lat_pad)


def _project_point(
    lon: float,
    lat: float,
    *,
    bounds: tuple[float, float, float, float],
    width: int,
    height: int,
    pad: int,
) -> tuple[float, float]:
    min_lon, max_lon, min_lat, max_lat = bounds
    x = pad + (lon - min_lon) / max(max_lon - min_lon, 0.0001) * (width - 2 * pad)
    y = height - pad - (lat - min_lat) / max(max_lat - min_lat, 0.0001) * (height - 2 * pad)
    return (x, y)


def _circle_radius(score: float) -> float:
    return 7.0 + _clamp01(score) * 18.0


def _render_map_svg(report: dict[str, Any]) -> str:
    stations = report.get("stations", [])
    stations = [s for s in stations if isinstance(s, dict)]
    aggregate = report.get("aggregate", {})
    target = report.get("target_window", {})
    width = 1120
    height = 780
    pad = 72
    bounds = _map_bounds(stations)

    def esc(value: Any) -> str:
        return html.escape(str(value), quote=True)

    def point(lon: float, lat: float) -> str:
        x, y = _project_point(lon, lat, bounds=bounds, width=width, height=height, pad=pad)
        return f"{x:.1f},{y:.1f}"

    outline_points = " ".join(point(lon, lat) for lon, lat in BE_OUTLINE_LON_LAT)
    lines: list[str] = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">'
    )
    lines.append('<title id="title">MeteoVoid Belgium Alert Map</title>')
    lines.append(
        '<desc id="desc">Carte statique des scores de risque par station pour la Belgique et les approches frontalières.</desc>'
    )
    lines.append('<rect width="100%" height="100%" fill="#f7f5ef"/>')
    lines.append(
        '<rect x="28" y="28" width="1064" height="724" rx="24" fill="#ffffff" stroke="#d9d4c8"/>'
    )
    lines.append(
        '<text x="56" y="70" font-family="Arial, Helvetica, sans-serif" font-size="28" font-weight="700" fill="#222">'
        "MeteoVoid Belgique, carte de veille</text>"
    )
    lines.append(
        f'<text x="56" y="102" font-family="Arial, Helvetica, sans-serif" font-size="16" fill="#555">'
        f'Score national {float(aggregate.get("score", 0.0)):.3f}, sévérité {esc(aggregate.get("severity", "n/a"))}, '
        f'fenêtre {esc(target.get("start", "n/a"))} à {esc(target.get("end", "n/a"))}</text>'
    )

    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        x = pad + frac * (width - 2 * pad)
        y = pad + frac * (height - 2 * pad)
        lines.append(
            f'<line x1="{x:.1f}" y1="{pad}" x2="{x:.1f}" y2="{height-pad}" stroke="#eee8dc"/>'
        )
        lines.append(
            f'<line x1="{pad}" y1="{y:.1f}" x2="{width-pad}" y2="{y:.1f}" stroke="#eee8dc"/>'
        )

    lines.append(
        f'<polygon points="{outline_points}" fill="#eef2f0" stroke="#9aa9a2" stroke-width="2" opacity="0.95"/>'
    )
    lines.append(
        '<text x="88" y="720" font-family="Arial, Helvetica, sans-serif" font-size="13" fill="#777">'
        "Carte schématique sans fond géographique externe. Points dimensionnés par score, couleurs par sévérité.</text>"
    )

    ordered = sorted(stations, key=lambda x: float(x.get("score") or 0.0), reverse=True)
    for item in ordered:
        lon = _safe_float(item.get("lon"))
        lat = _safe_float(item.get("lat"))
        if lon is None or lat is None:
            continue
        x, y = _project_point(lon, lat, bounds=bounds, width=width, height=height, pad=pad)
        severity = str(item.get("severity", "normal"))
        score = float(item.get("score") or 0.0)
        color = "#888888" if not item.get("source_ok", True) else _severity_color(severity)
        radius = _circle_radius(score)
        stroke = "#333333" if item.get("source_ok", True) else "#777777"
        station_name = esc(item.get("name", item.get("station_id", "station")))
        station_id = esc(item.get("station_id", ""))
        title = esc(
            f"{item.get('name', station_id)} | score {score:.3f} | {severity} | {item.get('worst_time') or 'n/a'}"
        )
        lines.append(f'<g class="station station-{esc(severity)}">')
        lines.append(f"<title>{title}</title>")
        lines.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" fill="{color}" '
            f'fill-opacity="0.82" stroke="{stroke}" stroke-width="1.4"/>'
        )
        lines.append(
            f'<text x="{x + radius + 5:.1f}" y="{y + 4:.1f}" font-family="Arial, Helvetica, sans-serif" '
            f'font-size="12" fill="#242424">{station_name}</text>'
        )
        lines.append("</g>")

    legend_x = 820
    legend_y = 134
    lines.append(f'<g transform="translate({legend_x},{legend_y})">')
    lines.append(
        '<rect x="0" y="0" width="232" height="178" rx="14" fill="#ffffff" stroke="#d9d4c8"/>'
    )
    lines.append(
        '<text x="18" y="28" font-family="Arial, Helvetica, sans-serif" font-size="15" font-weight="700" fill="#333">Légende</text>'
    )
    for idx, sev in enumerate(["normal", "watch", "medium", "high", "alert"]):
        y = 54 + idx * 23
        lines.append(f'<circle cx="24" cy="{y}" r="8" fill="{_severity_color(sev)}"/>')
        lines.append(
            f'<text x="42" y="{y + 4}" font-family="Arial, Helvetica, sans-serif" font-size="13" fill="#333">{sev}</text>'
        )
    lines.append(
        '<text x="18" y="164" font-family="Arial, Helvetica, sans-serif" font-size="12" fill="#666">Plus le cercle est grand, plus le score est élevé.</text>'
    )
    lines.append("</g>")
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def _render_map_html(report: dict[str, Any]) -> str:
    svg = _render_map_svg(report)
    aggregate = report.get("aggregate", {})
    stations = report.get("stations", [])
    ordered = sorted(
        [s for s in stations if isinstance(s, dict)],
        key=lambda x: float(x.get("score") or 0.0),
        reverse=True,
    )
    rows: list[str] = []
    for item in ordered[:15]:
        signals = "; ".join(str(x) for x in item.get("signals", []))
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(item.get('name', '')))}</td>"
            f"<td>{html.escape(str(item.get('severity', '')))}</td>"
            f"<td>{float(item.get('score') or 0.0):.3f}</td>"
            f"<td>{html.escape(str(item.get('worst_time') or 'n/a'))}</td>"
            f"<td>{html.escape(signals)}</td>"
            "</tr>"
        )
    return (
        """<!doctype html>
<html lang=\"fr\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>MeteoVoid Belgium Alert Map</title>
  <style>
    body { font-family: Arial, Helvetica, sans-serif; margin: 24px; background: #f7f5ef; color: #222; }
    main { max-width: 1180px; margin: 0 auto; }
    .panel { background: #fff; border: 1px solid #d9d4c8; border-radius: 18px; padding: 20px; margin-bottom: 18px; }
    svg { width: 100%; height: auto; display: block; }
    table { width: 100%; border-collapse: collapse; font-size: 14px; }
    th, td { border-bottom: 1px solid #e7e1d7; padding: 8px; text-align: left; vertical-align: top; }
    th { background: #fbfaf6; }
    code { background: #f1ece1; padding: 2px 5px; border-radius: 5px; }
  </style>
</head>
<body>
<main>
  <section class=\"panel\">
    <h1>MeteoVoid Belgium Alert Watch</h1>
    <p>Score national : <code>"""
        + f"{float(aggregate.get('score', 0.0)):.3f}"
        + """</code>. Sévérité : <code>"""
        + html.escape(str(aggregate.get("severity", "n/a")))
        + """</code>.</p>
    <p>Carte statique hors ligne. Elle ne dépend d’aucune tuile externe.</p>
  </section>
  <section class=\"panel\">
"""
        + svg
        + """
  </section>
  <section class=\"panel\">
    <h2>Stations</h2>
    <table>
      <thead><tr><th>Station</th><th>Sévérité</th><th>Score</th><th>Heure sensible</th><th>Signaux</th></tr></thead>
      <tbody>
"""
        + "\n".join(rows)
        + """
      </tbody>
    </table>
  </section>
</main>
</body>
</html>
"""
    )


def _render_geojson(report: dict[str, Any]) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    for item in report.get("stations", []):
        if not isinstance(item, dict):
            continue
        lon = _safe_float(item.get("lon"))
        lat = _safe_float(item.get("lat"))
        if lon is None or lat is None:
            continue
        props = {k: v for k, v in item.items() if k not in {"lat", "lon", "components"}}
        props["component_heat"] = (
            item.get("components", {}).get("heat")
            if isinstance(item.get("components"), dict)
            else None
        )
        props["component_moisture"] = (
            item.get("components", {}).get("moisture")
            if isinstance(item.get("components"), dict)
            else None
        )
        props["component_precipitation"] = (
            item.get("components", {}).get("precipitation")
            if isinstance(item.get("components"), dict)
            else None
        )
        props["component_wind_gust"] = (
            item.get("components", {}).get("wind_gust")
            if isinstance(item.get("components"), dict)
            else None
        )
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": props,
            }
        )
    return {
        "type": "FeatureCollection",
        "name": "MeteoVoid Belgium Alert Risk By Station",
        "generated_at": report.get("generated_at"),
        "features": features,
    }


def _render_markdown(report: dict[str, Any]) -> str:
    aggregate = report["aggregate"]
    stations = report["stations"]
    data_mode = report.get("data_mode", "unknown")
    source_type = report.get("source_type", "unknown")
    source_detail = report.get("source_detail", report.get("source", "unknown"))
    integrations = report.get("integrations", {})

    lines: list[str] = []
    lines.append("# MeteoVoid Belgium Alert Watch")
    lines.append("")
    lines.append(f"Généré le : `{report['generated_at']}`")
    lines.append(
        f"Fenêtre analysée : `{report['target_window']['start']}` à "
        f"`{report['target_window']['end']}`"
    )
    lines.append(f"Score national : `{aggregate['score']:.3f}`")
    lines.append(f"Sévérité : `{aggregate['severity']}`")
    lines.append("")
    lines.append("## Source et limites")
    lines.append("")
    lines.append(f"Source principale : `{source_detail}`")
    lines.append(f"Mode de données : `{data_mode}`")
    lines.append(f"Type de source : `{source_type}`")
    lines.append(
        "Données récupérées au moment de l’exécution"
        if data_mode == "live_forecast_api"
        else "Données de démonstration déterministes, sans accès réseau"
    )
    lines.append("")
    lines.append("Intégrations externes actuellement actives :")
    lines.append(
        f"- Avertissements officiels IRM/KMI : `{bool(integrations.get('official_warning_integrated', False))}`"
    )
    lines.append(f"- MeteoAlarm : `{bool(integrations.get('metealarm_integrated', False))}`")
    lines.append(f"- ESTOFEX : `{bool(integrations.get('estofex_integrated', False))}`")
    lines.append(f"- Radar : `{bool(integrations.get('radar_integrated', False))}`")
    lines.append(f"- Foudre : `{bool(integrations.get('lightning_integrated', False))}`")
    lines.append("")
    lines.append(
        "Ce rapport est une veille basée sur modèle. Ce n’est pas une alerte officielle. "
        "Pour la sécurité publique, il doit toujours être comparé avec l’IRM/KMI, "
        "MeteoAlarm, le radar et le nowcast foudre."
    )
    lines.append("")
    lines.append("## Carte")
    lines.append("")
    lines.append(
        "Une carte statique est générée avec le rapport : `belgium_alert_map.svg` et "
        "`belgium_alert_map.html`. Un tableau de bord professionnel est aussi généré : `belgium_alert_dashboard.html`. Un fichier SIG est aussi produit : `risk_by_station.geojson`."
    )
    lines.append("")
    lines.append("## Stations les plus sensibles")
    lines.append("")
    lines.append(
        "| Station | Région | Sévérité | Score | Heure sensible | Tmax °C | Point de rosée °C | "
        "Précip % | Précip mm/h | Rafales m/s | Baisse hPa/6h | Signaux |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    ordered = sorted(stations, key=lambda x: float(x["score"]), reverse=True)
    for item in ordered[:12]:
        signals = "; ".join(item.get("signals", []))
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item["name"]),
                    str(item["region"]),
                    str(item["severity"]),
                    f"{float(item['score']):.3f}",
                    str(item.get("worst_time") or "n/a"),
                    _fmt(item.get("max_temperature_c")),
                    _fmt(item.get("max_dew_point_c")),
                    _fmt(item.get("max_precip_probability_pct"), 0),
                    _fmt(item.get("max_precipitation_mm_h")),
                    _fmt(item.get("max_wind_gust_ms")),
                    _fmt(item.get("max_pressure_drop_6h_hpa")),
                    signals.replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    lines.append("## Notes opérationnelles")
    lines.append("")
    lines.append("- `watch` : garder la situation sous surveillance rapprochée.")
    lines.append("- `medium` : comparer avec les avertissements officiels et l’évolution radar.")
    lines.append(
        "- `high` : préparer un message d’alerte clair si les signaux externes confirment."
    )
    lines.append("- `alert` : publier seulement après confirmation externe.")
    lines.append("")
    lines.append(
        "Vérifications externes recommandées : avertissements IRM/KMI, MeteoAlarm, "
        "ESTOFEX, radar, foudre."
    )
    lines.append("")
    return "\n".join(lines)


def _severity_badge_label(severity: str) -> str:
    labels = {
        "normal": "normal",
        "watch": "watch",
        "medium": "medium",
        "high": "high",
        "alert": "alert",
    }
    return labels.get(str(severity), str(severity))


def _fmt_time(value: Any) -> str:
    if value in (None, ""):
        return "n/a"
    raw = str(value)
    if "T" in raw:
        return raw.replace("T", " ")
    return raw


def _station_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    stations = report.get("stations", [])
    rows = [s for s in stations if isinstance(s, dict)]
    return sorted(rows, key=lambda x: float(x.get("score") or 0.0), reverse=True)


def _dominant_corridor(rows: list[dict[str, Any]]) -> str:
    high_rows = [r for r in rows if str(r.get("severity")) in {"high", "alert"}]
    names = [str(r.get("name", "")) for r in high_rows[:5] if r.get("name")]
    if not names:
        return "Aucun axe dominant ne ressort encore nettement dans les stations suivies."
    return "Les stations les plus exposées se concentrent autour de " + ", ".join(names) + "."


def _dashboard_insights(report: dict[str, Any]) -> list[tuple[str, str, str]]:
    rows = _station_rows(report)
    high_count = sum(1 for r in rows if str(r.get("severity")) in {"high", "alert"})
    max_temp = _max_number([r.get("max_temperature_c") for r in rows])
    max_dew = _max_number([r.get("max_dew_point_c") for r in rows])
    max_precip = _max_number([r.get("max_precip_probability_pct") for r in rows])
    external = report.get("external_confirmation", {})
    operational = report.get("operational_state", {})
    trend = report.get("trend", {})

    insights = [
        (
            "Zones les plus sensibles",
            _dominant_corridor(rows),
            "heat",
        ),
        (
            "Signal convectif",
            f"{high_count} station(s) en niveau high ou alert. Tmax observée dans le modèle : {_fmt(max_temp)} °C, point de rosée maximal : {_fmt(max_dew)} °C.",
            "storm",
        ),
        (
            "Précipitations probables",
            f"Probabilité maximale de précipitation dans la grille : {_fmt(max_precip, 0)} %. A confirmer avec radar, foudre et bulletins officiels.",
            "rain",
        ),
    ]
    if isinstance(external, dict):
        insights.append(
            (
                "Confirmation externe",
                f"Score externe : {float(external.get('score') or 0.0):.3f}. Statut : {external.get('status', 'non_confirmed')}. {external.get('summary', '')}",
                "storm",
            )
        )
    if isinstance(operational, dict):
        insights.append(
            (
                "Niveau opérationnel",
                f"{operational.get('level', 'watch')} : {operational.get('reason', 'surveillance en cours')}",
                "rain",
            )
        )
    if isinstance(trend, dict) and trend.get("status") != "no_history":
        insights.append(
            (
                "Tendance",
                f"{trend.get('status', 'unknown')} sur {trend.get('comparison_runs', 0)} run(s). Écart score : {float(trend.get('delta_score') or 0.0):+.3f}.",
                "heat",
            )
        )
    return insights


def _render_dashboard_map_svg(report: dict[str, Any]) -> str:
    stations = _station_rows(report)
    width = 1060
    height = 520
    pad = 58
    bounds = _map_bounds(stations)

    def esc(value: Any) -> str:
        return html.escape(str(value), quote=True)

    def point(lon: float, lat: float) -> str:
        x, y = _project_point(lon, lat, bounds=bounds, width=width, height=height, pad=pad)
        return f"{x:.1f},{y:.1f}"

    outline_points = " ".join(point(lon, lat) for lon, lat in BE_OUTLINE_LON_LAT)
    lines: list[str] = []
    lines.append(
        f'<svg class="mv-map-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="map-title map-desc">'
    )
    lines.append('<title id="map-title">Carte des risques MeteoVoid Belgique</title>')
    lines.append(
        '<desc id="map-desc">Carte professionnelle des scores par station pour la Belgique et les approches frontalières.</desc>'
    )
    lines.append("<defs>")
    lines.append(
        '<linearGradient id="mvSea" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#d9efff"/><stop offset="1" stop-color="#f8fbff"/></linearGradient>'
    )
    lines.append(
        '<linearGradient id="mvLand" x1="0" x2="1" y1="0" y2="1"><stop offset="0" stop-color="#f3f6e8"/><stop offset="1" stop-color="#edf4df"/></linearGradient>'
    )
    lines.append(
        '<filter id="softShadow" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="8" stdDeviation="8" flood-color="#12213a" flood-opacity="0.14"/></filter>'
    )
    lines.append(
        '<filter id="markerShadow" x="-80%" y="-80%" width="260%" height="260%"><feDropShadow dx="0" dy="3" stdDeviation="3" flood-color="#172033" flood-opacity="0.22"/></filter>'
    )
    lines.append("</defs>")
    lines.append('<rect width="100%" height="100%" rx="18" fill="#f8fbff"/>')
    lines.append('<path d="M0,0 L250,0 C205,54 128,88 0,96 Z" fill="url(#mvSea)" opacity="0.88"/>')
    lines.append('<g opacity="0.50" stroke="#cfe3ef" stroke-width="1">')
    for frac in (0.18, 0.36, 0.54, 0.72, 0.90):
        x = pad + frac * (width - 2 * pad)
        y = pad + frac * (height - 2 * pad)
        lines.append(f'<line x1="{x:.1f}" y1="{pad}" x2="{x:.1f}" y2="{height-pad}"/>')
        lines.append(f'<line x1="{pad}" y1="{y:.1f}" x2="{width-pad}" y2="{y:.1f}"/>')
    lines.append("</g>")
    lines.append('<text x="110" y="390" class="mv-country">FRANCE</text>')
    lines.append('<text x="860" y="110" class="mv-country">PAYS-BAS</text>')
    lines.append('<text x="870" y="325" class="mv-country">ALLEMAGNE</text>')
    lines.append('<text x="760" y="458" class="mv-country">LUXEMBOURG</text>')
    lines.append(
        f'<polygon points="{outline_points}" fill="url(#mvLand)" stroke="#b9c7a8" stroke-width="2.2" filter="url(#softShadow)"/>'
    )
    lines.append('<g stroke="#a8d5e7" stroke-width="1" opacity="0.55" fill="none">')
    lines.append('<path d="M258 222 C360 245, 476 247, 590 230 S780 225, 890 252"/>')
    lines.append('<path d="M410 136 C480 170, 555 172, 630 155 S760 150, 830 185"/>')
    lines.append('<path d="M520 332 C590 348, 650 382, 706 426"/>')
    lines.append("</g>")

    for item in reversed(stations):
        lon = _safe_float(item.get("lon"))
        lat = _safe_float(item.get("lat"))
        if lon is None or lat is None:
            continue
        x, y = _project_point(lon, lat, bounds=bounds, width=width, height=height, pad=pad)
        severity = str(item.get("severity", "normal"))
        score = float(item.get("score") or 0.0)
        radius = 8.5 + _clamp01(score) * 16.0
        color = "#94a3b8" if not item.get("source_ok", True) else _severity_color(severity)
        name = esc(item.get("name", item.get("station_id", "station")))
        title = esc(
            f"{item.get('name', '')} | score {score:.3f} | {severity} | {_fmt_time(item.get('worst_time'))}"
        )
        label_dx = radius + 7
        label_dy = 4
        if x > width * 0.76:
            label_dx = -radius - 7
        anchor = "start" if label_dx > 0 else "end"
        lines.append('<g class="mv-station">')
        lines.append(f"<title>{title}</title>")
        lines.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius + 5:.1f}" fill="{color}" opacity="0.14"/>'
        )
        lines.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" fill="{color}" stroke="#ffffff" stroke-width="4" filter="url(#markerShadow)"/>'
        )
        lines.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{max(3.0, radius * 0.23):.1f}" fill="#ffffff" opacity="0.55"/>'
        )
        lines.append(
            f'<text x="{x + label_dx:.1f}" y="{y + label_dy:.1f}" text-anchor="{anchor}" class="mv-label">{name}</text>'
        )
        lines.append("</g>")

    lines.append('<g class="mv-legend" transform="translate(26,320)">')
    lines.append(
        '<rect x="0" y="0" width="170" height="174" rx="14" fill="#ffffff" stroke="#d8e0ea" filter="url(#softShadow)"/>'
    )
    lines.append('<text x="18" y="28" class="mv-legend-title">Sévérité</text>')
    for idx, sev in enumerate(["normal", "watch", "medium", "high", "alert"]):
        y = 54 + idx * 21
        lines.append(f'<circle cx="24" cy="{y}" r="7" fill="{_severity_color(sev)}"/>')
        lines.append(f'<text x="42" y="{y + 4}" class="mv-legend-text">{sev}</text>')
    lines.append('<line x1="18" y1="150" x2="152" y2="150" stroke="#e5ebf2"/>')
    lines.append('<text x="18" y="166" class="mv-note">Taille = score</text>')
    lines.append("</g>")
    lines.append("</svg>")
    return "\n".join(lines)


def _render_dashboard_html(report: dict[str, Any]) -> str:
    aggregate = report.get("aggregate", {})
    target = report.get("target_window", {})
    rows = _station_rows(report)
    generated_at = str(report.get("generated_at", "n/a"))
    score = float(aggregate.get("score") or 0.0)
    severity = str(aggregate.get("severity", "normal"))
    source_detail = html.escape(str(report.get("source_detail", "unknown")))
    source_type = html.escape(str(report.get("source_type", "unknown")))
    data_mode = html.escape(str(report.get("data_mode", "unknown")))
    last_sensitive = next((str(r.get("worst_time")) for r in rows if r.get("worst_time")), "n/a")
    active_count = int(aggregate.get("source_ok_count") or 0)
    error_count = int(aggregate.get("source_error_count") or 0)
    top_scores = [float(r.get("score") or 0.0) for r in rows[:6]] or [0.0]
    spark_points = []
    for i, val in enumerate(top_scores):
        x = 8 + i * (88 / max(1, len(top_scores) - 1))
        y = 48 - val * 34
        spark_points.append(f"{x:.1f},{y:.1f}")
    sparkline = " ".join(spark_points)

    def esc(value: Any) -> str:
        return html.escape(str(value), quote=True)

    def badge(sev: Any) -> str:
        sev_s = str(sev)
        return f'<span class="badge badge-{esc(sev_s)}">{esc(_severity_badge_label(sev_s))}</span>'

    station_rows: list[str] = []
    for item in rows:
        signals = "; ".join(str(x) for x in item.get("signals", []))
        station_rows.append(
            "<tr>"
            f"<td><strong>{esc(item.get('name', ''))}</strong><span>{esc(item.get('region', ''))}</span></td>"
            f"<td>{badge(item.get('severity', 'normal'))}</td>"
            f"<td class=\"num\">{float(item.get('score') or 0.0):.3f}</td>"
            f"<td>{esc(_fmt_time(item.get('worst_time')))}</td>"
            f"<td>{esc(signals)}</td>"
            "</tr>"
        )

    insight_blocks: list[str] = []
    icon_map = {"heat": "☀", "storm": "ϟ", "rain": "☔"}
    for title, text, kind in _dashboard_insights(report):
        insight_blocks.append(
            f'<article class="insight insight-{esc(kind)}"><div class="insight-icon">{icon_map.get(kind, "i")}</div>'
            f"<div><h3>{esc(title)}</h3><p>{esc(text)}</p></div></article>"
        )

    official_states = (
        report.get("integrations", {}) if isinstance(report.get("integrations"), dict) else {}
    )
    integrations_text = ", ".join(
        [
            f"IRM/KMI: {bool(official_states.get('official_warning_integrated', False))}",
            f"MeteoAlarm: {bool(official_states.get('metealarm_integrated', False))}",
            f"ESTOFEX: {bool(official_states.get('estofex_integrated', False))}",
            f"Radar: {bool(official_states.get('radar_integrated', False))}",
            f"Foudre: {bool(official_states.get('lightning_integrated', False))}",
        ]
    )

    return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MeteoVoid Belgique Dashboard</title>
  <style>
    :root {{
      --bg: #f3f6fb;
      --panel: #ffffff;
      --ink: #0f213f;
      --muted: #607089;
      --line: #dfe7f0;
      --blue: #2b6fed;
      --normal: {SEVERITY_COLORS['normal']};
      --watch: {SEVERITY_COLORS['watch']};
      --medium: {SEVERITY_COLORS['medium']};
      --high: {SEVERITY_COLORS['high']};
      --alert: {SEVERITY_COLORS['alert']};
      --shadow: 0 14px 34px rgba(15, 33, 63, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--bg); color: var(--ink); font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .app {{ display: grid; grid-template-columns: 228px 1fr; min-height: 100vh; }}
    aside {{ background: linear-gradient(180deg, #0b1d37 0%, #102b4f 100%); color: #dbe7ff; padding: 24px 18px; display: flex; flex-direction: column; gap: 28px; }}
    .brand {{ display: flex; align-items: center; gap: 12px; font-weight: 800; letter-spacing: 0.2px; }}
    .logo {{ width: 46px; height: 46px; border-radius: 15px; display: grid; place-items: center; background: rgba(255,255,255,0.12); font-size: 24px; }}
    nav {{ display: grid; gap: 9px; }}
    nav a {{ color: #cbd7ee; text-decoration: none; padding: 12px 14px; border-radius: 13px; font-weight: 650; }}
    nav a.active {{ background: rgba(43,111,237,0.28); color: #fff; outline: 1px solid rgba(137,172,255,0.45); }}
    .status {{ margin-top: auto; border: 1px solid rgba(210,226,255,0.20); background: rgba(255,255,255,0.07); border-radius: 16px; padding: 14px; font-size: 13px; }}
    .dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: #65c466; margin-right: 8px; }}
    main {{ padding: 28px 34px 24px; }}
    header {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; margin-bottom: 20px; }}
    h1 {{ margin: 0; font-size: 38px; line-height: 1; letter-spacing: -1.2px; }}
    .subtitle {{ margin: 8px 0 0; color: var(--muted); font-size: 16px; }}
    .header-actions {{ display: flex; align-items: center; gap: 16px; }}
    .refresh {{ border: 1px solid var(--line); background: #fff; border-radius: 12px; padding: 10px 16px; font-weight: 700; color: var(--blue); box-shadow: 0 6px 18px rgba(15,33,63,0.05); }}
    .stamp {{ color: var(--muted); text-align: right; font-size: 14px; line-height: 1.4; }}
    .kpis {{ display: grid; grid-template-columns: 1.15fr 1fr 1.15fr 0.9fr 1.15fr; gap: 14px; margin-bottom: 16px; }}
    .card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 18px; box-shadow: var(--shadow); }}
    .kpi {{ padding: 18px 20px; min-height: 116px; }}
    .kpi small {{ color: var(--muted); font-weight: 800; letter-spacing: .06em; text-transform: uppercase; }}
    .kpi strong {{ display: block; margin-top: 8px; font-size: 32px; line-height: 1; }}
    .kpi p {{ color: var(--muted); margin: 10px 0 0; font-size: 13px; }}
    .severity-word {{ color: var(--high); }}
    .spark {{ float: right; margin-top: 4px; width: 110px; height: 54px; }}
    .layout {{ display: grid; grid-template-columns: minmax(640px, 1.9fr) minmax(300px, 0.9fr); gap: 16px; align-items: stretch; }}
    .panel-title {{ padding: 16px 18px 0; font-size: 16px; font-weight: 800; }}
    .map-panel {{ overflow: hidden; }}
    .map-wrap {{ padding: 10px 14px 14px; }}
    .mv-map-svg {{ width: 100%; height: auto; display: block; }}
    .mv-country {{ font-size: 13px; fill: #738196; letter-spacing: .08em; font-weight: 800; }}
    .mv-label {{ font-size: 12px; fill: #172033; font-weight: 800; paint-order: stroke; stroke: #fff; stroke-width: 4px; stroke-linejoin: round; }}
    .mv-legend-title {{ font-size: 14px; fill: #172033; font-weight: 800; }}
    .mv-legend-text {{ font-size: 12px; fill: #34445b; }}
    .mv-note {{ font-size: 11px; fill: #607089; }}
    .insights {{ padding: 16px; display: grid; gap: 12px; }}
    .insight {{ display: grid; grid-template-columns: 54px 1fr; gap: 13px; align-items: center; border: 1px solid var(--line); border-radius: 16px; padding: 14px; background: linear-gradient(180deg, #fff, #fbfdff); }}
    .insight-icon {{ width: 46px; height: 46px; border-radius: 15px; display: grid; place-items: center; font-size: 23px; font-weight: 900; }}
    .insight-heat .insight-icon {{ color: var(--high); background: rgba(216,86,70,.10); }}
    .insight-storm .insight-icon {{ color: var(--medium); background: rgba(229,147,58,.12); }}
    .insight-rain .insight-icon {{ color: var(--alert); background: rgba(110,63,160,.10); }}
    .insight h3 {{ margin: 0 0 5px; font-size: 15px; }}
    .insight p {{ margin: 0; color: #34445b; font-size: 13px; line-height: 1.35; }}
    .info-strip {{ margin-top: 2px; border: 1px solid #cfe0ff; background: #eff6ff; color: #1d4f9c; border-radius: 14px; padding: 12px 14px; font-weight: 650; font-size: 13px; }}
    .table-card {{ margin-top: 16px; overflow: hidden; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th {{ text-align: left; color: var(--muted); font-size: 12px; letter-spacing: .03em; text-transform: uppercase; background: #f9fbfe; padding: 13px 18px; border-bottom: 1px solid var(--line); }}
    td {{ padding: 11px 18px; border-bottom: 1px solid #edf2f7; vertical-align: top; }}
    td span {{ display: block; color: var(--muted); font-size: 12px; margin-top: 2px; }}
    .num {{ font-variant-numeric: tabular-nums; font-weight: 800; }}
    .badge {{ display: inline-flex; min-width: 66px; justify-content: center; border-radius: 999px; color: #fff; padding: 4px 9px; font-weight: 800; font-size: 12px; }}
    .badge-normal {{ background: var(--normal); }}
    .badge-watch {{ background: var(--watch); }}
    .badge-medium {{ background: var(--medium); }}
    .badge-high {{ background: var(--high); }}
    .badge-alert {{ background: var(--alert); }}
    .meta {{ margin-top: 14px; display: flex; justify-content: space-between; gap: 12px; color: var(--muted); font-size: 13px; }}
    .foot {{ margin-top: 18px; display: flex; align-items: center; justify-content: space-between; color: var(--muted); font-size: 13px; }}
    @media (max-width: 1180px) {{ .app {{ grid-template-columns: 1fr; }} aside {{ display: none; }} .kpis {{ grid-template-columns: repeat(2, 1fr); }} .layout {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <div class="app">
    <aside>
      <div class="brand"><div class="logo">☔</div><div>MeteoVoid<br>Belgique</div></div>
      <nav>
        <a class="active" href="#">Vue d'ensemble</a>
        <a href="#stations">Stations</a>
        <a href="#">Alertes</a>
        <a href="#">Historique</a>
        <a href="#">Paramètres</a>
      </nav>
      <div class="status"><p><span class="dot"></span><strong>Système opérationnel</strong></p><p>Dernière mise à jour<br>{esc(generated_at)}</p></div>
    </aside>
    <main>
      <header>
        <div>
          <h1>MeteoVoid Belgique</h1>
          <p class="subtitle">Tableau de bord de surveillance des risques météo en Belgique</p>
        </div>
        <div class="header-actions">
          <button class="refresh" type="button">Actualiser</button>
          <div class="stamp">{esc(generated_at)}<br>Europe/Brussels</div>
        </div>
      </header>

      <section class="kpis">
        <article class="card kpi"><small>Score national</small><svg class="spark" viewBox="0 0 110 54"><polyline points="{sparkline}" fill="none" stroke="#2b6fed" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg><strong>{score:.3f}</strong><p>Plus le score est élevé, plus la vigilance augmente.</p></article>
        <article class="card kpi"><small>Sévérité nationale</small><strong class="severity-word">{esc(severity)}</strong><p>Niveau dominant issu du scoring modèle.</p></article>
        <article class="card kpi"><small>Fenêtre de veille</small><strong>{esc(target.get('start', 'n/a'))}<br>au {esc(target.get('end', 'n/a'))}</strong><p>Période couverte par l'analyse.</p></article>
        <article class="card kpi"><small>Stations évaluées</small><strong>{active_count}</strong><p>{error_count} station(s) en erreur de source.</p></article>
        <article class="card kpi"><small>Dernière heure sensible</small><strong>{esc(_fmt_time(last_sensitive))}</strong><p>Heure sensible la plus récente du top risque.</p></article>
      </section>

      <section class="layout">
        <article class="card map-panel"><div class="panel-title">Carte des risques météo par station</div><div class="map-wrap">{_render_dashboard_map_svg(report)}</div></article>
        <article class="card"><div class="panel-title">Points clés et lecture opérationnelle</div><div class="insights">{''.join(insight_blocks)}<div class="info-strip">Données basées sur des prévisions modèle. Surveillance active recommandée, confirmation externe nécessaire.</div></div></article>
      </section>

      <section id="stations" class="card table-card">
        <div class="panel-title">Stations et évaluation des risques</div>
        <table>
          <thead><tr><th>Station</th><th>Sévérité</th><th>Score</th><th>Heure sensible</th><th>Signaux</th></tr></thead>
          <tbody>{''.join(station_rows)}</tbody>
        </table>
      </section>

      <div class="meta">
        <span>Données : {source_detail} | Mode : {data_mode} | Type : {source_type}</span>
        <span>{esc(integrations_text)}</span>
      </div>
      <footer class="foot"><strong>MeteoVoid Belgique</strong><span>Données non contractuelles. Comparaison indispensable avec IRM/KMI, MeteoAlarm, radar et foudre.</span></footer>
    </main>
  </div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Professional map rendering overrides
# ---------------------------------------------------------------------------
# These definitions intentionally override the first lightweight map renderer above.
# The HTML map uses Leaflet and OpenStreetMap tiles for a real geographic basemap.
# The SVG map remains an offline fallback and now applies marker decluttering.

BE_OUTLINE_LON_LAT_DETAILED = [
    (2.54, 51.09),
    (2.70, 51.14),
    (2.91, 51.23),
    (3.18, 51.29),
    (3.45, 51.33),
    (3.82, 51.36),
    (4.26, 51.50),
    (4.74, 51.44),
    (5.16, 51.34),
    (5.55, 51.15),
    (5.82, 50.93),
    (6.20, 50.78),
    (6.38, 50.62),
    (6.18, 50.36),
    (6.29, 50.12),
    (5.98, 49.96),
    (5.82, 49.54),
    (5.42, 49.50),
    (5.05, 49.63),
    (4.75, 49.56),
    (4.36, 49.80),
    (3.98, 49.93),
    (3.55, 50.02),
    (3.24, 50.31),
    (2.82, 50.72),
    (2.55, 50.82),
    (2.54, 51.09),
]

LABEL_OFFSETS = {
    "BE_COXYDE": (16, -16, "start"),
    "BE_GENT": (-18, -20, "end"),
    "BE_ANTWERP": (16, -18, "start"),
    "BE_HASSELT": (18, -10, "start"),
    "BE_UCCLE": (-18, -16, "end"),
    "BE_JODOIGNE": (20, -16, "start"),
    "BE_LIEGE": (18, 4, "start"),
    "BE_NAMUR": (18, 20, "start"),
    "BE_CHARLEROI": (-18, 18, "end"),
    "BE_MONS": (-18, 20, "end"),
    "BE_ARLON": (-18, -18, "end"),
    "FR_LILLE": (-18, -18, "end"),
    "NL_MAASTRICHT": (18, -22, "start"),
    "DE_AACHEN": (18, 20, "start"),
    "LU_LUXEMBOURG": (18, 18, "start"),
}


def _better_bounds(stations: list[dict[str, Any]]) -> tuple[float, float, float, float]:
    """Stable map bounds centered on Belgium plus the immediate approaches."""
    return (2.25, 6.65, 49.35, 51.65)


def _project_entries_decluttered(
    stations: list[dict[str, Any]],
    *,
    bounds: tuple[float, float, float, float],
    width: int,
    height: int,
    pad: int,
    radius_scale: float = 1.0,
) -> list[dict[str, Any]]:
    """Project stations and move markers slightly when markers would overlap.

    The true geographic point is kept as raw_x/raw_y. When a marker is shifted,
    renderers can draw a thin leader line so the displacement remains explicit.
    """

    ordered = sorted(stations, key=lambda x: float(x.get("score") or 0.0), reverse=True)
    placed: list[dict[str, Any]] = []
    angles = [0, 60, 120, 180, 240, 300]
    candidates: list[tuple[float, float]] = [(0.0, 0.0)]
    for ring in (10, 18, 28, 40, 54, 70):
        for angle in angles:
            import math

            rad = math.radians(angle)
            candidates.append((math.cos(rad) * ring, math.sin(rad) * ring))

    for item in ordered:
        lon = _safe_float(item.get("lon"))
        lat = _safe_float(item.get("lat"))
        if lon is None or lat is None:
            continue
        raw_x, raw_y = _project_point(lon, lat, bounds=bounds, width=width, height=height, pad=pad)
        score = float(item.get("score") or 0.0)
        radius = (7.0 + _clamp01(score) * 15.0) * radius_scale
        best_x = raw_x
        best_y = raw_y
        for dx, dy in candidates:
            candidate_x = min(max(raw_x + dx, pad + radius), width - pad - radius)
            candidate_y = min(max(raw_y + dy, pad + radius), height - pad - radius)
            ok = True
            for other in placed:
                dist = ((candidate_x - other["x"]) ** 2 + (candidate_y - other["y"]) ** 2) ** 0.5
                if dist < radius + other["radius"] + 8:
                    ok = False
                    break
            if ok:
                best_x = candidate_x
                best_y = candidate_y
                break
        placed.append(
            {
                "item": item,
                "raw_x": raw_x,
                "raw_y": raw_y,
                "x": best_x,
                "y": best_y,
                "radius": radius,
                "shifted": abs(best_x - raw_x) > 1.0 or abs(best_y - raw_y) > 1.0,
            }
        )
    return placed


def _render_map_svg(report: dict[str, Any]) -> str:
    stations = [s for s in report.get("stations", []) if isinstance(s, dict)]
    aggregate = report.get("aggregate", {})
    target = report.get("target_window", {})
    width = 1180
    height = 760
    pad = 74
    bounds = _better_bounds(stations)
    placements = _project_entries_decluttered(
        stations, bounds=bounds, width=width, height=height, pad=pad, radius_scale=1.0
    )

    def esc(value: Any) -> str:
        return html.escape(str(value), quote=True)

    def point(lon: float, lat: float) -> str:
        x, y = _project_point(lon, lat, bounds=bounds, width=width, height=height, pad=pad)
        return f"{x:.1f},{y:.1f}"

    outline_points = " ".join(point(lon, lat) for lon, lat in BE_OUTLINE_LON_LAT_DETAILED)
    lines: list[str] = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">'
    )
    lines.append('<title id="title">MeteoVoid Belgique, carte de veille</title>')
    lines.append(
        '<desc id="desc">Carte statique des scores de risque par station. Les marqueurs proches sont légèrement décalés et reliés à leur position réelle.</desc>'
    )
    lines.append("<defs>")
    lines.append(
        '<linearGradient id="sea" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#dff1ff"/><stop offset="1" stop-color="#f8fbff"/></linearGradient>'
    )
    lines.append(
        '<linearGradient id="land" x1="0" x2="1" y1="0" y2="1"><stop offset="0" stop-color="#f3f7e8"/><stop offset="1" stop-color="#edf4df"/></linearGradient>'
    )
    lines.append(
        '<filter id="shadow" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="8" stdDeviation="10" flood-color="#172033" flood-opacity="0.14"/></filter>'
    )
    lines.append(
        '<filter id="markerShadow" x="-80%" y="-80%" width="260%" height="260%"><feDropShadow dx="0" dy="3" stdDeviation="3" flood-color="#172033" flood-opacity="0.25"/></filter>'
    )
    lines.append("</defs>")
    lines.append('<rect width="100%" height="100%" fill="#f3f6fb"/>')
    lines.append(
        '<rect x="28" y="28" width="1124" height="704" rx="26" fill="#ffffff" stroke="#dce4ee"/>'
    )
    lines.append(
        '<text x="60" y="74" font-family="Arial, Helvetica, sans-serif" font-size="30" font-weight="800" fill="#10213f">MeteoVoid Belgique, carte de veille</text>'
    )
    lines.append(
        f'<text x="60" y="106" font-family="Arial, Helvetica, sans-serif" font-size="15" fill="#607089">Score national {float(aggregate.get("score", 0.0)):.3f}, sévérité {esc(aggregate.get("severity", "n/a"))}, fenêtre {esc(target.get("start", "n/a"))} à {esc(target.get("end", "n/a"))}</text>'
    )
    lines.append(
        '<rect x="60" y="128" width="1060" height="538" rx="20" fill="#f8fbff" stroke="#dfe7f0"/>'
    )
    lines.append(
        '<path d="M60,128 L310,128 C278,185 190,215 60,232 Z" fill="url(#sea)" opacity="0.85"/>'
    )

    grid_x0, grid_y0, grid_w, grid_h = 60, 128, 1060, 538
    lines.append('<g opacity="0.55" stroke="#d6e5ef" stroke-width="1">')
    for frac in (0.18, 0.36, 0.54, 0.72, 0.90):
        x = grid_x0 + frac * grid_w
        y = grid_y0 + frac * grid_h
        lines.append(f'<line x1="{x:.1f}" y1="{grid_y0}" x2="{x:.1f}" y2="{grid_y0 + grid_h}"/>')
        lines.append(f'<line x1="{grid_x0}" y1="{y:.1f}" x2="{grid_x0 + grid_w}" y2="{y:.1f}"/>')
    lines.append("</g>")
    lines.append(
        '<text x="160" y="588" font-family="Arial" font-size="13" fill="#738196" font-weight="800" letter-spacing="1.2">FRANCE</text>'
    )
    lines.append(
        '<text x="910" y="210" font-family="Arial" font-size="13" fill="#738196" font-weight="800" letter-spacing="1.2">PAYS-BAS</text>'
    )
    lines.append(
        '<text x="920" y="410" font-family="Arial" font-size="13" fill="#738196" font-weight="800" letter-spacing="1.2">ALLEMAGNE</text>'
    )
    lines.append(
        '<text x="790" y="625" font-family="Arial" font-size="13" fill="#738196" font-weight="800" letter-spacing="1.2">LUXEMBOURG</text>'
    )
    lines.append(
        f'<polygon points="{outline_points}" fill="url(#land)" stroke="#b7c7a8" stroke-width="2.4" filter="url(#shadow)"/>'
    )
    lines.append('<g stroke="#9ed4e8" stroke-width="1.2" opacity="0.55" fill="none">')
    lines.append('<path d="M300 300 C420 325, 520 320, 640 300 S830 300, 940 330"/>')
    lines.append('<path d="M450 220 C520 248, 590 244, 668 228 S800 230, 882 265"/>')
    lines.append('<path d="M575 410 C650 432, 715 465, 780 530"/>')
    lines.append("</g>")

    for entry in reversed(placements):
        item = entry["item"]
        x = float(entry["x"])
        y = float(entry["y"])
        raw_x = float(entry["raw_x"])
        raw_y = float(entry["raw_y"])
        radius = float(entry["radius"])
        severity = str(item.get("severity", "normal"))
        score = float(item.get("score") or 0.0)
        color = "#94a3b8" if not item.get("source_ok", True) else _severity_color(severity)
        station_id = str(item.get("station_id", ""))
        station_name = esc(item.get("name", station_id))
        title = esc(
            f"{item.get('name', station_id)} | score {score:.3f} | {severity} | {item.get('worst_time') or 'n/a'}"
        )
        if entry["shifted"]:
            lines.append(
                f'<line x1="{raw_x:.1f}" y1="{raw_y:.1f}" x2="{x:.1f}" y2="{y:.1f}" stroke="#516276" stroke-width="1" stroke-dasharray="3 4" opacity="0.58"/>'
            )
        label_dx, label_dy, anchor = LABEL_OFFSETS.get(station_id, (radius + 8, 4, "start"))
        lines.append('<g class="station">')
        lines.append(f"<title>{title}</title>")
        lines.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius + 6:.1f}" fill="{color}" opacity="0.16"/>'
        )
        lines.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" fill="{color}" stroke="#ffffff" stroke-width="4" filter="url(#markerShadow)"/>'
        )
        lines.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{max(3.0, radius * 0.22):.1f}" fill="#ffffff" opacity="0.55"/>'
        )
        lines.append(
            f'<text x="{x + label_dx:.1f}" y="{y + label_dy:.1f}" text-anchor="{anchor}" font-family="Arial, Helvetica, sans-serif" font-size="12" font-weight="800" fill="#172033" paint-order="stroke" stroke="#ffffff" stroke-width="4" stroke-linejoin="round">{station_name}</text>'
        )
        lines.append("</g>")

    legend_x = 72
    legend_y = 470
    lines.append(f'<g transform="translate({legend_x},{legend_y})">')
    lines.append(
        '<rect x="0" y="0" width="184" height="156" rx="16" fill="#ffffff" stroke="#d8e0ea" filter="url(#shadow)"/>'
    )
    lines.append(
        '<text x="18" y="29" font-family="Arial" font-size="15" font-weight="800" fill="#172033">Sévérité</text>'
    )
    for idx, sev in enumerate(["normal", "watch", "medium", "high", "alert"]):
        yy = 55 + idx * 20
        lines.append(f'<circle cx="24" cy="{yy}" r="7" fill="{_severity_color(sev)}"/>')
        lines.append(
            f'<text x="42" y="{yy + 4}" font-family="Arial" font-size="12" fill="#34445b">{sev}</text>'
        )
    lines.append(
        '<text x="60" y="704" font-family="Arial, Helvetica, sans-serif" font-size="12" fill="#607089">Fond SVG hors ligne. Les lignes pointillées indiquent un léger décalage anti-superposition. La carte interactive HTML utilise OpenStreetMap.</text>'
    )
    lines.append("</g>")
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def _leaflet_station_payload(report: dict[str, Any]) -> str:
    features: list[dict[str, Any]] = []
    for item in report.get("stations", []):
        if not isinstance(item, dict):
            continue
        lat = _safe_float(item.get("lat"))
        lon = _safe_float(item.get("lon"))
        if lat is None or lon is None:
            continue
        features.append(
            {
                "station_id": item.get("station_id"),
                "name": item.get("name"),
                "region": item.get("region"),
                "lat": lat,
                "lon": lon,
                "score": float(item.get("score") or 0.0),
                "severity": item.get("severity", "normal"),
                "worst_time": item.get("worst_time"),
                "signals": item.get("signals", []),
                "source_ok": bool(item.get("source_ok", True)),
            }
        )
    return json.dumps(features, ensure_ascii=False).replace("</", "<\\/")


def _render_map_html(report: dict[str, Any]) -> str:
    aggregate = report.get("aggregate", {})
    target = report.get("target_window", {})
    stations_json = _leaflet_station_payload(report)
    source = html.escape(str(report.get("source_detail", "Open-Meteo Forecast API")))
    data_mode = html.escape(str(report.get("data_mode", "unknown")))
    source_type = html.escape(str(report.get("source_type", "unknown")))
    return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MeteoVoid Belgique, carte interactive</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css">
  <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css">
  <style>
    :root {{ --ink:#0f213f; --muted:#607089; --line:#dfe7f0; --panel:#ffffff; }}
    html, body {{ height:100%; margin:0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color:var(--ink); background:#f3f6fb; }}
    .shell {{ height:100%; display:grid; grid-template-rows:auto 1fr auto; }}
    header {{ display:flex; justify-content:space-between; gap:18px; align-items:flex-start; padding:16px 18px; background:#fff; border-bottom:1px solid var(--line); }}
    h1 {{ margin:0; font-size:22px; letter-spacing:-.3px; }}
    p {{ margin:4px 0 0; color:var(--muted); font-size:13px; }}
    .score {{ display:flex; gap:10px; align-items:center; flex-wrap:wrap; justify-content:flex-end; font-size:13px; color:var(--muted); }}
    .pill {{ display:inline-flex; align-items:center; border:1px solid var(--line); border-radius:999px; background:#fff; padding:7px 10px; font-weight:800; color:var(--ink); }}
    #map {{ min-height:520px; height:100%; }}
    footer {{ padding:9px 14px; font-size:12px; color:var(--muted); background:#fff; border-top:1px solid var(--line); display:flex; justify-content:space-between; gap:14px; }}
    .risk-dot {{ border-radius:999px; border:3px solid #fff; box-shadow:0 4px 12px rgba(15,33,63,.25); display:block; }}
    .legend {{ background:#fff; border:1px solid var(--line); border-radius:14px; box-shadow:0 12px 30px rgba(15,33,63,.12); padding:12px 13px; line-height:1.25; }}
    .legend h3 {{ margin:0 0 9px; font-size:14px; }}
    .legend-row {{ display:flex; align-items:center; gap:8px; margin:6px 0; font-size:13px; }}
    .legend-swatch {{ width:12px; height:12px; border-radius:50%; display:inline-block; }}
    .popup h3 {{ margin:0 0 6px; font-size:16px; }}
    .popup .meta {{ color:#607089; margin-bottom:6px; }}
    .popup ul {{ padding-left:18px; margin:7px 0 0; }}
    .leaflet-tooltip {{ font-weight:800; color:#0f213f; border:1px solid #dfe7f0; box-shadow:0 4px 12px rgba(15,33,63,.12); }}
    .note {{ background:#eff6ff; color:#1d4f9c; border:1px solid #cfe0ff; border-radius:12px; padding:8px 10px; }}
  </style>
</head>
<body>
<div class="shell">
  <header>
    <div>
      <h1>MeteoVoid Belgique, carte interactive</h1>
      <p>Fond géographique OpenStreetMap, regroupement des points proches et affichage des détails au clic.</p>
    </div>
    <div class="score">
      <span class="pill">Score {float(aggregate.get('score', 0.0)):.3f}</span>
      <span class="pill">Sévérité {html.escape(str(aggregate.get('severity', 'n/a')))}</span>
      <span class="pill">{html.escape(str(target.get('start', 'n/a')))} à {html.escape(str(target.get('end', 'n/a')))}</span>
    </div>
  </header>
  <div id="map"></div>
  <footer>
    <span>Données : {source} | Mode : {data_mode} | Type : {source_type}</span>
    <span>Carte non officielle. Vérification IRM/KMI, MeteoAlarm, radar et foudre indispensable.</span>
  </footer>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<script>
const severityColors = {{normal:"{SEVERITY_COLORS['normal']}", watch:"{SEVERITY_COLORS['watch']}", medium:"{SEVERITY_COLORS['medium']}", high:"{SEVERITY_COLORS['high']}", alert:"{SEVERITY_COLORS['alert']}"}};
const stations = {stations_json};
const map = L.map('map', {{ zoomControl: true, scrollWheelZoom: true }}).setView([50.64, 4.65], 8);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  maxZoom: 12,
  attribution: '&copy; OpenStreetMap contributors'
}}).addTo(map);
const group = (L.markerClusterGroup ? L.markerClusterGroup({{ showCoverageOnHover:false, spiderfyOnMaxZoom:true, disableClusteringAtZoom:10, maxClusterRadius:38 }}) : L.layerGroup());
function esc(value) {{ return String(value ?? '').replace(/[&<>"']/g, ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}}[ch])); }}
function markerSize(score) {{ return 18 + Math.max(0, Math.min(1, Number(score || 0))) * 24; }}
for (const st of stations) {{
  const sev = String(st.severity || 'normal');
  const color = st.source_ok ? (severityColors[sev] || '#94a3b8') : '#94a3b8';
  const size = markerSize(st.score);
  const marker = L.marker([st.lat, st.lon], {{
    title: st.name,
    icon: L.divIcon({{
      className: 'risk-icon',
      html: `<span class="risk-dot" style="width:${{size}}px;height:${{size}}px;background:${{color}}"></span>`,
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
    }})
  }});
  const signals = Array.isArray(st.signals) ? st.signals : [];
  const popup = `<div class="popup"><h3>${{esc(st.name)}}</h3><div class="meta">${{esc(st.region)}} | score ${{Number(st.score || 0).toFixed(3)}} | ${{esc(sev)}} | ${{esc(st.worst_time || 'n/a')}}</div>${{signals.length ? '<ul>' + signals.map(s => '<li>' + esc(s) + '</li>').join('') + '</ul>' : '<div class="note">Aucun signal détaillé disponible.</div>'}}</div>`;
  marker.bindPopup(popup, {{ maxWidth: 360 }});
  marker.bindTooltip(esc(st.name), {{ permanent:false, direction:'top', offset:[0, -12] }});
  group.addLayer(marker);
}}
group.addTo(map);
if (stations.length) {{
  const bounds = L.latLngBounds(stations.map(st => [st.lat, st.lon]));
  map.fitBounds(bounds.pad(0.16));
}}
const legend = L.control({{ position: 'bottomleft' }});
legend.onAdd = function() {{
  const div = L.DomUtil.create('div', 'legend');
  div.innerHTML = '<h3>Sévérité</h3>' + ['normal','watch','medium','high','alert'].map(sev => `<div class="legend-row"><span class="legend-swatch" style="background:${{severityColors[sev]}}"></span>${{sev}}</div>`).join('') + '<p>La taille du marqueur reflète le score. Les points proches sont regroupés automatiquement.</p>';
  return div;
}};
legend.addTo(map);
</script>
</body>
</html>
"""


def _render_dashboard_map_svg(report: dict[str, Any]) -> str:
    # Kept as an offline fallback for environments where the Leaflet map cannot load.
    return _render_map_svg(report)


def _render_dashboard_html(report: dict[str, Any]) -> str:
    aggregate = report.get("aggregate", {})
    target = report.get("target_window", {})
    rows = _station_rows(report)
    generated_at = str(report.get("generated_at", "n/a"))
    score = float(aggregate.get("score") or 0.0)
    severity = str(aggregate.get("severity", "normal"))
    source_detail = html.escape(str(report.get("source_detail", "unknown")))
    source_type = html.escape(str(report.get("source_type", "unknown")))
    data_mode = html.escape(str(report.get("data_mode", "unknown")))
    last_sensitive = next((str(r.get("worst_time")) for r in rows if r.get("worst_time")), "n/a")
    active_count = int(aggregate.get("source_ok_count") or 0)
    error_count = int(aggregate.get("source_error_count") or 0)
    top_scores = [float(r.get("score") or 0.0) for r in rows[:6]] or [0.0]
    spark_points = []
    for i, val in enumerate(top_scores):
        x = 8 + i * (88 / max(1, len(top_scores) - 1))
        y = 48 - val * 34
        spark_points.append(f"{x:.1f},{y:.1f}")
    sparkline = " ".join(spark_points)

    def esc(value: Any) -> str:
        return html.escape(str(value), quote=True)

    def badge(sev: Any) -> str:
        sev_s = str(sev)
        return f'<span class="badge badge-{esc(sev_s)}">{esc(_severity_badge_label(sev_s))}</span>'

    station_rows: list[str] = []
    for item in rows:
        signals = "; ".join(str(x) for x in item.get("signals", []))
        station_rows.append(
            "<tr>"
            f"<td><strong>{esc(item.get('name', ''))}</strong><span>{esc(item.get('region', ''))}</span></td>"
            f"<td>{badge(item.get('severity', 'normal'))}</td>"
            f'<td class="num">{float(item.get("score") or 0.0):.3f}</td>'
            f"<td>{esc(_fmt_time(item.get('worst_time')))}</td>"
            f"<td>{esc(signals)}</td>"
            "</tr>"
        )

    insight_blocks: list[str] = []
    icon_map = {"heat": "Chaleur", "storm": "Orage", "rain": "Pluie"}
    for title, text, kind in _dashboard_insights(report):
        insight_blocks.append(
            f'<article class="insight insight-{esc(kind)}"><div class="insight-icon">{esc(icon_map.get(kind, "Info"))}</div>'
            f"<div><h3>{esc(title)}</h3><p>{esc(text)}</p></div></article>"
        )

    official_states = (
        report.get("integrations", {}) if isinstance(report.get("integrations"), dict) else {}
    )
    integrations_text = ", ".join(
        [
            f"IRM/KMI: {bool(official_states.get('official_warning_integrated', False))}",
            f"MeteoAlarm: {bool(official_states.get('metealarm_integrated', False))}",
            f"ESTOFEX: {bool(official_states.get('estofex_integrated', False))}",
            f"Radar: {bool(official_states.get('radar_integrated', False))}",
            f"Foudre: {bool(official_states.get('lightning_integrated', False))}",
        ]
    )

    return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MeteoVoid Belgique Dashboard</title>
  <style>
    :root {{ --bg:#f3f6fb; --panel:#ffffff; --ink:#0f213f; --muted:#607089; --line:#dfe7f0; --blue:#2b6fed; --normal:{SEVERITY_COLORS['normal']}; --watch:{SEVERITY_COLORS['watch']}; --medium:{SEVERITY_COLORS['medium']}; --high:{SEVERITY_COLORS['high']}; --alert:{SEVERITY_COLORS['alert']}; --shadow:0 14px 34px rgba(15, 33, 63, 0.08); }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--ink); font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .app {{ display:grid; grid-template-columns:228px 1fr; min-height:100vh; }}
    aside {{ background:linear-gradient(180deg, #0b1d37 0%, #102b4f 100%); color:#dbe7ff; padding:24px 18px; display:flex; flex-direction:column; gap:28px; }}
    .brand {{ display:flex; align-items:center; gap:12px; font-weight:800; letter-spacing:.2px; }}
    .logo {{ width:46px; height:46px; border-radius:15px; display:grid; place-items:center; background:rgba(255,255,255,.12); font-size:22px; }}
    nav {{ display:grid; gap:9px; }}
    nav a {{ color:#cbd7ee; text-decoration:none; padding:12px 14px; border-radius:13px; font-weight:650; }}
    nav a.active {{ background:rgba(43,111,237,.28); color:#fff; outline:1px solid rgba(137,172,255,.45); }}
    .status {{ margin-top:auto; border:1px solid rgba(210,226,255,.20); background:rgba(255,255,255,.07); border-radius:16px; padding:14px; font-size:13px; }}
    .dot {{ display:inline-block; width:10px; height:10px; border-radius:50%; background:#65c466; margin-right:8px; }}
    main {{ padding:28px 34px 24px; }}
    header {{ display:flex; align-items:flex-start; justify-content:space-between; gap:18px; margin-bottom:20px; }}
    h1 {{ margin:0; font-size:38px; line-height:1; letter-spacing:-1.2px; }}
    .subtitle {{ margin:8px 0 0; color:var(--muted); font-size:16px; }}
    .header-actions {{ display:flex; align-items:center; gap:16px; }}
    .refresh {{ border:1px solid var(--line); background:#fff; border-radius:12px; padding:10px 16px; font-weight:700; color:var(--blue); box-shadow:0 6px 18px rgba(15,33,63,.05); }}
    .stamp {{ color:var(--muted); text-align:right; font-size:14px; line-height:1.4; }}
    .kpis {{ display:grid; grid-template-columns:1.15fr 1fr 1.15fr .9fr 1.15fr; gap:14px; margin-bottom:16px; }}
    .card {{ background:var(--panel); border:1px solid var(--line); border-radius:18px; box-shadow:var(--shadow); }}
    .kpi {{ padding:18px 20px; min-height:116px; }}
    .kpi small {{ color:var(--muted); font-weight:800; letter-spacing:.06em; text-transform:uppercase; }}
    .kpi strong {{ display:block; margin-top:8px; font-size:32px; line-height:1; }}
    .kpi p {{ color:var(--muted); margin:10px 0 0; font-size:13px; }}
    .severity-word {{ color:var(--high); }}
    .spark {{ float:right; margin-top:4px; width:110px; height:54px; }}
    .layout {{ display:grid; grid-template-columns:minmax(640px, 1.9fr) minmax(300px, .9fr); gap:16px; align-items:stretch; }}
    .panel-title {{ padding:16px 18px 0; font-size:16px; font-weight:800; }}
    .map-panel {{ overflow:hidden; min-height:588px; }}
    .map-frame {{ width:100%; height:520px; border:0; display:block; border-radius:14px; background:#f8fbff; }}
    .map-wrap {{ padding:10px 14px 14px; }}
    .map-links {{ padding:0 18px 16px; display:flex; gap:12px; flex-wrap:wrap; color:var(--muted); font-size:13px; }}
    .map-links a {{ color:var(--blue); font-weight:800; text-decoration:none; }}
    .insights {{ padding:16px; display:grid; gap:12px; }}
    .insight {{ display:grid; grid-template-columns:76px 1fr; gap:13px; align-items:center; border:1px solid var(--line); border-radius:16px; padding:14px; background:linear-gradient(180deg, #fff, #fbfdff); }}
    .insight-icon {{ min-width:64px; height:38px; border-radius:999px; display:grid; place-items:center; font-size:12px; font-weight:900; }}
    .insight-heat .insight-icon {{ color:#b42318; background:rgba(216,86,70,.10); }}
    .insight-storm .insight-icon {{ color:#a15c07; background:rgba(229,147,58,.12); }}
    .insight-rain .insight-icon {{ color:#5b3190; background:rgba(110,63,160,.10); }}
    .insight h3 {{ margin:0 0 5px; font-size:15px; }}
    .insight p {{ margin:0; color:#34445b; font-size:13px; line-height:1.35; }}
    .info-strip {{ margin-top:2px; border:1px solid #cfe0ff; background:#eff6ff; color:#1d4f9c; border-radius:14px; padding:12px 14px; font-weight:650; font-size:13px; }}
    .table-card {{ margin-top:16px; overflow:hidden; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th {{ text-align:left; color:var(--muted); font-size:12px; letter-spacing:.03em; text-transform:uppercase; background:#f9fbfe; padding:13px 18px; border-bottom:1px solid var(--line); }}
    td {{ padding:11px 18px; border-bottom:1px solid #edf2f7; vertical-align:top; }}
    td span {{ display:block; color:var(--muted); font-size:12px; margin-top:2px; }}
    .num {{ font-variant-numeric:tabular-nums; font-weight:800; }}
    .badge {{ display:inline-flex; min-width:66px; justify-content:center; border-radius:999px; color:#fff; padding:4px 9px; font-weight:800; font-size:12px; }}
    .badge-normal {{ background:var(--normal); }} .badge-watch {{ background:var(--watch); }} .badge-medium {{ background:var(--medium); }} .badge-high {{ background:var(--high); }} .badge-alert {{ background:var(--alert); }}
    .meta {{ margin-top:14px; display:flex; justify-content:space-between; gap:16px; color:var(--muted); font-size:12px; flex-wrap:wrap; }}
    .foot {{ margin-top:16px; display:flex; justify-content:space-between; gap:18px; color:var(--muted); font-size:13px; }}
    @media (max-width:1100px) {{ .app {{ grid-template-columns:1fr; }} aside {{ display:none; }} .kpis, .layout {{ grid-template-columns:1fr; }} .map-frame {{ height:470px; }} header {{ flex-direction:column; }} }}
  </style>
</head>
<body>
  <div class="app">
    <aside>
      <div class="brand"><div class="logo">MV</div><div>MeteoVoid<br>Belgique</div></div>
      <nav><a class="active" href="#">Vue d'ensemble</a><a href="#stations">Stations</a><a href="belgium_alert_map.html">Carte</a><a href="#">Historique</a><a href="#">Paramètres</a></nav>
      <div class="status"><p><span class="dot"></span>Système opérationnel</p><p>Dernière mise à jour<br>{esc(generated_at)}</p></div>
    </aside>
    <main>
      <header>
        <div><h1>MeteoVoid Belgique</h1><p class="subtitle">Tableau de bord de surveillance météo pour la Belgique</p></div>
        <div class="header-actions"><button class="refresh">Actualiser</button><div class="stamp">{esc(generated_at)}<br>Europe/Brussels</div></div>
      </header>
      <section class="kpis">
        <article class="card kpi"><small>Score national</small><svg class="spark" viewBox="0 0 110 54"><polyline points="{sparkline}" fill="none" stroke="#2b6fed" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg><strong>{score:.3f}</strong><p>Plus le score est élevé, plus la vigilance augmente.</p></article>
        <article class="card kpi"><small>Sévérité nationale</small><strong class="severity-word">{esc(severity)}</strong><p>Niveau dominant issu du scoring modèle.</p></article>
        <article class="card kpi"><small>Fenêtre de veille</small><strong>{esc(target.get('start', 'n/a'))}<br>au {esc(target.get('end', 'n/a'))}</strong><p>Période couverte par l'analyse.</p></article>
        <article class="card kpi"><small>Stations évaluées</small><strong>{active_count}</strong><p>{error_count} station(s) en erreur de source.</p></article>
        <article class="card kpi"><small>Dernière heure sensible</small><strong>{esc(_fmt_time(last_sensitive))}</strong><p>Heure sensible la plus récente du top risque.</p></article>
      </section>
      <section class="layout">
        <article class="card map-panel"><div class="panel-title">Carte interactive des risques météo par station</div><div class="map-wrap"><iframe class="map-frame" src="belgium_alert_map.html" title="Carte interactive MeteoVoid Belgique"></iframe></div><div class="map-links"><a href="belgium_alert_map.html">Ouvrir la carte pleine page</a><span>Fond OpenStreetMap, clustering des points proches, détails au clic.</span></div></article>
        <article class="card"><div class="panel-title">Points clés et lecture opérationnelle</div><div class="insights">{''.join(insight_blocks)}<div class="info-strip">Données basées sur des prévisions modèle. Surveillance active recommandée, confirmation externe nécessaire.</div></div></article>
      </section>
      <section id="stations" class="card table-card">
        <div class="panel-title">Stations et évaluation des risques</div>
        <table><thead><tr><th>Station</th><th>Sévérité</th><th>Score</th><th>Heure sensible</th><th>Signaux</th></tr></thead><tbody>{''.join(station_rows)}</tbody></table>
      </section>
      <div class="meta"><span>Données : {source_detail} | Mode : {data_mode} | Type : {source_type}</span><span>{esc(integrations_text)}</span></div>
      <footer class="foot"><strong>MeteoVoid Belgique</strong><span>Données non contractuelles. Comparaison indispensable avec IRM/KMI, MeteoAlarm, radar et foudre.</span></footer>
    </main>
  </div>
</body>
</html>
"""


def _json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _level_score(value: str, mapping: dict[str, float]) -> float:
    return mapping.get(str(value).strip().lower(), 0.0)


def _external_confirmation_from_inputs(
    *,
    irm_warning_level: str,
    metealarm_level: str,
    estofex_level: str,
    radar_confirmation: str,
    lightning_confirmation: str,
    external_note: str,
) -> dict[str, Any]:
    official_scores = [
        _level_score(irm_warning_level, {"none": 0.0, "yellow": 0.35, "orange": 0.70, "red": 1.0}),
        _level_score(metealarm_level, {"none": 0.0, "yellow": 0.35, "orange": 0.70, "red": 1.0}),
        _level_score(estofex_level, {"none": 0.0, "level1": 0.45, "level2": 0.75, "level3": 1.0}),
        _level_score(
            radar_confirmation, {"none": 0.0, "weak": 0.25, "moderate": 0.60, "strong": 0.90}
        ),
        _level_score(lightning_confirmation, {"none": 0.0, "nearby": 0.45, "confirmed": 0.85}),
    ]
    weights = [0.24, 0.21, 0.20, 0.20, 0.15]
    score = round(sum(s * w for s, w in zip(official_scores, weights, strict=False)), 6)
    active = []
    if irm_warning_level != "none":
        active.append(f"IRM/KMI {irm_warning_level}")
    if metealarm_level != "none":
        active.append(f"MeteoAlarm {metealarm_level}")
    if estofex_level != "none":
        active.append(f"ESTOFEX {estofex_level}")
    if radar_confirmation != "none":
        active.append(f"radar {radar_confirmation}")
    if lightning_confirmation != "none":
        active.append(f"foudre {lightning_confirmation}")
    if score >= 0.75:
        status = "confirmed_high"
    elif score >= 0.40:
        status = "partially_confirmed"
    elif score > 0.0:
        status = "weak_confirmation"
    else:
        status = "not_integrated_or_not_confirmed"
    summary = "; ".join(active) if active else "Aucune confirmation externe renseignée dans ce run."
    if external_note.strip():
        summary = f"{summary} Note : {external_note.strip()}"
    return {
        "score": score,
        "status": status,
        "summary": summary,
        "inputs": {
            "irm_warning_level": irm_warning_level,
            "metealarm_level": metealarm_level,
            "estofex_level": estofex_level,
            "radar_confirmation": radar_confirmation,
            "lightning_confirmation": lightning_confirmation,
            "external_note": external_note.strip(),
        },
    }


def _components_summary(stations: list[dict[str, Any]]) -> dict[str, Any]:
    keys = ["heat", "moisture", "precipitation", "wind_gust", "pressure_drop", "weather_code"]
    ok = [s for s in stations if s.get("source_ok")]
    summary: dict[str, Any] = {}
    for key in keys:
        vals = []
        for station in ok:
            comps = station.get("components", {})
            if isinstance(comps, dict):
                val = _safe_float(comps.get(key))
                if val is not None:
                    vals.append(val)
        summary[key] = {
            "mean": round(sum(vals) / len(vals), 6) if vals else 0.0,
            "max": round(max(vals), 6) if vals else 0.0,
        }
    return summary


def _source_status(report: dict[str, Any]) -> dict[str, Any]:
    stations = [s for s in report.get("stations", []) if isinstance(s, dict)]
    total = len(stations)
    ok = [s for s in stations if s.get("source_ok")]
    errors = [s for s in stations if not s.get("source_ok")]
    health = (len(ok) / total) if total else 0.0
    ext = report.get("external_confirmation", {})
    integrations = report.get("integrations", {})
    return {
        "generated_at": report.get("generated_at"),
        "primary_source": report.get("source_detail"),
        "data_mode": report.get("data_mode"),
        "source_type": report.get("source_type"),
        "source_health_score": round(health, 6),
        "source_ok_count": len(ok),
        "source_error_count": len(errors),
        "station_errors": [
            {
                "station_id": s.get("station_id"),
                "name": s.get("name"),
                "error": s.get("error"),
            }
            for s in errors
        ],
        "external_confirmation": ext,
        "integrations": integrations,
        "limits": report.get("limits", []),
    }


def _read_last_history_row(history_csv: Path) -> dict[str, str] | None:
    if not history_csv.exists():
        return None
    try:
        with history_csv.open("r", encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
    except OSError:
        return None
    if not rows:
        return None
    return rows[-1]


def _trend_from_history(report: dict[str, Any], history_dir: Path) -> dict[str, Any]:
    previous = _read_last_history_row(history_dir / "belgium_alert_history.csv")
    if not previous:
        return {
            "status": "no_history",
            "comparison_runs": 0,
            "delta_score": 0.0,
            "previous_score": None,
            "current_score": float(report.get("aggregate", {}).get("score") or 0.0),
            "summary": "Aucun historique local disponible pour comparer ce run.",
        }
    current = float(report.get("aggregate", {}).get("score") or 0.0)
    prev = _safe_float(previous.get("national_score")) or 0.0
    delta = round(current - prev, 6)
    if delta >= 0.08:
        status = "rising_fast"
    elif delta >= 0.025:
        status = "rising"
    elif delta <= -0.08:
        status = "falling_fast"
    elif delta <= -0.025:
        status = "falling"
    else:
        status = "stable"
    return {
        "status": status,
        "comparison_runs": 1,
        "delta_score": delta,
        "previous_score": prev,
        "previous_generated_at": previous.get("generated_at"),
        "current_score": current,
        "summary": f"Score précédent {prev:.3f}, score actuel {current:.3f}, écart {delta:+.3f}.",
    }


def _operational_state(report: dict[str, Any]) -> dict[str, Any]:
    aggregate = report.get("aggregate", {})
    model_score = float(aggregate.get("score") or 0.0)
    model_severity = str(aggregate.get("severity", "normal"))
    external = report.get("external_confirmation", {})
    external_score = float(external.get("score") or 0.0) if isinstance(external, dict) else 0.0
    trend = report.get("trend", {})
    trend_status = (
        str(trend.get("status", "no_history")) if isinstance(trend, dict) else "no_history"
    )
    source_health = _source_status(report).get("source_health_score", 0.0)

    if model_score >= 0.78 and external_score >= 0.40:
        level = "alert_confirmed"
        reason = "signal modèle très élevé et confirmation externe partielle ou forte"
    elif model_score >= 0.65 and external_score >= 0.40:
        level = "pre_alert_confirmed"
        reason = "signal modèle élevé et confirmation externe partielle"
    elif model_score >= 0.65:
        level = "watch_reinforced"
        reason = "signal modèle élevé, confirmation externe encore absente ou insuffisante"
    elif model_score >= 0.50 or external_score >= 0.40:
        level = "watch"
        reason = "signal à surveiller, sans convergence suffisante pour alerte"
    elif model_score >= 0.35:
        level = "low_watch"
        reason = "signal faible à modéré"
    else:
        level = "normal"
        reason = "pas de signal notable dans la grille suivie"

    if source_health < 0.75:
        reason = f"{reason}. Attention : qualité source dégradée"
    if trend_status in {"rising", "rising_fast"} and level in {"watch", "watch_reinforced"}:
        reason = f"{reason}. Tendance en hausse"
    return {
        "level": level,
        "reason": reason,
        "model_score": round(model_score, 6),
        "model_severity": model_severity,
        "external_confirmation_score": round(external_score, 6),
        "source_health_score": round(float(source_health), 6),
        "trend_status": trend_status,
        "public_alert_allowed": level in {"pre_alert_confirmed", "alert_confirmed"},
        "public_alert_caution": "Ne jamais publier comme alerte officielle. Comparer avec IRM/KMI, MeteoAlarm, radar et foudre.",
    }


def _history_row(report: dict[str, Any], run_id: str) -> dict[str, Any]:
    stations = [s for s in report.get("stations", []) if isinstance(s, dict)]
    rows = _station_rows(report)
    top = rows[0] if rows else {}
    aggregate = report.get("aggregate", {})
    external = report.get("external_confirmation", {})
    operational = report.get("operational_state", {})
    return {
        "run_id": run_id,
        "generated_at": report.get("generated_at"),
        "target_start": report.get("target_window", {}).get("start"),
        "target_end": report.get("target_window", {}).get("end"),
        "national_score": float(aggregate.get("score") or 0.0),
        "severity": aggregate.get("severity"),
        "operational_level": operational.get("level"),
        "external_confirmation_score": (
            float(external.get("score") or 0.0) if isinstance(external, dict) else 0.0
        ),
        "source_ok_count": aggregate.get("source_ok_count"),
        "source_error_count": aggregate.get("source_error_count"),
        "top_station_id": top.get("station_id"),
        "top_station_name": top.get("name"),
        "top_station_score": float(top.get("score") or 0.0),
        "nb_high": sum(1 for s in stations if str(s.get("severity")) == "high"),
        "nb_alert": sum(1 for s in stations if str(s.get("severity")) == "alert"),
        "trend_status": report.get("trend", {}).get("status"),
    }


def _append_history(report: dict[str, Any], history_dir: Path, run_id: str) -> Path:
    history_dir.mkdir(parents=True, exist_ok=True)
    csv_path = history_dir / "belgium_alert_history.csv"
    row = _history_row(report, run_id)
    fieldnames = list(row.keys())
    write_header = not csv_path.exists()
    with csv_path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerow(row)
    return csv_path


def _write_manifest(out_dir: Path, run_id: str) -> Path:
    files = []
    for path in sorted(out_dir.iterdir()):
        if path.is_file() and path.name != "manifest.json":
            files.append(
                {
                    "path": path.name,
                    "bytes": path.stat().st_size,
                    "sha256": _sha256_file(path),
                }
            )
    manifest = {
        "run_id": run_id,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "files": files,
    }
    path = out_dir / "manifest.json"
    path.write_text(_json_dumps(manifest), encoding="utf-8")
    return path


def _snapshot_run(out_dir: Path, history_dir: Path, run_id: str) -> None:
    run_dir = history_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    for path in out_dir.iterdir():
        if path.is_file():
            shutil.copy2(path, run_dir / path.name)


def _render_markdown(report: dict[str, Any]) -> str:
    aggregate = report["aggregate"]
    stations = report["stations"]
    data_mode = report.get("data_mode", "unknown")
    source_type = report.get("source_type", "unknown")
    source_detail = report.get("source_detail", report.get("source", "unknown"))
    integrations = report.get("integrations", {})
    external = report.get("external_confirmation", {})
    operational = report.get("operational_state", {})
    trend = report.get("trend", {})
    components_summary = report.get("components_summary", {})

    lines: list[str] = []
    lines.append("# MeteoVoid Belgium Alert Watch")
    lines.append("")
    lines.append(f"Généré le : `{report['generated_at']}`")
    lines.append(
        f"Fenêtre analysée : `{report['target_window']['start']}` à "
        f"`{report['target_window']['end']}`"
    )
    lines.append(f"Score national : `{aggregate['score']:.3f}`")
    lines.append(f"Sévérité modèle : `{aggregate['severity']}`")
    lines.append(f"Niveau opérationnel : `{operational.get('level', 'n/a')}`")
    lines.append(f"Raison : {operational.get('reason', 'n/a')}")
    lines.append("")
    lines.append("## Source et limites")
    lines.append("")
    lines.append(f"Source principale : `{source_detail}`")
    lines.append(f"Mode de données : `{data_mode}`")
    lines.append(f"Type de source : `{source_type}`")
    lines.append(
        "Données récupérées au moment de l’exécution"
        if data_mode == "live_forecast_api"
        else "Données de démonstration déterministes, sans accès réseau"
    )
    lines.append("")
    lines.append("## Confirmation externe")
    lines.append("")
    lines.append(f"Score de confirmation externe : `{float(external.get('score') or 0.0):.3f}`")
    lines.append(f"Statut : `{external.get('status', 'n/a')}`")
    lines.append(f"Synthèse : {external.get('summary', 'n/a')}")
    lines.append("")
    lines.append("Intégrations externes actives ou renseignées dans ce run :")
    lines.append(
        f"- Avertissements officiels IRM/KMI : `{bool(integrations.get('official_warning_integrated', False))}`"
    )
    lines.append(f"- MeteoAlarm : `{bool(integrations.get('metealarm_integrated', False))}`")
    lines.append(f"- ESTOFEX : `{bool(integrations.get('estofex_integrated', False))}`")
    lines.append(f"- Radar : `{bool(integrations.get('radar_integrated', False))}`")
    lines.append(f"- Foudre : `{bool(integrations.get('lightning_integrated', False))}`")
    lines.append("")
    lines.append("## Tendance")
    lines.append("")
    lines.append(f"Statut : `{trend.get('status', 'no_history')}`")
    lines.append(f"Résumé : {trend.get('summary', 'n/a')}")
    lines.append("")
    lines.append("## Résumé des composantes modèle")
    lines.append("")
    lines.append("| Composante | Moyenne | Maximum |")
    lines.append("|---|---:|---:|")
    for key, value in components_summary.items() if isinstance(components_summary, dict) else []:
        if isinstance(value, dict):
            lines.append(
                f"| {key} | {float(value.get('mean') or 0.0):.3f} | {float(value.get('max') or 0.0):.3f} |"
            )
    lines.append("")
    lines.append(
        "Ce rapport est une veille basée sur modèle. Ce n’est pas une alerte officielle. "
        "Pour la sécurité publique, il doit toujours être comparé avec l’IRM/KMI, "
        "MeteoAlarm, le radar et le nowcast foudre."
    )
    lines.append("")
    lines.append("## Fichiers générés")
    lines.append("")
    lines.append("- `belgium_alert_dashboard.html`")
    lines.append("- `belgium_alert_map.html`")
    lines.append("- `belgium_alert_map.svg`")
    lines.append("- `belgium_alert_report.json`")
    lines.append("- `risk_by_station.csv`")
    lines.append("- `risk_by_station.geojson`")
    lines.append("- `source_status.json`")
    lines.append("- `alert_state.json`")
    lines.append("- `history.csv`")
    lines.append("- `manifest.json`")
    lines.append("")
    lines.append("## Stations les plus sensibles")
    lines.append("")
    lines.append(
        "| Station | Région | Sévérité | Score | Heure sensible | Tmax °C | Point de rosée °C | "
        "Précip % | Précip mm/h | Rafales m/s | Baisse hPa/6h | Signaux |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    ordered = sorted(stations, key=lambda x: float(x["score"]), reverse=True)
    for item in ordered[:12]:
        signals = "; ".join(item.get("signals", []))
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item["name"]),
                    str(item["region"]),
                    str(item["severity"]),
                    f"{float(item['score']):.3f}",
                    str(item.get("worst_time") or "n/a"),
                    _fmt(item.get("max_temperature_c")),
                    _fmt(item.get("max_dew_point_c")),
                    _fmt(item.get("max_precip_probability_pct"), 0),
                    _fmt(item.get("max_precipitation_mm_h")),
                    _fmt(item.get("max_wind_gust_ms")),
                    _fmt(item.get("max_pressure_drop_6h_hpa")),
                    signals.replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    lines.append("## Notes opérationnelles")
    lines.append("")
    lines.append("- `normal` : pas de signal notable.")
    lines.append("- `low_watch` ou `watch` : garder la situation sous surveillance.")
    lines.append("- `watch_reinforced` : surveillance rapprochée, comparaison externe nécessaire.")
    lines.append("- `pre_alert_confirmed` : signal modèle et confirmation externe convergents.")
    lines.append(
        "- `alert_confirmed` : publier seulement avec formulation prudente et renvoi vers sources officielles."
    )
    lines.append("")
    return "\n".join(lines)


def _write_outputs(report: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "belgium_alert_report.json"
    report_path.write_text(_json_dumps(report), encoding="utf-8")
    (out_dir / "belgium_alert_report.md").write_text(_render_markdown(report), encoding="utf-8")
    (out_dir / "belgium_alert_map.svg").write_text(_render_map_svg(report), encoding="utf-8")
    (out_dir / "belgium_alert_map.html").write_text(_render_map_html(report), encoding="utf-8")
    (out_dir / "belgium_alert_dashboard.html").write_text(
        _render_dashboard_html(report), encoding="utf-8"
    )
    (out_dir / "risk_by_station.geojson").write_text(
        _json_dumps(_render_geojson(report)),
        encoding="utf-8",
    )
    (out_dir / "source_status.json").write_text(
        _json_dumps(_source_status(report)), encoding="utf-8"
    )
    (out_dir / "alert_state.json").write_text(
        _json_dumps(report.get("operational_state", {})), encoding="utf-8"
    )

    rows = report["stations"]
    csv_path = out_dir / "risk_by_station.csv"
    fieldnames = [
        "station_id",
        "name",
        "region",
        "score",
        "severity",
        "worst_time",
        "max_temperature_c",
        "max_dew_point_c",
        "max_relative_humidity_pct",
        "max_precip_probability_pct",
        "max_precipitation_mm_h",
        "max_wind_gust_ms",
        "max_pressure_drop_6h_hpa",
        "component_heat",
        "component_moisture",
        "component_precipitation",
        "component_wind_gust",
        "component_pressure_drop",
        "component_weather_code",
        "thunderstorm_code_seen",
        "shower_code_seen",
        "source_ok",
        "error",
        "signals",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            comps = row.get("components", {}) if isinstance(row.get("components"), dict) else {}
            writer.writerow(
                {
                    **{k: row.get(k) for k in fieldnames if not k.startswith("component_")},
                    "component_heat": comps.get("heat"),
                    "component_moisture": comps.get("moisture"),
                    "component_precipitation": comps.get("precipitation"),
                    "component_wind_gust": comps.get("wind_gust"),
                    "component_pressure_drop": comps.get("pressure_drop"),
                    "component_weather_code": comps.get("weather_code"),
                    "signals": "; ".join(row.get("signals", [])),
                }
            )


def _should_send_webhook(severity: str, min_severity: str) -> bool:
    return SEVERITY_RANK.get(severity, 0) >= SEVERITY_RANK.get(min_severity, 2)


def _send_webhook(url: str, report: dict[str, Any], *, timeout_s: float) -> None:
    payload = {
        "source": "MeteoVoid Belgium Alert Watch",
        "generated_at": report["generated_at"],
        "target_window": report["target_window"],
        "aggregate": report["aggregate"],
        "external_confirmation": report.get("external_confirmation"),
        "operational_state": report.get("operational_state"),
        "trend": report.get("trend"),
        "top_stations": report["aggregate"].get("top_stations", []),
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=timeout_s) as response:  # noqa: S310
        response.read()


def _build_report(
    *,
    stations_path: Path,
    target: TargetWindow,
    timezone: str,
    timeout_s: float,
    offline_demo: bool,
    external_confirmation: dict[str, Any],
) -> dict[str, Any]:
    config = load_stations_config(stations_path)
    risks: list[StationRisk] = []
    for station in config.stations:
        try:
            if station.source != "openmeteo":
                raise ValueError(f"Unsupported station source: {station.source}")
            if offline_demo:
                payload = _offline_payload(station, target=target)
            else:
                url = _build_openmeteo_forecast_url(station, target=target, timezone=timezone)
                payload = _http_json(url, timeout_s=timeout_s)
            risks.append(_station_risk_from_payload(station, payload))
        except (OSError, URLError, TimeoutError, ValueError) as exc:
            risks.append(_failed_station(station, str(exc)))

    stations = [asdict(r) for r in risks]
    aggregate = _aggregate_risk(risks)
    generated = datetime.now().astimezone().isoformat(timespec="seconds")
    source = "openmeteo_forecast" if not offline_demo else "offline_demo"
    data_mode = "live_forecast_api" if not offline_demo else "offline_demo"
    source_type = "model_forecast" if not offline_demo else "synthetic_demo"
    source_detail = (
        "Open-Meteo Forecast API" if not offline_demo else "Deterministic offline demo payload"
    )
    external_inputs = (
        external_confirmation.get("inputs", {}) if isinstance(external_confirmation, dict) else {}
    )
    return {
        "generated_at": generated,
        "source": source,
        "data_mode": data_mode,
        "source_type": source_type,
        "source_detail": source_detail,
        "timezone": timezone,
        "target_window": {
            "start": target.start.isoformat(),
            "end": target.end.isoformat(),
            "label": target.label,
        },
        "integrations": {
            "official_warning_integrated": external_inputs.get("irm_warning_level", "none")
            != "none",
            "metealarm_integrated": external_inputs.get("metealarm_level", "none") != "none",
            "estofex_integrated": external_inputs.get("estofex_level", "none") != "none",
            "radar_integrated": external_inputs.get("radar_confirmation", "none") != "none",
            "lightning_integrated": external_inputs.get("lightning_confirmation", "none") != "none",
        },
        "external_confirmation": external_confirmation,
        "outputs": {
            "json": "belgium_alert_report.json",
            "markdown": "belgium_alert_report.md",
            "csv": "risk_by_station.csv",
            "geojson": "risk_by_station.geojson",
            "map_svg": "belgium_alert_map.svg",
            "map_html": "belgium_alert_map.html",
            "dashboard_html": "belgium_alert_dashboard.html",
            "source_status": "source_status.json",
            "alert_state": "alert_state.json",
            "history": "history.csv",
            "manifest": "manifest.json",
        },
        "aggregate": aggregate,
        "components_summary": _components_summary(stations),
        "stations": stations,
        "limits": [
            "Ce rapport n’est pas un avertissement météorologique officiel.",
            "Utiliser les avertissements officiels IRM/KMI, MeteoAlarm, le radar et la foudre avant toute alerte publique.",
            "Les codes météo Open-Meteo et les prévisions horaires peuvent évoluer rapidement en contexte convectif.",
        ],
    }


def _sync_history_outputs(
    report: dict[str, Any], out_dir: Path, history_dir: Path, run_id: str
) -> None:
    history_csv = _append_history(report, history_dir, run_id)
    shutil.copy2(history_csv, out_dir / "history.csv")
    _write_manifest(out_dir, run_id)
    _snapshot_run(out_dir, history_dir, run_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Génère un rapport de veille météo pour la Belgique."
    )
    parser.add_argument(
        "--stations", default="config/stations_belgium.yaml", help="Stations YAML file"
    )
    parser.add_argument("--out-dir", default="_ci_out/belgium_alert", help="Output directory")
    parser.add_argument(
        "--target-date",
        default="auto",
        help="auto, today, tomorrow, next-friday or YYYY-MM-DD",
    )
    parser.add_argument(
        "--horizon-days", type=int, default=5, help="Used only with --target-date auto"
    )
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE, help="Forecast timezone")
    parser.add_argument("--timeout-s", type=float, default=10.0, help="HTTP timeout per station")
    parser.add_argument("--offline-demo", action="store_true", help="Use deterministic demo data")
    parser.add_argument("--webhook-url", default="", help="URL webhook JSON générique optionnelle")
    parser.add_argument("--min-severity", default="medium", choices=sorted(SEVERITY_RANK))
    parser.add_argument("--fail-on-webhook-error", action="store_true")
    parser.add_argument("--history-dir", default="", help="Persistent history directory")
    parser.add_argument("--no-history", action="store_true", help="Do not append local history")
    parser.add_argument("--run-id", default="", help="Optional run id for reproducible snapshots")
    parser.add_argument(
        "--irm-warning-level",
        default="none",
        choices=["none", "yellow", "orange", "red"],
        help="Manual or future connector value for IRM/KMI warning level",
    )
    parser.add_argument(
        "--metealarm-level",
        default="none",
        choices=["none", "yellow", "orange", "red"],
        help="Manual or future connector value for MeteoAlarm level",
    )
    parser.add_argument(
        "--estofex-level",
        default="none",
        choices=["none", "level1", "level2", "level3"],
        help="Manual or future connector value for ESTOFEX level",
    )
    parser.add_argument(
        "--radar-confirmation",
        default="none",
        choices=["none", "weak", "moderate", "strong"],
        help="Manual radar confirmation state",
    )
    parser.add_argument(
        "--lightning-confirmation",
        default="none",
        choices=["none", "nearby", "confirmed"],
        help="Manual lightning confirmation state",
    )
    parser.add_argument("--external-note", default="", help="Free-text external context note")
    args = parser.parse_args(argv)

    target = _parse_target_window(args.target_date, horizon_days=args.horizon_days)
    out_dir = Path(args.out_dir)
    history_dir = Path(args.history_dir) if args.history_dir.strip() else (out_dir / "history")
    run_id = args.run_id.strip() or datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    external_confirmation = _external_confirmation_from_inputs(
        irm_warning_level=args.irm_warning_level,
        metealarm_level=args.metealarm_level,
        estofex_level=args.estofex_level,
        radar_confirmation=args.radar_confirmation,
        lightning_confirmation=args.lightning_confirmation,
        external_note=args.external_note,
    )
    report = _build_report(
        stations_path=Path(args.stations),
        target=target,
        timezone=args.timezone,
        timeout_s=float(args.timeout_s),
        offline_demo=bool(args.offline_demo),
        external_confirmation=external_confirmation,
    )
    report["run_id"] = run_id
    report["trend"] = _trend_from_history(report, history_dir)
    report["operational_state"] = _operational_state(report)
    _write_outputs(report, out_dir)

    if not args.no_history:
        _sync_history_outputs(report, out_dir, history_dir, run_id)
    else:
        _write_manifest(out_dir, run_id)

    webhook_url = args.webhook_url.strip()
    min_severity = args.min_severity
    notification_severity = report["aggregate"]["severity"]
    if report.get("operational_state", {}).get("level") in {
        "pre_alert_confirmed",
        "alert_confirmed",
    }:
        notification_severity = "alert"
    if webhook_url and _should_send_webhook(notification_severity, min_severity):
        try:
            _send_webhook(webhook_url, report, timeout_s=float(args.timeout_s))
        except (OSError, URLError, TimeoutError, ValueError) as exc:
            message = f"Échec du webhook : {exc}"
            if args.fail_on_webhook_error:
                raise SystemExit(message) from exc
            print(message, file=sys.stderr)

    for name in [
        "belgium_alert_report.json",
        "belgium_alert_report.md",
        "belgium_alert_map.svg",
        "belgium_alert_map.html",
        "belgium_alert_dashboard.html",
        "risk_by_station.geojson",
        "risk_by_station.csv",
        "source_status.json",
        "alert_state.json",
        "history.csv",
        "manifest.json",
    ]:
        path = out_dir / name
        if path.exists():
            print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
