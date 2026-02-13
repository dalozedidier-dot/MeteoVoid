from __future__ import annotations

import json
import time

import meteovoid.api as api_mod


class FakeRedis:
    def __init__(self) -> None:
        self._kv: dict[str, str] = {}
        self._keys: list[str] = []
        self._streams: dict[str, list[tuple[str, dict[bytes, bytes]]]] = {}

    def get(self, key: str) -> str | None:
        return self._kv.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> None:  # noqa: ARG002
        self._kv[key] = value
        if key not in self._keys:
            self._keys.append(key)

    def keys(self, pattern: str) -> list[str]:
        # Minimal glob: only supports '*' in pattern.
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

    def xrevrange(self, stream: str, count: int = 1000):  # noqa: ANN001
        msgs = self._streams.get(stream, [])
        # Return newest-first, as redis does.
        return list(reversed(msgs[-count:]))

    def add_stream_msg(self, stream: str, msg_id: str, fields: dict[bytes, bytes]) -> None:
        self._streams.setdefault(stream, []).append((msg_id, fields))


def test_api_latest_any_picks_newest(monkeypatch) -> None:
    fr = FakeRedis()

    older = {
        "station_id": "S1",
        "variable": "temperature_c",
        "score": 0.1,
        "state": "stable",
        "ts_ingest": time.time() - 10.0,
    }
    newer = {
        "station_id": "S2",
        "variable": "wind_gust_ms",
        "score": 0.9,
        "state": "unstable",
        "ts_ingest": time.time() - 1.0,
    }
    fr.set("meteovoid:latest:S1:temperature_c", json.dumps(older), ex=60)
    fr.set("meteovoid:latest:S2:wind_gust_ms", json.dumps(newer), ex=60)

    def fake_make(_url: str):  # noqa: ANN001
        return fr

    monkeypatch.setattr(api_mod, "_make_redis", fake_make)

    out = api_mod.latest_any(redis_url="redis://x")
    assert out["station_id"] == "S2"
    assert out["state"] == "unstable"


def test_api_history_filters_stream(monkeypatch) -> None:
    fr = FakeRedis()

    payload1 = {"station_id": "S1", "variable": "temperature_c", "score": 0.2}
    payload2 = {"station_id": "S1", "variable": "wind_gust_ms", "score": 0.9}
    payload3 = {"station_id": "S1", "variable": "temperature_c", "score": 0.3}

    fr.add_stream_msg(
        api_mod.OUT_STREAM,
        "1700000000000-0",
        {
            b"station_id": b"S1",
            b"variable": b"temperature_c",
            b"payload": json.dumps(payload1).encode("utf-8"),
        },
    )
    fr.add_stream_msg(
        api_mod.OUT_STREAM,
        "1700000000001-0",
        {
            b"station_id": b"S1",
            b"variable": b"wind_gust_ms",
            b"payload": json.dumps(payload2).encode("utf-8"),
        },
    )
    fr.add_stream_msg(
        api_mod.OUT_STREAM,
        "1700000000002-0",
        {
            b"station_id": b"S1",
            b"variable": b"temperature_c",
            b"payload": json.dumps(payload3).encode("utf-8"),
        },
    )

    def fake_make(_url: str):  # noqa: ANN001
        return fr

    monkeypatch.setattr(api_mod, "make_redis", fake_make)

    out = api_mod.history(station_id="S1", variable="temperature_c", limit=10, redis_url="redis://x")
    assert out["status"] == "ok"
    assert out["station_id"] == "S1"
    assert out["variable"] == "temperature_c"
    assert len(out["items"]) == 2
    assert out["items"][0]["score"] == 0.2
    assert out["items"][1]["score"] == 0.3
    assert out["items"][0]["stream_id"] == "1700000000000-0"
