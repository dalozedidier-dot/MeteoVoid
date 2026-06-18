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
    cape: list[float] = []
    cin: list[float] = []
    lifted: list[float] = []
    shear: list[float] = []
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
        # Proxy convective fields, shaped like the real ones (clearly flagged
        # "proxy" downstream so they are never confused with model output).
        cape.append(
            round(max(0.0, 2600.0 * convective_peak * near_storm + rng.uniform(-80, 120)), 0)
        )
        cin.append(round(-(40.0 * (1.0 - near_storm) * convective_peak + rng.uniform(0, 30)), 0))
        lifted.append(round(3.0 - 9.0 * convective_peak * near_storm + rng.uniform(-0.5, 0.5), 1))
        shear.append(round(6.0 + 16.0 * convective_peak * near_storm + rng.uniform(-1.0, 2.0), 1))
    return {
        "temperature_c": temp,
        "dew_point_c": dew,
        "precip_prob_pct": precip,
        "pressure_hpa": pressure,
        "wind_gust_ms": gust,
        "cape_jkg": cape,
        "cin_jkg": cin,
        "lifted_index": lifted,
        "bulk_shear_ms": shear,
    }


def _humidex_proxy(temp_c: float, dew_c: float) -> float:
    """Lightweight heat/moisture proxy in [0..1] from temperature and dew point."""
    e = 6.11 * math.exp(5417.7530 * (1.0 / 273.16 - 1.0 / (273.16 + max(dew_c, -40.0))))
    humidex = temp_c + 0.5555 * (e - 10.0)
    return max(0.0, min(1.0, (humidex - 21.0) / 24.0))


def _convective_block(
    series: dict[str, list[float]], idx: int, basis: str, precip_v: float, gust_v: float
) -> dict[str, Any]:
    """Native convective indices (CAPE/CIN/LI/shear) when present, else a proxy.

    ``basis`` is "native_openmeteo" when real model fields were fetched, or
    "proxy_demo" / "proxy_live" otherwise. The distinction is published so the
    page never presents a proxy as a real convective model field.
    """
    have = all(k in series and series[k] for k in ("cape_jkg", "cin_jkg", "lifted_index"))
    native = have and basis == "native_openmeteo"
    if have:
        cape_v = series["cape_jkg"][idx]
        cin_v = series["cin_jkg"][idx]
        li_v = series["lifted_index"][idx]
        shear_v = series.get("bulk_shear_ms", [0.0] * (idx + 1))[idx]
        cape_term = min(1.0, max(0.0, cape_v) / 2500.0)
        li_term = min(1.0, max(0.0, -li_v) / 8.0)
        shear_term = min(1.0, max(0.0, shear_v) / 25.0)
        cin_penalty = min(1.0, abs(cin_v) / 120.0)
        score = max(
            0.0,
            min(
                1.0,
                (0.5 * cape_term + 0.3 * li_term + 0.2 * shear_term) * (1.0 - 0.4 * cin_penalty),
            ),
        )
        fields: dict[str, Any] = {
            "cape_jkg": cape_v,
            "cin_jkg": cin_v,
            "lifted_index": li_v,
            "bulk_shear_ms": shear_v,
        }
    else:
        score = max(0.0, min(1.0, precip_v / 100.0 * 0.6 + gust_v / 28.0 * 0.4))
        fields = {"cape_jkg": None, "cin_jkg": None, "lifted_index": None, "bulk_shear_ms": None}
    return {
        "basis": basis if have else "proxy_precip_gust",
        "native_fields_available": native,
        "score": round(score, 3),
        **fields,
    }


