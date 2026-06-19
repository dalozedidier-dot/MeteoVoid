from __future__ import annotations

import time

import pytest

from meteovoid.stream import run_live_worker


class BatchRedis:
    def __init__(self, total: int = 500) -> None:
        self.pending = [
            (
                f"{i + 1}-0",
                {
                    "station_id": f"S{i % 8}",
                    "variable": "temperature",
                    "value": str(10.0 + (i % 12) * 0.1),
                    "ts": str(i),
                },
            )
            for i in range(total)
        ]
        self.added: list[tuple[str, dict[str, str]]] = []

    def xread(
        self,
        streams: dict[str, str],  # noqa: ARG002
        block: int,  # noqa: ARG002
        count: int,
    ) -> list[tuple[str, list[tuple[str, dict[str, str]]]]]:
        if not self.pending:
            return []
        batch = self.pending[:count]
        self.pending = self.pending[count:]
        return [("meteovoid:observations", batch)]

    def xadd(self, stream: str, fields: dict[str, str]) -> str:
        self.added.append((stream, dict(fields)))
        return f"out-{len(self.added)}"

    def set(self, key: str, value: str) -> None:  # pragma: no cover
        _ = (key, value)


@pytest.mark.performance
def test_live_worker_processes_batch_without_dlq(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = BatchRedis(total=500)
    monkeypatch.setattr("meteovoid.stream.make_redis", lambda _url: fake)
    monkeypatch.setattr("meteovoid.stream.load_station_config", lambda _path: None)
    monkeypatch.setattr("meteovoid.stream._db.ensure_schema", lambda: None)

    started = time.perf_counter()
    run_live_worker(
        "redis://x",
        "meteovoid:observations",
        "meteovoid:reports",
        max_messages=500,
        max_idle_s=0.01,
    )
    elapsed = time.perf_counter() - started

    report_count = sum(1 for stream, _fields in fake.added if stream == "meteovoid:reports")
    dlq_count = sum(1 for stream, _fields in fake.added if stream.endswith(":dlq"))
    assert report_count == 500
    assert dlq_count == 0
    assert elapsed < 10.0
