from typing import Dict, Any, Iterable
import json
import time
from redis import Redis
from .live import analyze_window
from .utils import make_redis


def stream_observations(
    r: Redis,
    stream: str,
    obs: Dict[str, Any],
) -> str:
    payload = {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in obs.items()}
    return r.xadd(stream, payload)


def run_live_worker(
    redis_url: str,
    in_stream: str = "meteovoid:observations",
    out_stream: str = "meteovoid:reports",
) -> None:
    r = make_redis(redis_url)

    last_id = "0-0"

    buffers: Dict[tuple[str, str], list[float]] = {}

    while True:
        messages = r.xread({in_stream: last_id}, block=5000, count=100)

        for _, entries in messages:
            for msg_id, data in entries:
                last_id = msg_id

                station_id = data.get("station_id")
                variable = data.get("variable")
                value = float(data.get("value", 0.0))

                key = (station_id, variable)
                buffers.setdefault(key, []).append(value)

                report = analyze_window(buffers[key])

                latest_key = f"meteovoid:latest:{station_id}:{variable}"
                r.set(latest_key, json.dumps(report), ex=7 * 24 * 3600)

                payload = {
                    k: json.dumps(v) if isinstance(v, (dict, list)) else str(v)
                    for k, v in report.items()
                }

                r.xadd(out_stream, payload, maxlen=200_000, approximate=True)