def _detect_station(
    station: dict[str, Any],
    *,
    run_day: str,
    series: dict[str, list[float]],
    convective_basis: str = "proxy_demo",
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
    conv = _convective_block(series, peak_idx, convective_basis, precip[peak_idx], gusts[peak_idx])
    convective = float(conv["score"])

    # Same engine at the core (volatility/spike/drift of gusts), blended with the
    # convective layer (native CAPE/CIN/LI/shear when available) and the heat
    # proxy into a public risk score, exactly the Belgium philosophy.
    score = max(0.0, min(1.0, 0.45 * composite.score + 0.35 * convective + 0.20 * heat))
    severity = _severity(score)

    hourly = [
        {"h": i, "s": round(max(0.0, min(1.0, 0.5 * (g / 28.0) + 0.5 * (p / 100.0))), 3)}
        for i, (g, p) in enumerate(zip(gusts, precip, strict=False))
    ]

    signals: list[str] = []
    if convective > 0.5:
        if conv["native_fields_available"]:
            signals.append(
                f"convectif natif : CAPE {conv['cape_jkg']} J/kg, LI {conv['lifted_index']}, "
                f"cisaillement {conv['bulk_shear_ms']} m/s"
            )
        else:
            signals.append("potentiel convectif (proxy pluie + rafales)")
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
        "convective": conv,
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
    master_sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the full per-country follow-up model (detection + radar network)."""
    run_day = run_day or date.today().isoformat()
    stations_cfg = [s for s in _as_list(cfg.get("stations")) if isinstance(s, dict) and s.get("id")]

    data_mode = "offline_demo"
    native_convective = False
    detections: list[dict[str, Any]] = []
    for station in stations_cfg:
        series = _synthetic_hourly(str(station["id"]), run_day)
        basis = "proxy_demo"
        if enable_live:
            live = _try_live_series(station)
            if live is not None:
                series = live
                data_mode = "live_openmeteo"
                if live.get("cape_jkg"):
                    basis = "native_openmeteo"
                    native_convective = True
                else:
                    basis = "proxy_live"
        detections.append(
            _detect_station(station, run_day=run_day, series=series, convective_basis=basis)
        )

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
            "convective_basis": "native_openmeteo" if native_convective else "proxy",
            "native_convective_fields": native_convective,
        },
        "stations": detections,
        "weather": _country_weather(detections),
        "radar_network": _radar_network(cfg),
        "machine_radar": _machine_radar_status(country_key, cfg),
        "validation": _validation_status(country_key),
        "convective": {
            "basis": "native_openmeteo" if native_convective else "proxy",
            "native_fields_available": native_convective,
            "fields": ["CAPE", "CIN", "lifted_index", "bulk_shear"],
            "note": (
                "Champs convectifs natifs (CAPE/CIN/LI/cisaillement) lus via Open-Meteo "
                "en mode live ; sinon proxy déterministe explicitement étiqueté."
            ),
        },
        "data_sources": master_sources or [],
        "non_official": True,
    }



def _humidex_value(temp_c: float, dew_c: float) -> float:
    """Humidex-style apparent temperature in °C."""
    try:
        e = 6.11 * math.exp(5417.7530 * (1.0 / 273.16 - 1.0 / (273.16 + max(dew_c, -40.0))))
        return round(max(temp_c, temp_c + 0.5555 * (e - 10.0)), 1)
    except (OverflowError, ValueError):
        return round(temp_c, 1)


def _country_weather(stations: list[dict[str, Any]]) -> dict[str, Any]:
    """Public weather bulletin for each country page.

    It uses the same station detections as the map so every country page has the
    same readable result: radar map + station temperatures + humidity signal.
    """
    rows: list[dict[str, Any]] = []
    for s in stations:
        drivers = _as_dict(s.get("drivers"))
        t = drivers.get("temperature_c")
        dew = drivers.get("dew_point_c")
        if not isinstance(t, int | float) or not isinstance(dew, int | float):
            continue
        rows.append(
            {
                "station_id": s.get("station_id"),
                "name": s.get("name"),
                "lat": s.get("lat"),
                "lon": s.get("lon"),
                "temperature_c": round(float(t), 1),
                "dew_point_c": round(float(dew), 1),
                "humidex": _humidex_value(float(t), float(dew)),
                "precip_prob_pct": drivers.get("precip_prob_pct"),
                "wind_gust_ms": drivers.get("wind_gust_ms"),
                "score": s.get("score"),
                "severity": s.get("severity"),
            }
        )
    rows.sort(key=lambda r: float(r.get("temperature_c") or -99.0), reverse=True)
    top = rows[0] if rows else {}
    return {
        "station_count": len(rows),
        "max_temperature_c": top.get("temperature_c"),
        "max_humidex": top.get("humidex"),
        "top_station": top.get("name"),
        "stations": rows,
        "note": "Températures issues du même maillage Open‑Meteo / MeteoVoid que la détection pays.",
    }

def _machine_radar_status(country_key: str, cfg: dict[str, Any]) -> dict[str, Any]:
    """Honest machine-radar state: 0 metrics until a real radar file is read."""
    key_env = cfg.get("radar_api_key_env")
    radar_file = os.environ.get(f"METEOVOID_RADAR_FILE_{country_key.upper()}")
    available = bool(radar_file) and Path(str(radar_file)).exists()
    metrics: dict[str, Any] | None = None
    if available and radar_file:
        try:
            from .belgium.opera_ord import analyse_radar_file

            metrics = analyse_radar_file(Path(str(radar_file)))
        except Exception:
            metrics = None
            available = False
    blockers = []
    if not radar_file:
        blockers.append("aucun fichier radar national fourni pour ce run")
    if key_env and not os.environ.get(str(key_env)):
        blockers.append(f"clé {key_env} non configurée")
    return {
        "available": available,
        "metrics": metrics,
        "blockers": blockers,
        "how_to_enable": [
            "configurer la clé nationale ou activer OPERA ORD / MeteoGate",
            f"fournir un fichier radar via METEOVOID_RADAR_FILE_{country_key.upper()} (ODIM HDF5 / GeoTIFF)",
            "MeteoVoid calcule alors des métriques machine et promeut la source en preuve",
        ],
        "note": (
            "Une carte affichée (RainViewer, page nationale) n'est pas une preuve machine. "
            "La preuve exige un fichier radar lisible transformé en métriques."
        ),
    }


def _validation_status(country_key: str) -> dict[str, Any]:
    """Honest historical-validation state: metrics need verified storm events."""
    events_path = Path(f"config/{country_key}_verified_storm_events.csv")
    count = 0
    if events_path.exists():
        try:
            lines = [
                ln
                for ln in events_path.read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.lstrip().startswith("#")
            ]
            count = max(0, len(lines) - 1)  # minus header
        except Exception:
            count = 0
    status = "available" if count > 0 else "needs_verified_events"
    return {
        "status": status,
        "verified_event_count": count,
        "metrics": {
            "brier_score": None,
            "pod": None,
            "far": None,
            "csi": None,
        },
        "note": (
            "Brier, POD, FAR et CSI ne sont calculables qu'avec des événements "
            f"vérifiés. Fournir config/{country_key}_verified_storm_events.csv pour "
            "mesurer vrais/faux positifs et délai de détection."
        ),
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

        # Open-Meteo exposes native convective fields (cape, convective_inhibition,
        # lifted_index) and pressure-level winds used to derive bulk shear.
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={float(lat)}&longitude={float(lon)}"
            "&hourly=temperature_2m,dew_point_2m,precipitation_probability,"
            "surface_pressure,wind_gusts_10m,cape,convective_inhibition,lifted_index,"
            "wind_speed_1000hPa,wind_speed_500hPa&forecast_days=2&timezone=UTC"
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
        out: dict[str, list[float]] = {
            "temperature_c": temp[:n],
            "dew_point_c": dew[:n],
            "precip_prob_pct": precip[:n],
            "pressure_hpa": pressure[:n],
            "wind_gust_ms": gust[:n],
        }
        cape = _floats("cape")
        cin = _floats("convective_inhibition")
        lifted = _floats("lifted_index")
        w1000 = _floats("wind_speed_1000hPa")
        w500 = _floats("wind_speed_500hPa")
        if len(cape) >= n and len(lifted) >= n:
            out["cape_jkg"] = cape[:n]
            out["cin_jkg"] = cin[:n] if len(cin) >= n else [0.0] * n
            out["lifted_index"] = lifted[:n]
            if len(w1000) >= n and len(w500) >= n:
                out["bulk_shear_ms"] = [abs(w500[i] - w1000[i]) for i in range(n)]
        return out
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

    # Attach the sanitised master radar source registry to each country so the
    # per-country page can show the honest source detail (env, quota, priority).
    country_source_map: dict[str, list[dict[str, Any]]] = {}
    try:
        from .radar_sources import build_source_registry, sources_for_country

        source_registry = build_source_registry()
        for key in keys:
            country_source_map[key] = sources_for_country(source_registry, key)
    except Exception:
        country_source_map = {}

    out: dict[str, dict[str, Any]] = {}
    for key in keys:
        country_cfg = registry.get(key)
        if isinstance(country_cfg, dict):
            out[key] = build_country_detection(
                key,
                country_cfg,
                run_day=run_day,
                enable_live=enable_live,
                master_sources=country_source_map.get(key, []),
            )
    return out
