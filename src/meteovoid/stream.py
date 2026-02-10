from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
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


def process_observation(
    fields: Mapping[str, Any],
    msg_id: str = "",
    cfg: LiveConfig | None = None,
    windows: dict[tuple[str, str], RollingWindow] | None = None,
    ts_ingest: float | None = None,
) -> dict[str, Any] | None:
    """Process a single observation message and return a live report.

    This is a pure-ish unit that can be tested without Redis. It updates the rolling
    window state (if provided) and returns a report dict ready to be JSON-serialized.
    """
    cfg = cfg or LiveConfig()
    windows = windows if windows is not None else {}

    station_id_raw = fields.get("station_id")
    variable_raw = fields.get("variable")
    if station_id_raw is None or variable_raw is None:
        return None

    station_id = str(station_id_raw).strip()
    variable = str(variable_raw).strip()
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
            "ts_ingest": float(ts_ingest if ts_ingest is not None else time.time()),
        }
    )
    return report


def run_live_worker(
    redis_url: str,
    in_stream: str,
    out_stream: str,
    cfg: LiveConfig | None = None,
) -> None:
    r = make_redis(redis_url)
    cfg = cfg or LiveConfig()

    windows: dict[tuple[str, str], RollingWindow] = {}

    # If METEOVOID_START_ID is set, it overrides the default behavior.
    # Otherwise: in CI we read from the beginning (0-0) to consume seeded messages,
    # and locally we tail the stream ($).
    start_id = os.getenv("METEOVOID_START_ID")
    last_id = start_id or ("0-0" if (os.getenv("GITHUB_ACTIONS") or os.getenv("CI")) else "$")

    while True:
        resp_any = r.xread({in_stream: last_id}, block=1000, count=200)
        resp = cast(XReadResponse, resp_any)

        if not resp:
            continue

        for _stream_name, messages in resp:
            for msg_id, fields in messages:
                last_id = msg_id

                report = process_observation(fields, msg_id=msg_id, cfg=cfg, windows=windows)
                if report is None:
                    continue

                station_id = cast(str, report["station_id"])
                variable = cast(str, report["variable"])

                payload = json.dumps(report, separators=(",", ":"), sort_keys=True)

                r.set(f"meteovoid:latest:{station_id}:{variable}", payload)

                out_fields: dict[EncodableT, EncodableT] = {
                    "station_id": station_id,
                    "variable": variable,
                    "payload": payload,
                }
                r.xadd(out_stream, out_fields)
