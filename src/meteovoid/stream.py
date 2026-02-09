from __future__ import annotations

import json
import os
import time
from typing import Any, cast

from redis.typing import EncodableT

from .live import analyze_window
from .utils import make_redis

StreamFields = dict[str, str]
Message = tuple[str, StreamFields]
XReadResponse = list[tuple[str, list[Message]]]


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def run_live_worker(redis_url: str, in_stream: str, out_stream: str) -> None:
    r = make_redis(redis_url)

    buffers: dict[tuple[str, str], list[float]] = {}

    # CI-friendly: consommer depuis le début pour lire les messages seedés
    if os.getenv("GITHUB_ACTIONS") or os.getenv("CI"):
        last_id = "0-0"
    else:
        last_id = "$"

    while True:
        resp_any = r.xread({in_stream: last_id}, block=1000, count=200)
        resp = cast(XReadResponse, resp_any)

        if not resp:
            continue

        for _stream_name, messages in resp:
            for msg_id, fields in messages:
                last_id = msg_id

                station_id = str(fields.get("station_id", "")).strip()
                variable = str(fields.get("variable", "")).strip()
                value = _to_float(fields.get("value"))

                if not station_id or not variable or value is None:
                    continue

                key = (station_id, variable)
                buf = buffers.setdefault(key, [])
                buf.append(value)
                if len(buf) > 180:
                    del buf[:-180]

                report = dict(analyze_window(buf))
                report.update(
                    {
                        "station_id": station_id,
                        "variable": variable,
                        "stream_id": msg_id,
                        "ts_ingest": time.time(),
                    }
                )

                payload = json.dumps(report, separators=(",", ":"), sort_keys=True)

                r.set(f"meteovoid:latest:{station_id}:{variable}", payload)

                out_fields: dict[EncodableT, EncodableT] = {
                    "station_id": station_id,
                    "variable": variable,
                    "payload": payload,
                }
                r.xadd(out_stream, out_fields)
