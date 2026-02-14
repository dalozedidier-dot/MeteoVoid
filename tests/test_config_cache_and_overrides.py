from __future__ import annotations

from pathlib import Path

from meteovoid.config import StationConfig, load_station_config, resolve_variable_overrides


def test_load_station_config_none_and_missing(tmp_path: Path) -> None:
    assert load_station_config(None) is None
    assert load_station_config(str(tmp_path / "missing.json")) is None


def test_load_station_config_cache(tmp_path: Path) -> None:
    p = tmp_path / "cfg.json"
    p.write_text('{"stations":{"*":{"defaults":{"stable_threshold":0.1}}}}', encoding="utf-8")

    c1 = load_station_config(str(p))
    assert c1 is not None
    c2 = load_station_config(str(p))
    assert c2 is not None
    # Cache hit should return same object instance for identical mtime.
    assert c1 is c2


def test_resolve_variable_overrides_handles_invalid_blocks() -> None:
    cfg = StationConfig(raw={"stations": "not-a-dict"})
    assert resolve_variable_overrides(cfg, station_id="X", variable="v") == {}
