"""Per-country European follow-up, at the same level as the Belgium page.

This module brings each tracked European country (Spain, France, Switzerland,
the Netherlands) up to the Belgium level of follow-up:

* it loads the real national radar network sites (physical radar positions,
  no API key required to display) from ``european_country_radar_sites.yaml``;
* it runs the *same* generic MeteoVoid detection engine
  (:func:`meteovoid.scoring.compute_composite_score`) on a per-country grid of
  observation stations, exactly like the Belgium per-station scoring;
* it stays honest about live data: national radar feeds are only promoted to
  machine evidence when their API key is configured and a frame is readable;
  otherwise the network is displayed and flagged "interface ready".

The offline path is fully deterministic so the public site renders in CI and on
GitHub Pages without any key or network. When ``enable_live`` is set and the
network/keys are available, Open-Meteo observations are used instead.
"""

from __future__ import annotations

import hashlib
import math
import os
import random
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from .scoring import compute_composite_score

DEFAULT_CONFIG = Path("config/european_country_radar_sites.yaml")

SEVERITY_BANDS: tuple[tuple[float, str, str], ...] = (
    (0.25, "calm", "veille faible"),
    (0.50, "watch", "à surveiller"),
    (0.75, "elevated", "signal élevé"),
    (1.01, "danger", "signal critique"),
)


def load_country_config(path: str | Path = DEFAULT_CONFIG) -> dict[str, Any]:
    """Load the per-country radar/station registry; tolerate a missing file."""
    p = Path(path)
    if not p.exists():
        return {"countries": {}}
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {"countries": {}}
    if not isinstance(data.get("countries"), dict):
        data["countries"] = {}
    return data


def _as_list(obj: Any) -> list[Any]:
    return obj if isinstance(obj, list) else []


def _as_dict(obj: Any) -> dict[str, Any]:
    return obj if isinstance(obj, dict) else {}


def _seed(*parts: str) -> int:
    return int(hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:12], 16)


def _severity(score: float) -> dict[str, str]:
    for threshold, key, label in SEVERITY_BANDS:
        if score < threshold:
            return {"key": key, "label": label}
    return {"key": "danger", "label": "signal critique"}


def _synthetic_hourly(station_id: str, run_day: str, hours: int = 48) -> dict[str, list[float]]:
    """Deterministic, plausible diurnal weather series for one station.

    The shape is realistic enough to exercise the detection engine (diurnal
    temperature wave, dew point, a convective afternoon precip bump, a pressure
    fall and wind gusts) while staying fully reproducible from the station id
    and the run day.
    """
    rng = random.Random(_seed(station_id, run_day))
    base_temp = 12.0 + rng.uniform(0.0, 16.0)
    amp = 4.0 + rng.uniform(0.0, 6.0)
    base_dew = base_temp - rng.uniform(3.0, 11.0)
    base_pressure = 1011.0 + rng.uniform(-9.0, 9.0)
    pressure_trend = rng.uniform(-7.0, 2.0)
    gust_base = 3.0 + rng.uniform(0.0, 7.0)
    convective_peak = rng.uniform(0.0, 1.0)
    storm_hour = rng.randint(12, 18)

    temp: list[float] = []
    dew: list[float] = []
    precip: list[float] = []
    pressure: list[float] = []
    gust: list[float] = []
    for h in range(hours):
        hour_of_day = h % 24
        diurnal = math.sin((hour_of_day - 9) / 24.0 * 2.0 * math.pi)
        t = base_temp + amp * diurnal + rng.uniform(-0.8, 0.8)
        d = min(t - 0.5, base_dew + 0.4 * amp * diurnal + rng.uniform(-0.6, 0.6))
        near_storm = math.exp(-((hour_of_day - storm_hour) ** 2) / 6.0)
        pr = max(0.0, 100.0 * convective_peak * near_storm + rng.uniform(-4.0, 8.0))
        p = base_pressure + pressure_trend * (h / hours) + rng.uniform(-0.4, 0.4)
        g = gust_base + 9.0 * convective_peak * near_storm + rng.uniform(-0.6, 1.4)
        temp.append(round(t, 1))
        dew.append(round(d, 1))
        precip.append(round(min(100.0, pr), 0))
        pressure.append(round(p, 1))
        gust.append(round(max(0.0, g), 1))
    return {
        "temperature_c": temp,
        "dew_point_c": dew,
        "precip_prob_pct": precip,
        "pressure_hpa": pressure,
        "wind_gust_ms": gust,
    }


