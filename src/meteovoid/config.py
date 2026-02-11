from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class StationConfig:
    """Runtime configuration loaded from JSON (optionally YAML if PyYAML is installed).

    This config is meant to be lightweight:
    - thresholds by station/variable (stable/unstable + optional watch/alert)
    - gap threshold override (max_gap_s)
    - imputation behavior
    - weights by variable for station-level aggregation

    Schema (JSON):

    {
      "stations": {
        "*": {
          "defaults": {"stable_threshold": 0.15, "unstable_threshold": 0.30},
          "variables": {"*": {"weight": 1.0}}
        },
        "DEMO_BE_0001": {
          "defaults": {"max_gap_s": 300},
          "variables": {
            "wind_gust_ms": {"stable_threshold": 0.10, "unstable_threshold": 0.25, "weight": 0.6},
            "temperature_c": {"stable_threshold": 0.02, "unstable_threshold": 0.08, "weight": 0.4}
          }
        }
      }
    }
    """

    raw: dict[str, Any]


_CACHE: dict[str, tuple[float, StationConfig]] = {}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_station_config(path: str | None) -> StationConfig | None:
    """Load config from disk. Returns None if path is empty or missing.

    Uses a simple (mtime-based) cache to avoid re-reading per message.
    """
    if not path:
        return None

    p = Path(path)
    if not p.exists() or not p.is_file():
        return None

    try:
        mtime = p.stat().st_mtime
    except OSError:
        return None

    cached = _CACHE.get(str(p))
    if cached and cached[0] == mtime:
        return cached[1]

    text = _read_text(p)

    data: dict[str, Any]
    if p.suffix.lower() in {".yaml", ".yml"}:
        # Optional YAML support if PyYAML is installed.
        try:
            import yaml  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "YAML config requested but PyYAML is not installed. Use JSON or add PyYAML."
            ) from e
        obj = yaml.safe_load(text)
        data = obj if isinstance(obj, dict) else {}
    else:
        obj = json.loads(text)
        data = obj if isinstance(obj, dict) else {}

    cfg = StationConfig(raw=data)
    _CACHE[str(p)] = (mtime, cfg)
    return cfg


def resolve_variable_overrides(
    cfg: StationConfig | None, station_id: str, variable: str
) -> dict[str, Any]:
    """Merge overrides in priority order:
    1) stations['*'].defaults
    2) stations['*'].variables['*'] then stations['*'].variables[variable]
    3) stations[station_id].defaults
    4) stations[station_id].variables['*'] then stations[station_id].variables[variable]
    """
    if cfg is None:
        return {}

    stations = cfg.raw.get("stations", {})
    if not isinstance(stations, dict):
        return {}

    def _get_station_block(sid: str) -> dict[str, Any]:
        block = stations.get(sid, {})
        return block if isinstance(block, dict) else {}

    def _get(block: dict[str, Any], key: str) -> dict[str, Any]:
        v = block.get(key, {})
        return v if isinstance(v, dict) else {}

    out: dict[str, Any] = {}

    g = _get_station_block("*")
    out.update(_get(g, "defaults"))

    gv = _get(g, "variables")
    out.update(_get(gv, "*"))
    out.update(_get(gv, variable))

    s = _get_station_block(station_id)
    out.update(_get(s, "defaults"))

    sv = _get(s, "variables")
    out.update(_get(sv, "*"))
    out.update(_get(sv, variable))

    return out


def env_config_path() -> str | None:
    """Return config path from environment."""
    return os.getenv("METEOVOID_CONFIG_PATH")
