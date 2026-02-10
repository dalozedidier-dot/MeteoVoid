from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from typing import Any, cast

from redis.typing import EncodableT

from .live import LiveConfig, RollingWindow, analyze_window
from .utils import make_redis

StreamFields = dict[str, str]
Message = tuple[str, StreamFields]
XReadResponse = list[tuple[str, list[Message]]]


def _parse_ts(ts: str) -> datetime:
    try:
        return datetime.fromtimestamp(float(ts), tz=UTC)
    except (TypeError, ValueError):
        return datetime(1970, 1, 1, tzinfo=UTC)


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _latest_key(station_id: str, variable: str) -> str:
    return f"meteovoid:latest:{station_id}:{variable}"


def process_observation(
    fields: StreamFields,
    msg_id: str,
    cfg: LiveConfig,
    windows: dict[tuple[str, str], RollingWindow],
) -> dict[str, Any] | None:
    """Pure processing step, unit-test friendly."""
    station_id = str(fields.get("station_id", "")).strip()
    variable = str(fields.get("variable", "")).strip()
    value = _to_float(fields.get("value"))
    ts = _parse_ts(str(fields.get("ts", "0")))

    if not station_id or not variable or value is None:
        return None

    key = (station_id, variable)
    win = windows.setdefault(key, RollingWindow(window_s=cfg.window_s))
    win.push(ts, float(value))

    values = win.values(ts)
    report = dict(analyze_window(values, cfg))
    report.update(
        {
            "station_id": station_id,
            "variable": variable,
            "stream_id": msg_id,
            "ts_ingest": time.time(),
        }
    )
    return report


def run_live_worker(
    redis_url: str,
    in_stream: str,
    out_stream: str,
    cfg: LiveConfig | None = None,
    start_id: str | None = None,
) -> None:
    r = make_redis(redis_url)
    cfg = cfg or LiveConfig()

    windows: dict[tuple[str, str], RollingWindow] = {}

    # IMPORTANT: In CI we often seed BEFORE starting the worker.
    # Default Redis semantics ($) ignores existing messages.
    # We make this explicit via METEOVOID_START_ID (docker-compose sets it to 0-0).
    last_id = start_id or os.getenv("METEOVOID_START_ID", "$")

    while True:
        resp_any = r.xread({in_stream: last_id}, block=1000, count=200)
        resp = cast(XReadResponse, resp_any)

        if not resp:
            continue

        for _stream_name, messages in resp:
            for msg_id, fields in messages:
                last_id = msg_id
                report = process_observation(fields, msg_id, cfg, windows)
                if report is None:
                    continue

                station_id = cast(str, report["station_id"])
                variable = cast(str, report["variable"])

                payload = json.dumps(report, separators=(",", ":"), sort_keys=True)

                r.set(_latest_key(station_id, variable), payload)

                out_fields: dict[EncodableT, EncodableT] = {
                    "station_id": station_id,
                    "variable": variable,
                    "payload": payload,
                }
                r.xadd(out_stream, out_fields)
