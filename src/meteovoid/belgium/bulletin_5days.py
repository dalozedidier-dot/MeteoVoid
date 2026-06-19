"""Classic 5-day Belgium weather bulletin.

This module deliberately separates a public, classic forecast from the expert
convective engine. It fetches only daily/hourly forecast fields that are exposed
by Open-Meteo and labels the result as non-official. When live access is not
available, callers can use deterministic offline data for CI and local demos.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_TIMEZONE = "Europe/Brussels"
OPEN_METEO_ENDPOINT = "https://api.open-meteo.com/v1/forecast"


@dataclass(frozen=True)
class ForecastZone:
    key: str
    label: str
    lat: float
    lon: float
    province_group: str


DEFAULT_ZONES: tuple[ForecastZone, ...] = (
    ForecastZone("coast", "Côte belge", 51.23, 2.92, "Côte"),
    ForecastZone("flanders_west", "Flandre occidentale", 51.21, 3.22, "Flandre"),
    ForecastZone("flanders_east", "Flandre orientale", 51.05, 3.73, "Flandre"),
    ForecastZone("brussels_brabant", "Bruxelles / Brabant", 50.85, 4.35, "Centre"),
    ForecastZone("hainaut", "Hainaut", 50.45, 3.95, "Wallonie"),
    ForecastZone("namur", "Namur", 50.47, 4.87, "Wallonie"),
    ForecastZone("liege", "Liège", 50.63, 5.57, "Wallonie"),
    ForecastZone("luxembourg", "Luxembourg / Ardenne", 49.92, 5.38, "Ardenne"),
)

DAILY_VARIABLES = [
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "apparent_temperature_max",
    "precipitation_probability_max",
    "precipitation_sum",
    "wind_gusts_10m_max",
    "wind_speed_10m_max",
]

HOURLY_CONVECTIVE_VARIABLES = [
    "temperature_2m",
    "dew_point_2m",
    "relative_humidity_2m",
    "precipitation_probability",
    "pressure_msl",
    "wind_gusts_10m",
    "cape",
    "convective_inhibition",
    "lifted_index",
    "total_column_integrated_water_vapour",
]


class BulletinError(RuntimeError):
    """Raised when a live bulletin cannot be generated."""


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _as_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        out = float(value)
        if math.isnan(out):
            return None
        return out
    except (TypeError, ValueError):
        return None


def _round(value: Any, ndigits: int = 1) -> float | None:
    number = _as_float(value)
    return round(number, ndigits) if number is not None else None


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _load_zone_config(path: Path | None) -> list[ForecastZone]:
    if path is None or not path.exists():
        return list(DEFAULT_ZONES)
    try:
        import yaml
    except ModuleNotFoundError as exc:  # pragma: no cover - package dependency exists in repo
        raise BulletinError("PyYAML is required to read Belgium forecast zones") from exc
    raw = _dict_or_empty(yaml.safe_load(path.read_text(encoding="utf-8")))
    zones = _list_or_empty(raw.get("zones"))
    if not zones:
        return list(DEFAULT_ZONES)
    parsed: list[ForecastZone] = []
    for item in zones:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        label = str(item.get("label") or key).strip()
        lat = _as_float(item.get("lat"))
        lon = _as_float(item.get("lon"))
        if not key or lat is None or lon is None:
            continue
        parsed.append(
            ForecastZone(
                key=key,
                label=label,
                lat=lat,
                lon=lon,
                province_group=str(item.get("province_group") or "").strip(),
            )
        )
    return parsed or list(DEFAULT_ZONES)


def _weather_code_label(code: Any) -> str:
    c = int(_as_float(code) or 0)
    if c == 0:
        return "temps généralement ensoleillé"
    if c in {1, 2, 3}:
        return "alternance de soleil et de nuages"
    if c in {45, 48}:
        return "brume ou brouillard par moments"
    if c in {51, 53, 55, 56, 57}:
        return "bruine ou faibles précipitations"
    if c in {61, 63, 65, 66, 67, 80, 81, 82}:
        return "averses ou pluie par moments"
    if c in {71, 73, 75, 77, 85, 86}:
        return "précipitations hivernales possibles"
    if c in {95, 96, 99}:
        return "risque d’orages"
    return "temps variable"


def _risk_note(day: dict[str, Any]) -> str:
    code = int(_as_float(day.get("weather_code")) or 0)
    pop = _as_float(day.get("precipitation_probability_max")) or 0.0
    tmax = _as_float(day.get("temperature_2m_max"))
    gust = _as_float(day.get("wind_gusts_10m_max"))
    notes: list[str] = []
    if code in {95, 96, 99} or pop >= 60:
        notes.append("risque d’averses localement orageuses à surveiller")
    if tmax is not None and tmax >= 30:
        notes.append("chaleur marquée")
    if gust is not None and gust >= 55:
        notes.append("rafales sensibles possibles")
    return "; ".join(notes) if notes else "pas de signal météo marqué dans le bulletin brut"


def _fetch_json(url: str, *, timeout_s: float) -> dict[str, Any]:
    req = Request(url, headers={"User-Agent": "MeteoVoid/Belgium-5day-bulletin"})
    with urlopen(req, timeout=timeout_s) as response:  # noqa: S310 - public weather API
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise BulletinError("Open-Meteo returned a non-object JSON payload")
    return payload


def _openmeteo_url(zone: ForecastZone, *, model: str, timezone: str, days: int) -> str:
    params: dict[str, Any] = {
        "latitude": f"{zone.lat:.4f}",
        "longitude": f"{zone.lon:.4f}",
        "daily": ",".join(DAILY_VARIABLES),
        "hourly": ",".join(HOURLY_CONVECTIVE_VARIABLES),
        "forecast_days": str(days),
        "timezone": timezone,
        "wind_speed_unit": "kmh",
    }
    if model and model != "best_match":
        params["models"] = model
    return f"{OPEN_METEO_ENDPOINT}?{urlencode(params)}"


def _day_from_daily(daily: dict[str, Any], idx: int) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, values in daily.items():
        if isinstance(values, list) and idx < len(values):
            out[key] = values[idx]
    out["weather_label"] = _weather_code_label(out.get("weather_code"))
    out["risk_note"] = _risk_note(out)
    return out


def _hourly_extremes(payload: dict[str, Any]) -> dict[str, Any]:
    hourly = _dict_or_empty(payload.get("hourly"))

    def values(key: str) -> list[float]:
        raw = _list_or_empty(hourly.get(key))
        parsed = [_as_float(x) for x in raw]
        return [x for x in parsed if x is not None]

    return {
        "dew_point_max_c": _round(max(values("dew_point_2m"), default=float("nan"))),
        "cape_max_j_kg": _round(max(values("cape"), default=float("nan")), 0),
        "cin_min_j_kg": _round(min(values("convective_inhibition"), default=float("nan")), 0),
        "lifted_index_min_c": _round(min(values("lifted_index"), default=float("nan")), 1),
        "pwat_max_mm": _round(
            max(values("total_column_integrated_water_vapour"), default=float("nan")), 1
        ),
        "pressure_min_hpa": _round(min(values("pressure_msl"), default=float("nan")), 1),
        "humidity_max_pct": _round(max(values("relative_humidity_2m"), default=float("nan")), 0),
    }


def _zone_live_forecast(
    zone: ForecastZone,
    *,
    model: str,
    timezone: str,
    days: int,
    timeout_s: float,
) -> dict[str, Any]:
    url = _openmeteo_url(zone, model=model, timezone=timezone, days=days)
    payload = _fetch_json(url, timeout_s=timeout_s)
    daily = _dict_or_empty(payload.get("daily"))
    dates = _list_or_empty(daily.get("time"))
    day_rows = [_day_from_daily(daily, idx) for idx in range(min(days, len(dates)))]
    extremes = _hourly_extremes(payload)
    return {
        "key": zone.key,
        "label": zone.label,
        "lat": zone.lat,
        "lon": zone.lon,
        "province_group": zone.province_group,
        "source": "Open-Meteo Forecast API",
        "model": model,
        "days": day_rows,
        "convective_extremes": extremes,
        "source_url": url,
    }


def _offline_zone_forecast(
    zone: ForecastZone, *, days: int, start: date | None = None
) -> dict[str, Any]:
    base = start or datetime.now(tz=UTC).date()
    day_rows: list[dict[str, Any]] = []
    for idx in range(days):
        tmax = 24.0 + idx * 0.8 + (1.5 if zone.key in {"hainaut", "brussels_brabant"} else 0.0)
        pop = 20 + (idx % 3) * 15
        code = 95 if idx in {1, 4} and pop >= 35 else (61 if pop >= 35 else 2)
        row = {
            "time": (base + timedelta(days=idx)).isoformat(),
            "weather_code": code,
            "temperature_2m_max": round(tmax, 1),
            "temperature_2m_min": round(max(10.0, tmax - 9.0), 1),
            "apparent_temperature_max": round(tmax + 1.5, 1),
            "precipitation_probability_max": pop,
            "precipitation_sum": round(max(0.0, pop - 25) / 10.0, 1),
            "wind_gusts_10m_max": 28 + idx * 4,
            "wind_speed_10m_max": 15 + idx * 2,
        }
        row["weather_label"] = _weather_code_label(code)
        row["risk_note"] = _risk_note(row)
        day_rows.append(row)
    return {
        "key": zone.key,
        "label": zone.label,
        "lat": zone.lat,
        "lon": zone.lon,
        "province_group": zone.province_group,
        "source": "offline_demo",
        "model": "offline_demo",
        "days": day_rows,
        "convective_extremes": {
            "dew_point_max_c": 18.0,
            "cape_max_j_kg": None,
            "cin_min_j_kg": None,
            "lifted_index_min_c": None,
            "pwat_max_mm": None,
            "pressure_min_hpa": None,
            "humidity_max_pct": 82.0,
        },
        "source_url": "",
    }


def _national_days(zone_forecasts: list[dict[str, Any]], *, days: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx in range(days):
        samples: list[dict[str, Any]] = []
        for zone in zone_forecasts:
            zone_days = _list_or_empty(zone.get("days"))
            if idx >= len(zone_days):
                continue
            candidate = zone_days[idx]
            if isinstance(candidate, dict):
                samples.append(candidate)
        if not samples:
            continue
        tmax_values = [_as_float(x.get("temperature_2m_max")) for x in samples]
        tmin_values = [_as_float(x.get("temperature_2m_min")) for x in samples]
        pop_values = [_as_float(x.get("precipitation_probability_max")) for x in samples]
        gust_values = [_as_float(x.get("wind_gusts_10m_max")) for x in samples]
        valid_tmax = [x for x in tmax_values if x is not None]
        valid_tmin = [x for x in tmin_values if x is not None]
        valid_pop = [x for x in pop_values if x is not None]
        valid_gust = [x for x in gust_values if x is not None]
        codes = [int(_as_float(x.get("weather_code")) or 0) for x in samples]
        dominant_code = max(set(codes), key=codes.count) if codes else 0
        date_value = str(samples[0].get("time") or "")[:10]
        row = {
            "date": date_value,
            "weather_code": dominant_code,
            "weather_label": _weather_code_label(dominant_code),
            "temperature_min_c": _round(min(valid_tmin), 1) if valid_tmin else None,
            "temperature_max_c": _round(max(valid_tmax), 1) if valid_tmax else None,
            "precipitation_probability_max_pct": _round(max(valid_pop), 0) if valid_pop else None,
            "wind_gust_max_kmh": _round(max(valid_gust), 0) if valid_gust else None,
        }
        row["risk_note"] = _risk_note(
            {
                "weather_code": dominant_code,
                "temperature_2m_max": row["temperature_max_c"],
                "precipitation_probability_max": row["precipitation_probability_max_pct"],
                "wind_gusts_10m_max": row["wind_gust_max_kmh"],
            }
        )
        rows.append(row)
    return rows


def _summary_text(national_days: list[dict[str, Any]]) -> str:
    if not national_days:
        return "Bulletin 5 jours indisponible pour le moment."
    hot_days = [d for d in national_days if (_as_float(d.get("temperature_max_c")) or 0.0) >= 30]
    storm_days = [
        d
        for d in national_days
        if int(_as_float(d.get("weather_code")) or 0) in {95, 96, 99}
        or (_as_float(d.get("precipitation_probability_max_pct")) or 0.0) >= 60
    ]
    bits = [
        f"Tendance Belgique sur {len(national_days)} jours : "
        f"{national_days[0].get('weather_label', 'temps variable')} au départ"
    ]
    if hot_days:
        bits.append(f"{len(hot_days)} jour(s) avec chaleur marquée possible")
    if storm_days:
        storm_dates = ", ".join(str(d.get("date")) for d in storm_days[:3])
        bits.append(f"risque d’averses orageuses à surveiller autour du {storm_dates}")
    return "; ".join(bits) + "."


def build_bulletin_5days(
    *,
    zones_config: Path | None = None,
    model: str = "best_match",
    timezone: str = DEFAULT_TIMEZONE,
    days: int = 5,
    timeout_s: float = 12.0,
    offline_demo: bool = False,
) -> dict[str, Any]:
    zones = _load_zone_config(zones_config)
    safe_days = max(1, min(int(days), 7))
    zone_forecasts: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for zone in zones:
        try:
            if offline_demo:
                item = _offline_zone_forecast(zone, days=safe_days)
            else:
                item = _zone_live_forecast(
                    zone,
                    model=model,
                    timezone=timezone,
                    days=safe_days,
                    timeout_s=timeout_s,
                )
            zone_forecasts.append(item)
        except Exception as exc:  # noqa: BLE001 - public artifact must degrade gracefully
            errors.append({"zone": zone.key, "label": zone.label, "error": str(exc)})
    national = _national_days(zone_forecasts, days=safe_days)
    return {
        "contract": "meteovoid_belgium_weather_5days_v1",
        "generated_at": _now_iso(),
        "timezone": timezone,
        "country": "Belgium",
        "model": model,
        "source": "Open-Meteo Forecast API" if not offline_demo else "offline_demo",
        "non_official": True,
        "days_requested": safe_days,
        "zones_count": len(zone_forecasts),
        "errors": errors,
        "summary": _summary_text(national),
        "national_days": national,
        "zones": zone_forecasts,
        "disclaimer": (
            "Bulletin automatique non officiel. À comparer avec l’IRM/KMI, MeteoAlarm, "
            "le radar et les observations réelles."
        ),
    }


def render_bulletin_markdown(data: dict[str, Any]) -> str:
    lines = ["# MeteoVoid Belgique · Bulletin météo classique à 5 jours", ""]
    lines.append(f"Généré : `{data.get('generated_at', '')}`")
    lines.append(f"Source : `{data.get('source', '')}` · modèle : `{data.get('model', '')}`")
    lines.append("")
    lines.append(str(data.get("summary") or ""))
    lines.append("")
    lines.append("## Tendance Belgique")
    lines.append("")
    for day in _list_or_empty(data.get("national_days")):
        if not isinstance(day, dict):
            continue
        lines.append(
            "- "
            f"{day.get('date')}: {day.get('weather_label')} · "
            f"{day.get('temperature_min_c')} / {day.get('temperature_max_c')} °C · "
            f"pluie max {day.get('precipitation_probability_max_pct')} % · "
            f"rafales {day.get('wind_gust_max_kmh')} km/h · {day.get('risk_note')}"
        )
    lines.append("")
    lines.append("## Zones")
    lines.append("")
    for zone in _list_or_empty(data.get("zones")):
        if not isinstance(zone, dict):
            continue
        zone_days = _list_or_empty(zone.get("days"))
        first = zone_days[0] if zone_days and isinstance(zone_days[0], dict) else {}
        lines.append(
            "- "
            f"{zone.get('label')}: {first.get('weather_label', '—')} · "
            f"max {first.get('temperature_2m_max', '—')} °C · "
            f"pluie {first.get('precipitation_probability_max', '—')} %"
        )
    lines.append("")
    lines.append(str(data.get("disclaimer") or ""))
    lines.append("")
    return "\n".join(lines)


def write_bulletin_outputs(data: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "weather_5days.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out_dir / "weather_5days.md").write_text(render_bulletin_markdown(data), encoding="utf-8")
