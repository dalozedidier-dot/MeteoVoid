from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

import meteovoid.api as api_mod
import meteovoid.cli as cli_mod
from meteovoid.simulate import push_synthetic_stream, synthetic_series
from meteovoid.stream import _default_start_id, _latest_key, _to_float, run_live_worker
from meteovoid.utils import make_redis

runner = CliRunner()


class FakeRedis:
    def __init__(self) -> None:
        self.set_calls: list[tuple[str, str]] = []
        self.xadd_calls: list[tuple[str, dict]] = []
        self._xread_payload: list = []

    def set(self, key: str, value: str, ex: int | None = None) -> None:  # noqa: ARG002
        self.set_calls.append((key, value))

    def xadd(self, stream: str, fields: dict) -> None:
        self.xadd_calls.append((stream, dict(fields)))

    def xread(self, streams: dict, block: int = 0, count: int = 0):  # noqa: ANN001, ARG002
        # Return the configured payload once then nothing.
        if self._xread_payload:
            payload = self._xread_payload
            self._xread_payload = []
            return payload
        return []


def test_api_not_found_and_invalid_payload(monkeypatch) -> None:
    fr = SimpleNamespace()
    fr.get = lambda _k: None  # noqa: E731
    fr.keys = lambda _p: []  # noqa: E731
    monkeypatch.setattr(api_mod, "_make_redis", lambda _u: fr)

    assert api_mod.latest("X", "Y", redis_url="redis://x")["status"] == "not_found"

    # invalid json
    fr.get = lambda _k: "{not json"  # noqa: E731
    assert api_mod.latest("X", "Y", redis_url="redis://x")["status"] == "invalid_payload"

    # valid json but not dict
    fr.get = lambda _k: json.dumps(["x"])  # noqa: E731
    assert api_mod.latest("X", "Y", redis_url="redis://x")["status"] == "invalid_payload"


def test_cli_simulate_and_live_dispatch(monkeypatch, tmp_path) -> None:
    called = {"simulate": 0, "live": 0, "serve": 0}

    def fake_push(*args, **kwargs):  # noqa: ANN001, ARG001
        called["simulate"] += 1

    def fake_live(*args, **kwargs):  # noqa: ANN001, ARG001
        called["live"] += 1

    monkeypatch.setattr(cli_mod, "push_synthetic_stream", fake_push)
    monkeypatch.setattr(cli_mod, "run_live_worker", fake_live)

    res1 = runner.invoke(cli_mod.app, ["simulate", "--steps", "1", "--sleep", "0"])
    assert res1.exit_code == 0
    assert called["simulate"] == 1

    res2 = runner.invoke(cli_mod.app, ["live"])
    assert res2.exit_code == 0
    assert called["live"] == 1

    # serve: monkeypatch uvicorn.run via sys.modules trick
    class FakeUvicorn:
        @staticmethod
        def run(*args, **kwargs):  # noqa: ANN001, ARG001
            called["serve"] += 1

    monkeypatch.setitem(os.sys.modules, "uvicorn", FakeUvicorn)
    res3 = runner.invoke(cli_mod.app, ["serve", "--port", "9999"])
    assert res3.exit_code == 0
    assert called["serve"] == 1


def test_synthetic_series_edges() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    assert synthetic_series(start, steps=0) == []
    with pytest.raises(ValueError, match="timezone-aware"):
        synthetic_series(datetime(2026, 1, 1), steps=1)


def test_push_synthetic_stream_uses_xadd(monkeypatch) -> None:
    fr = FakeRedis()
    monkeypatch.setattr("meteovoid.simulate.make_redis", lambda _u: fr)
    monkeypatch.setattr("meteovoid.simulate.time.sleep", lambda _s: None)

    push_synthetic_stream(
        redis_url="redis://x",
        stream="s",
        station_id="A",
        variable="B",
        steps=3,
        sleep=0.0,
    )

    assert len(fr.xadd_calls) == 3
    stream, fields = fr.xadd_calls[0]
    assert stream == "s"
    assert fields["station_id"] == "A"
    assert fields["variable"] == "B"
    assert "ts" in fields and "value" in fields


def test_stream_helpers_and_one_message(monkeypatch) -> None:
    assert _to_float("1.5") == 1.5
    assert _to_float("nope") is None
    assert _latest_key("S1", "wind") == "meteovoid:latest:S1:wind"

    # default start id: simulate CI env
    monkeypatch.setenv("CI", "true")
    assert _default_start_id() == "0-0"
    monkeypatch.delenv("CI", raising=False)

    fr = FakeRedis()
    fr._xread_payload = [
        (
            "meteovoid:observations",
            [
                (
                    "1-0",
                    {
                        "ts": "0",
                        "station_id": "S1",
                        "variable": "wind",
                        "value": "1.0",
                    },
                )
            ],
        )
    ]

    monkeypatch.setattr("meteovoid.stream.make_redis", lambda _u: fr)

    run_live_worker(
        redis_url="redis://x",
        in_stream="meteovoid:observations",
        out_stream="meteovoid:reports",
        start_id="0-0",
        max_messages=1,
    )

    assert fr.set_calls
    assert fr.xadd_calls
    k, payload = fr.set_calls[0]
    assert k.startswith("meteovoid:latest:S1:wind")
    d = json.loads(payload)
    assert d["station_id"] == "S1"
    assert d["variable"] == "wind"


def test_make_redis_smoke() -> None:
    r = make_redis("redis://localhost:6379/0")
    assert hasattr(r, "get")
