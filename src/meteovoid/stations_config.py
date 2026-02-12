from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class StationSpec:
    station_id: str
    name: str
    region: str
    lat: float
    lon: float
    source: str
    variables: list[str]


@dataclass(frozen=True)
class StationsConfig:
    stations: list[StationSpec]
    thresholds: dict[str, dict[str, float]]


def _as_str(v: Any, default: str = "") -> str:
    return str(v) if isinstance(v, str) else default


def _as_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def load_stations_config(path: str | Path) -> StationsConfig:
    p = Path(path)
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Stations config must be a mapping")

    stations_any = data.get("stations", [])
    if not isinstance(stations_any, list):
        raise ValueError("stations must be a list")

    stations: list[StationSpec] = []
    for item in stations_any:
        if not isinstance(item, dict):
            continue
        station_id = _as_str(item.get("id", "")).strip()
        if not station_id:
            continue
        name = _as_str(item.get("name", station_id)).strip() or station_id
        region = _as_str(item.get("region", "default")).strip() or "default"
        lat = _as_float(item.get("lat", 0.0))
        lon = _as_float(item.get("lon", 0.0))
        source = _as_str(item.get("source", "openmeteo")).strip() or "openmeteo"
        vars_any = item.get("variables", [])
        variables = [str(x) for x in vars_any] if isinstance(vars_any, list) else []
        variables = [v.strip() for v in variables if v.strip()]
        if not variables:
            continue
        stations.append(
            StationSpec(
                station_id=station_id,
                name=name,
                region=region,
                lat=lat,
                lon=lon,
                source=source,
                variables=variables,
            )
        )

    thresholds_any = data.get("thresholds", {}) or {}
    thresholds: dict[str, dict[str, float]] = {}
    if isinstance(thresholds_any, dict):
        for var, conf_any in thresholds_any.items():
            if not isinstance(var, str) or not isinstance(conf_any, dict):
                continue
            conf: dict[str, float] = {}
            for k in ("watch", "alert"):
                if k in conf_any:
                    conf[k] = _as_float(conf_any[k])
            if conf:
                thresholds[var] = conf

    return StationsConfig(stations=stations, thresholds=thresholds)


def filter_stations(
    cfg: StationsConfig,
    *,
    region: str | None = None,
    station_ids: list[str] | None = None,
) -> list[StationSpec]:
    out = cfg.stations
    if region:
        r = region.strip().lower()
        out = [s for s in out if s.region.lower() == r]
    if station_ids:
        wanted = {sid.strip() for sid in station_ids if sid.strip()}
        out = [s for s in out if s.station_id in wanted]
    return out