def _humidex_proxy(temp_c: float, dew_c: float) -> float:
    """Lightweight heat/moisture proxy in [0..1] from temperature and dew point."""
    e = 6.11 * math.exp(5417.7530 * (1.0 / 273.16 - 1.0 / (273.16 + max(dew_c, -40.0))))
    humidex = temp_c + 0.5555 * (e - 10.0)
    return max(0.0, min(1.0, (humidex - 21.0) / 24.0))


def _detect_station(
    station: dict[str, Any], *, run_day: str, series: dict[str, list[float]]
) -> dict[str, Any]:
    """Score one station with the generic MeteoVoid engine plus weather proxies."""
    now = datetime.now(UTC)
    gusts = series["wind_gust_ms"]
    samples = [(now, float(v)) for v in gusts]

    composite = compute_composite_score(
        samples=samples,
        values=gusts,
        window_s=3600 * len(gusts),
        missing_time_frac=0.0,
        overrides={"expected_range": {"min": 0.0, "max": 35.0}},
    )

    temp = series["temperature_c"]
    dew = series["dew_point_c"]
    precip = series["precip_prob_pct"]
    pressure = series["pressure_hpa"]

    peak_idx = max(range(len(gusts)), key=lambda i: gusts[i] + precip[i] / 100.0)
    pressure_drop = round(max(0.0, max(pressure) - min(pressure)), 1)
    heat = _humidex_proxy(temp[peak_idx], dew[peak_idx])
    convective = max(0.0, min(1.0, precip[peak_idx] / 100.0 * 0.6 + gusts[peak_idx] / 28.0 * 0.4))

    # Same engine at the core (volatility/spike/drift of gusts), blended with the
    # weather proxies into a public risk score, exactly the Belgium philosophy.
    score = max(0.0, min(1.0, 0.45 * composite.score + 0.35 * convective + 0.20 * heat))
    severity = _severity(score)

    hourly = [
        {"h": i, "s": round(max(0.0, min(1.0, 0.5 * (g / 28.0) + 0.5 * (p / 100.0))), 3)}
        for i, (g, p) in enumerate(zip(gusts, precip, strict=False))
    ]

    signals: list[str] = []
    if convective > 0.5:
        signals.append("potentiel convectif marqué (pluie + rafales)")
    if pressure_drop >= 5.0:
        signals.append(f"chute de pression {pressure_drop} hPa sur la fenêtre")
    if heat > 0.55:
        signals.append("charge thermique/humidité élevée")
    if composite.signals.get("spike", 0.0) > 0.4:
        signals.append("rafales en à-coups (signal interne)")
    if not signals:
        signals.append("pas de signal interne notable")

    return {
        "station_id": station.get("id"),
        "name": station.get("name"),
        "lat": station.get("lat"),
        "lon": station.get("lon"),
        "score": round(score, 3),
        "severity": severity,
        "worst_time": f"+{peak_idx}h",
        "drivers": {
            "temperature_c": temp[peak_idx],
            "dew_point_c": dew[peak_idx],
            "precip_prob_pct": precip[peak_idx],
            "pressure_drop_hpa": pressure_drop,
            "wind_gust_ms": gusts[peak_idx],
        },
        "hourly": hourly,
        "signals": signals[:4],
        "engine_signals": {k: round(v, 3) for k, v in composite.signals.items()},
    }


def _radar_network(cfg: dict[str, Any]) -> dict[str, Any]:
    """Build the real radar-network model (sites + honest key status)."""
    radars = [
        r for r in _as_list(cfg.get("radars")) if isinstance(r, dict) and r.get("lat") is not None
    ]
    key_env = cfg.get("radar_api_key_env")
    key_configured = bool(key_env) and bool(os.environ.get(str(key_env)))
    if not key_env:
        # MeteoSwiss exposes open data without a key.
        status = "open_data_interface_ready"
    elif key_configured:
        status = "national_key_configured"
    else:
        status = "interface_ready_awaiting_national_key"
    return {
        "operator": cfg.get("radar_operator"),
        "network": cfg.get("radar_network"),
        "site_count": len(radars),
        "sites": radars,
        "api_key_env": key_env,
        "api_key_configured": key_configured,
        "status": status,
        "machine_evidence": False,
        "note": (
            "Sites radar nationaux réels affichés sur la carte. Promotion en preuve "
            "machine uniquement si une trame radar nationale est lisible et métriquée."
        ),
    }


