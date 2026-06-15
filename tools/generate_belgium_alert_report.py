from __future__ import annotations

import argparse
import csv
import json
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
        return TargetWindow(start=today, end=end, label=f"auto_{today.isoformat()}_{end.isoformat()}")
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
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "MeteoVoid/BelgiumAlert"})
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
    weather_codes = [_safe_int(v) for v in weather_codes_any] if isinstance(weather_codes_any, list) else []
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
        signals.append(f"chaleur marquée, Tmax {max_temp:.1f} °C" if max_temp else "chaleur marquée")
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
        prob = _safe_float(precipitation_probability[i]) if i < len(precipitation_probability) else None
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


def _render_markdown(report: dict[str, Any]) -> str:
    aggregate = report["aggregate"]
    stations = report["stations"]
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
    lines.append("## Guide de lecture")
    lines.append("")
    lines.append(
        "Ce rapport est une veille basée sur modèle. Ce n’est pas une alerte officielle. "
        "Pour la sécurité publique, il doit toujours être comparé avec l’IRM/KMI, "
        "MeteoAlarm, le radar et le nowcast foudre."
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
    lines.append("- `high` : préparer un message d’alerte clair si les signaux externes confirment.")
    lines.append("- `alert` : publier seulement après confirmation externe.")
    lines.append("")
    lines.append(
        "Vérifications externes recommandées : avertissements IRM/KMI, MeteoAlarm, "
        "ESTOFEX, radar, foudre."
    )
    lines.append("")
    return "\n".join(lines)


def _write_outputs(report: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "belgium_alert_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out_dir / "belgium_alert_report.md").write_text(_render_markdown(report), encoding="utf-8")

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
        "thunderstorm_code_seen",
        "shower_code_seen",
        "source_ok",
        "error",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in fieldnames})


def _should_send_webhook(severity: str, min_severity: str) -> bool:
    return SEVERITY_RANK.get(severity, 0) >= SEVERITY_RANK.get(min_severity, 2)


def _send_webhook(url: str, report: dict[str, Any], *, timeout_s: float) -> None:
    payload = {
        "source": "MeteoVoid Belgium Alert Watch",
        "generated_at": report["generated_at"],
        "target_window": report["target_window"],
        "aggregate": report["aggregate"],
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
    return {
        "generated_at": generated,
        "source": "openmeteo_forecast" if not offline_demo else "offline_demo",
        "timezone": timezone,
        "target_window": {
            "start": target.start.isoformat(),
            "end": target.end.isoformat(),
            "label": target.label,
        },
        "aggregate": aggregate,
        "stations": stations,
        "limits": [
            "Ce rapport n’est pas un avertissement météorologique officiel.",
            "Utiliser les avertissements officiels IRM/KMI, MeteoAlarm, le radar et la foudre avant toute alerte publique.",
            "Les codes météo Open-Meteo et les prévisions horaires peuvent évoluer rapidement en contexte convectif.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Génère un rapport de veille météo pour la Belgique.")
    parser.add_argument("--stations", default="config/stations_belgium.yaml", help="Stations YAML file")
    parser.add_argument("--out-dir", default="_ci_out/belgium_alert", help="Output directory")
    parser.add_argument(
        "--target-date",
        default="auto",
        help="auto, today, tomorrow, next-friday or YYYY-MM-DD",
    )
    parser.add_argument("--horizon-days", type=int, default=5, help="Used only with --target-date auto")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE, help="Forecast timezone")
    parser.add_argument("--timeout-s", type=float, default=10.0, help="HTTP timeout per station")
    parser.add_argument("--offline-demo", action="store_true", help="Use deterministic demo data")
    parser.add_argument("--webhook-url", default="", help="URL webhook JSON générique optionnelle")
    parser.add_argument("--min-severity", default="medium", choices=sorted(SEVERITY_RANK))
    parser.add_argument("--fail-on-webhook-error", action="store_true")
    args = parser.parse_args(argv)

    target = _parse_target_window(args.target_date, horizon_days=args.horizon_days)
    report = _build_report(
        stations_path=Path(args.stations),
        target=target,
        timezone=args.timezone,
        timeout_s=float(args.timeout_s),
        offline_demo=bool(args.offline_demo),
    )
    out_dir = Path(args.out_dir)
    _write_outputs(report, out_dir)

    webhook_url = args.webhook_url.strip()
    if webhook_url and _should_send_webhook(report["aggregate"]["severity"], args.min_severity):
        try:
            _send_webhook(webhook_url, report, timeout_s=float(args.timeout_s))
        except (OSError, URLError, TimeoutError, ValueError) as exc:
            message = f"Échec du webhook : {exc}"
            if args.fail_on_webhook_error:
                raise SystemExit(message) from exc
            print(message, file=sys.stderr)

    print(out_dir / "belgium_alert_report.json")
    print(out_dir / "belgium_alert_report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
