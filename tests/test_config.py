from __future__ import annotations

import json
from pathlib import Path

from meteovoid.config import StationConfig, load_station_config, resolve_variable_overrides


def test_resolve_variable_overrides_merges_layers(tmp_path: Path) -> None:
    cfg_obj = {
        "stations": {
            "*": {
                "defaults": {"stable_threshold": 0.10, "unstable_threshold": 0.30},
                "variables": {"*": {"weight": 1.0}, "wind_gust_ms": {"weight": 0.5}},
            },
            "S1": {
                "defaults": {"max_gap_s": 123.0},
                "variables": {"wind_gust_ms": {"stable_threshold": 0.05}},
            },
        }
    }
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(cfg_obj), encoding="utf-8")

    cfg = load_station_config(str(p))
    assert cfg is not None

    ov = resolve_variable_overrides(cfg, station_id="S1", variable="wind_gust_ms")
    assert ov["stable_threshold"] == 0.05
    assert ov["unstable_threshold"] == 0.30
    assert ov["max_gap_s"] == 123.0
    assert ov["weight"] == 0.5

    ov2 = resolve_variable_overrides(cfg, station_id="S1", variable="temperature_c")
    assert ov2["stable_threshold"] == 0.10
    assert ov2["unstable_threshold"] == 0.30
    assert ov2["max_gap_s"] == 123.0
    assert ov2["weight"] == 1.0


def test_resolve_variable_overrides_handles_missing() -> None:
    cfg = StationConfig(raw={})
    assert resolve_variable_overrides(cfg, station_id="S1", variable="x") == {}
