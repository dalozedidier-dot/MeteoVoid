from __future__ import annotations

import json
import time
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

import redis

from .live import LiveScoreConfig, RollingWindow, compute_live_report


def _parse_float(x: Any) -> float:
    try:
        return float(x)
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"Invalid float value: {x!r}") from e


def _parse_ts(ts: Any) -> datetime:
    if ts is None:
        return datetime.now(timezone.utc)
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(float(ts), tz=timezone.utc)
    s = str(ts).strip()
    # Accept Z or offset formats
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        # Fallback: unix seconds in string
        return datetime.fromtimestamp(float(s), tz=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def make_redis(url: str) -> redis.Redis:
    return redis.Redis.from_url(url, decode_responses=True)


def stream_observations(
    r: redis.Redis,
    stream: str,
    obs: Dict[str, Any],
    maxlen: int = 100_000,
) -> str:
    fields = {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in obs.items()}
    return r.xadd(stream, fields, maxlen=maxlen, approximate=True)


def live_worker(
    *,
    redis_url: str = "redis://redis:6379/0",
    in_stream: str = "meteovoid:observations",
    out_stream: str = "meteovoid:reports",
    window_s: int = 1800,
    expected_interval_s: int = 60,
    stable_threshold: float = 0.15,
    unstable_threshold: float = 0.30,
    block_ms: int = 10_000,
) -> None:
    r = make_redis(redis_url)
    cfg = LiveScoreConfig(
        window_s=window_s,
        expected_interval_s=expected_interval_s,
        stable_threshold=stable_threshold,
        unstable_threshold=unstable_threshold,
    )

    windows: Dict[Tuple[str, str], RollingWindow] = {}

    last_id = "$"  # start at latest; set "0-0" to replay from beginning
    while True:
        resp = r.xread({in_stream: last_id}, block=block_ms, count=200)
        if not resp:
            continue

        for _, entries in resp:
            for entry_id, data in entries:
                last_id = entry_id

                station_id = str(data.get("station_id", "unknown"))
                variable = str(data.get("variable", "value"))

                ts = _parse_ts(data.get("ts"))
                epoch = ts.timestamp()
                value = _parse_float(data.get("value"))

                key = (station_id, variable)
                win = windows.get(key)
                if win is None:
                    win = RollingWindow(window_s=cfg.window_s)
                    windows[key] = win
                win.add(epoch, value)

                report = compute_live_report(
                    now_ts=ts,
                    station_id=station_id,
                    variable=variable,
                    window=win,
                    cfg=cfg,
                ).to_dict()

                # Persist a latest snapshot for quick reads
                latest_key = f"meteovoid:latest:{station_id}:{variable}"
                r.set(latest_key, json.dumps(report), ex=7 * 24 * 3600)

                # Stream out reports
                r.xadd(out_stream, {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in report.items()},
                       maxlen=200_000, approximate=True)
