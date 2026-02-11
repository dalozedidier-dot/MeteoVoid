from __future__ import annotations

import json

import meteovoid.api as api_mod


class FakeRedis:
    def __init__(self) -> None:
        self._kv: dict[str, str] = {}
        self._keys: list[str] = []

    def get(self, key: str) -> str | None:
        return self._kv.get(key)

    def set(self, key: str, value: str) -> None:
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


def test_latest_any_picks_most_recent(monkeypatch) -> None:
    fr = FakeRedis()

    fr.set("meteovoid:latest:S1:wind", json.dumps({"station_id": "S1", "variable": "wind", "ts_ingest": 10, "score": 0.1}))
    fr.set("meteovoid:latest:S2:temp", json.dumps({"station_id": "S2", "variable": "temp", "ts_ingest": 20, "score": 0.2}))

    def fake_make(_url: str):  # noqa: ANN001
        return fr

    monkeypatch.setattr(api_mod, "_make_redis", fake_make)

    out = api_mod.latest_any(redis_url="redis://x")
    assert out["station_id"] == "S2"
    assert out["variable"] == "temp"