def build_country_detection(
    country_key: str,
    cfg: dict[str, Any],
    *,
    run_day: str | None = None,
    enable_live: bool = False,
) -> dict[str, Any]:
    """Build the full per-country follow-up model (detection + radar network)."""
    run_day = run_day or date.today().isoformat()
    stations_cfg = [s for s in _as_list(cfg.get("stations")) if isinstance(s, dict) and s.get("id")]

    data_mode = "offline_demo"
    detections: list[dict[str, Any]] = []
    for station in stations_cfg:
        series = _synthetic_hourly(str(station["id"]), run_day)
        if enable_live:
            live = _try_live_series(station)
            if live is not None:
                series = live
                data_mode = "live_openmeteo"
        detections.append(_detect_station(station, run_day=run_day, series=series))

    detections.sort(key=lambda d: d.get("score") or 0.0, reverse=True)
    scores = [float(d.get("score") or 0.0) for d in detections]
    max_score = max(scores) if scores else 0.0
    mean_score = round(sum(scores) / len(scores), 3) if scores else 0.0
    counts: dict[str, int] = {"calm": 0, "watch": 0, "elevated": 0, "danger": 0}
    for d in detections:
        counts[str(d["severity"]["key"])] = counts.get(str(d["severity"]["key"]), 0) + 1
    level = _severity(max_score)

    bbox = _as_dict(cfg.get("bbox"))
    center = _as_dict(cfg.get("center"))

    return {
        "contract": "meteovoid_country_followup_v1",
        "country": country_key,
        "label": cfg.get("label", country_key.title()),
        "iso2": cfg.get("iso2", ""),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "run_day": run_day,
        "data_mode": data_mode,
        "center": center,
        "bbox": bbox,
        "zoom": cfg.get("zoom", 6),
        "operational_level": level,
        "summary": {
            "station_count": len(detections),
            "max_score": round(max_score, 3),
            "mean_score": mean_score,
            "severity_counts": counts,
            "radar_site_count": _radar_network(cfg)["site_count"],
        },
        "stations": detections,
        "radar_network": _radar_network(cfg),
        "non_official": True,
    }


def _try_live_series(station: dict[str, Any]) -> dict[str, list[float]] | None:
    """Best-effort real observations via Open-Meteo; returns None on any failure."""
    lat = station.get("lat")
    lon = station.get("lon")
    if lat is None or lon is None:
        return None
    try:
        import json
        from urllib.request import Request, urlopen

        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={float(lat)}&longitude={float(lon)}"
            "&hourly=temperature_2m,dew_point_2m,precipitation_probability,"
            "surface_pressure,wind_gusts_10m&forecast_days=2&timezone=UTC"
        )
        req = Request(url, headers={"User-Agent": "MeteoVoid/CountryFollowup"})
        with urlopen(req, timeout=8) as resp:  # noqa: S310 - fixed https host
            payload = json.loads(resp.read().decode("utf-8"))
        hourly = _as_dict(payload.get("hourly"))

        def _floats(key: str) -> list[float]:
            seq = hourly.get(key)
            if not isinstance(seq, list):
                return []
            return [float(v) for v in seq if isinstance(v, int | float)]

        temp = _floats("temperature_2m")
        dew = _floats("dew_point_2m")
        precip = _floats("precipitation_probability")
        pressure = _floats("surface_pressure")
        gust = _floats("wind_gusts_10m")
        n = min(len(temp), len(dew), len(precip), len(pressure), len(gust))
        if n < 12:
            return None
        return {
            "temperature_c": temp[:n],
            "dew_point_c": dew[:n],
            "precip_prob_pct": precip[:n],
            "pressure_hpa": pressure[:n],
            "wind_gust_ms": gust[:n],
        }
    except Exception:
        return None


def build_all_countries(
    *,
    config_path: str | Path = DEFAULT_CONFIG,
    countries: list[str] | None = None,
    run_day: str | None = None,
    enable_live: bool = False,
) -> dict[str, dict[str, Any]]:
    """Build the follow-up model for every configured (or requested) country."""
    cfg = load_country_config(config_path)
    registry = cfg.get("countries", {})
    keys = countries or list(registry.keys())
    out: dict[str, dict[str, Any]] = {}
    for key in keys:
        country_cfg = registry.get(key)
        if isinstance(country_cfg, dict):
            out[key] = build_country_detection(
                key, country_cfg, run_day=run_day, enable_live=enable_live
            )
    return out
