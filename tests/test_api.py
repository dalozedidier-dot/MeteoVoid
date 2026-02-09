from __future__ import annotations

import json

import meteovoid.api as api_mod


class FakeRedis:
    def __init__(self) -> None:
        self._kv: dict[str, str] = {}
        self._keys: list[str] = []

    def get(self, key: str) -> str | None:
        return self._kv.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> None:  # noqa: ARG002
        self._kv[key] = value
        if key not in self._keys:
            self._keys.append(key)

    def keys(self, pattern: str) -> list[str]:
        # Very small glob: only supports '*' in pattern
        if pattern == "*":
            return list(self._keys)
        parts = pattern.split("*")
        out = []
        for k in self._keys:
            ok = True
            pos = 0
            for p in parts:
                if not p:
                    continue
                idx = k.find(p, pos)
                if idx < 0:
                    ok = False
                    break
                pos = idx + len(p)
            if ok:
                out.append(k)
        return out


def test_api_latest_and_stations(monkeypatch) -> None:
    fr = FakeRedis()

    payload = {
        "ts": "2026-02-09T00:00:00Z",
        "station_id": "S1",
        "variable": "wind_gust_ms",
        "window_s": 1800,
        "score": 0.2,
        "state": "transition",
        "data_points": 100,
        "missing_frac": 0.0,
        "p95": 12.3,
        "trend": 0.01,
        "explain": {"variance_jump": 0.1, "slope_change": 0.1, "outlier_frac": 0.0},
    }
    fr.set("meteovoid:latest:S1:wind_gust_ms", json.dumps(payload), ex=60)

    def fake_make(_url: str):  # noqa: ANN001
        return fr

    monkeypatch.setattr(api_mod, "_make_redis", fake_make)

    out = api_mod.latest(station_id="S1", variable="wind_gust_ms", redis_url="redis://x")
    assert out["station_id"] == "S1"

    st = api_mod.stations(pattern="*", redis_url="redis://x")
    assert "S1" in st["stations"]
    assert "wind_gust_ms" in st["stations"]["S1"]
