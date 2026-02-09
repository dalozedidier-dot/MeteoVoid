# File: src/meteovoid/stream.py
from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from redis import Redis

from .live import LiveConfig, analyze_window
from .utils import make_redis


def _as_float(v: Any) -> float:
    try:
        return float(v)
    except Exception:
        return 0.0


def _json_dumpable_fields(d: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for k, v in d.items():
        if isinstance(v, (dict, list)):
            out[k] = json.dumps(v)
        else:
            out[k] = str(v)
    return out


def run_live_worker(
    redis_url: str,
    in_stream: str = "meteovoid:observations",
    out_stream: str = "meteovoid:reports",
    window_points: int = 180,
) -> None:
    """
    Reads observations from a Redis Stream, maintains per-(station,variable) rolling buffers,
    computes an instability report, stores the latest report in Redis, and emits reports
    to an output Redis Stream.
    """
    r: Redis = make_redis(redis_url)

    cfg = LiveConfig(window_points=window_points)

    buffers: Dict[Tuple[str, str], List[float]] = {}

    # IMPORTANT:
    # Start at "$" to consume *new* messages only. This is correct for a live worker,
    # and avoids getting stuck on past stream history in CI runs.
    last_id = "$"

    while True:
        res = r.xread({in_stream: last_id}, block=5000, count=200)
        if not res:
            continue

        for _, entries in res:
            for msg_id, data in entries:
                last_id = msg_id

                station_id = str(data.get("station_id", "UNKNOWN"))
                variable = str(data.get("variable", "value"))
                value = _as_float(data.get("value", 0.0))

                key = (station_id, variable)
                buf = buffers.setdefault(key, [])
                buf.append(value)

                report = analyze_window(buf, cfg=cfg)
                report["station_id"] = station_id
                report["variable"] = variable
                report["event_ts"] = str(data.get("ts", ""))

                latest_key = f"meteovoid:latest:{station_id}:{variable}"
                r.set(latest_key, json.dumps(report), ex=7 * 24 * 3600)

                r.xadd(
                    out_stream,
                    _json_dumpable_fields(report),
                    maxlen=200_000,
                    approximate=True,
                )
