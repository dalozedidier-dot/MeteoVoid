"""Structured JSON logging for MeteoVoid.

All modules should use `get_logger(__name__)` to obtain a logger.
Every log record is emitted as a single-line JSON object to stdout,
which is the correct format for docker logs, Loki, Datadog, Cloud Logging, etc.

Usage::

    from meteovoid.log import get_logger
    log = get_logger(__name__)

    log.info("ingest.cycle", ok=8, total=10, published=32, seconds=1.4)
    log.warning("station.silent", station_id="BE_UCCLE", silence_s=700)
    log.error("db.write_failed", exc=str(e), station_id="BE_UCCLE")
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any


def _build_record(level: str, event: str, **fields: Any) -> str:
    rec: dict[str, Any] = {
        "ts": round(time.time(), 3),
        "level": level,
        "event": event,
    }
    rec.update(fields)
    return json.dumps(rec, default=str, separators=(",", ":"))


class _StructuredLogger:
    """Thin wrapper that emits single-line JSON to stdout."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._level = _level_from_env()

    def _emit(self, level: str, level_n: int, event: str, **fields: Any) -> None:
        if level_n < self._level:
            return
        fields["logger"] = self._name
        line = _build_record(level, event, **fields)
        print(line, flush=True)  # noqa: T201

    def debug(self, event: str, **fields: Any) -> None:
        self._emit("DEBUG", logging.DEBUG, event, **fields)

    def info(self, event: str, **fields: Any) -> None:
        self._emit("INFO", logging.INFO, event, **fields)

    def warning(self, event: str, **fields: Any) -> None:
        self._emit("WARNING", logging.WARNING, event, **fields)

    def error(self, event: str, **fields: Any) -> None:
        self._emit("ERROR", logging.ERROR, event, **fields)

    def critical(self, event: str, **fields: Any) -> None:
        self._emit("CRITICAL", logging.CRITICAL, event, **fields)


def _level_from_env() -> int:
    raw = os.getenv("LOG_LEVEL", "INFO").upper().strip()
    return getattr(logging, raw, logging.INFO)


def get_logger(name: str) -> _StructuredLogger:
    return _StructuredLogger(name)
