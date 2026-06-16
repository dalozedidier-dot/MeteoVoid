from __future__ import annotations

import argparse
import json
import time
from importlib import import_module
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from . import db as _db
from .log import get_logger
from .stations_config import StationSpec, load_stations_config

try:  # pragma: no cover - exercised indirectly when live extra is installed
    _redis_obj: Any = import_module("redis")
except ModuleNotFoundError:  # pragma: no cover - basic install without live extra

    class _RedisCompat:
        @classmethod
        def from_url(cls, *_args: object, **_kwargs: object) -> object:
            raise RuntimeError(
                "Redis ingestion requires the live extra: "
                "install with `pip install meteo-void[live]`."
            )

    class _RedisModuleCompat:
        Redis = _RedisCompat

    _redis_obj = _RedisModuleCompat()

# Kept as a module-level attribute for backwards compatibility with tests and
# callers that monkeypatch ``ingest_europe.redis.Redis.from_url``.
redis: Any = _redis_obj


_log = get_logger(__name__)

# Redis key recording the last time a station successfully published
_LAST_SEEN_KEY = "meteovoid:ingest_last_seen:{station_id}"
# Redis key for silence alerts
_SILENCE_KEY = "meteovoid:silence:{station_id}"
# Default silence threshold (seconds without data before flagging)
_DEFAULT_SILENCE_S = 300


def _http_json(url: str, timeout_s: float = 8.0) -> dict[str, Any]:
    req = Request(url, headers={"Accept": "application/json"})
    with urlopen(req, timeout=timeout_s) as r:  # noqa: S310
        data = r.read().decode("utf-8", errors="replace")
    obj = json.loads(data)
    if not isinstance(obj, dict):
        raise ValueError("HTTP response is not a JSON object")
    return obj


def _http_json_with_retry(
    url: str,
    *,
    timeout_s: float = 8.0,
    max_attempts: int = 3,
    base_backoff_s: float = 2.0,
) -> dict[str, Any]:
    """Fetch JSON with exponential backoff retry."""
    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(max_attempts):
        try:
            return _http_json(url, timeout_s=timeout_s)
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            last_exc = exc
            if attempt < max_attempts - 1:
                sleep_s = base_backoff_s * (2**attempt)
                _log.warning(
                    "ingest.http_retry",
                    attempt=attempt + 1,
                    max=max_attempts,
                    sleep=sleep_s,
                    exc=str(exc),
                )
                time.sleep(sleep_s)
    raise last_exc


def _build_openmeteo_url(st: StationSpec) -> str:
    params = {
        "latitude": f"{st.lat:.6f}",
        "longitude": f"{st.lon:.6f}",
        "current": ",".join(st.variables),
        "wind_speed_unit": "ms",
        "temperature_unit": "celsius",
        "timeformat": "unixtime",
        "timezone": "GMT",
    }
    return "https://api.open-meteo.com/v1/forecast?" + urlencode(params)


def _extract_current(obj: dict[str, Any]) -> tuple[int | None, dict[str, float]]:
    cur = obj.get("current")
    if not isinstance(cur, dict):
        return None, {}

    ts_any = cur.get("time")
    ts: int | None = None
    if ts_any is not None:
        try:
            ts = int(ts_any)
        except (TypeError, ValueError):
            ts = None

    values: dict[str, float] = {}
    for k, v in cur.items():
        if k == "time":
            continue
        try:
            values[k] = float(v)
        except (TypeError, ValueError):
            continue
    return ts, values


def _publish_observation(
    r: Any,
    *,
    out_stream: str,
    station_id: str,
    variable: str,
    value: float,
    ts: int | None,
    source: str,
    per_stream: bool,
) -> None:
    fields: dict[Any, Any] = {
        "station_id": station_id,
        "variable": variable,
        "value": value,
        "source": source,
    }
    if ts is not None:
        fields["ts"] = ts

    r.xadd(out_stream, fields, maxlen=50000, approximate=True)

    if per_stream:
        per = f"{out_stream}:{station_id}:{variable}"
        r.xadd(per, fields, maxlen=50000, approximate=True)


def _update_last_seen(r: Any, station_id: str, silence_threshold_s: int) -> None:
    """Record current time as last-seen and clear any silence flag."""
    now_s = int(time.time())
    key = _LAST_SEEN_KEY.format(station_id=station_id)
    r.set(key, str(now_s), ex=silence_threshold_s * 4)
    # Clear silence flag if it was set
    r.delete(_SILENCE_KEY.format(station_id=station_id))


def check_station_silence(
    r: Any,
    station_id: str,
    *,
    silence_threshold_s: int = _DEFAULT_SILENCE_S,
) -> bool:
    """Return True if the station has been silent longer than the threshold."""
    key = _LAST_SEEN_KEY.format(station_id=station_id)
    raw = r.get(key)
    if raw is None:
        return False  # Never seen — not yet considered silent (no baseline)
    try:
        last_seen = int(str(raw))
    except (TypeError, ValueError):
        return False
    silence_s = int(time.time()) - last_seen
    if silence_s > silence_threshold_s:
        silence_key = _SILENCE_KEY.format(station_id=station_id)
        r.set(silence_key, str(silence_s), ex=silence_threshold_s * 2)
        return True
    return False


def ingest_once(
    *,
    r: Any,
    station: StationSpec,
    out_stream: str,
    per_stream: bool,
    silence_threshold_s: int = _DEFAULT_SILENCE_S,
) -> dict[str, Any]:
    if station.source != "openmeteo":
        return {"station_id": station.station_id, "ok": False, "error": "unsupported source"}

    url = _build_openmeteo_url(station)
    try:
        obj = _http_json_with_retry(url)
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        error_str = str(exc)
        _log.warning(
            "ingest.station_failed",
            station_id=station.station_id,
            source=station.source,
            exc=error_str,
        )
        _db.log_ingest_failure(
            station_id=station.station_id,
            source=station.source,
            error=error_str,
            url=url,
        )
        return {"station_id": station.station_id, "ok": False, "error": error_str}

    ts, cur = _extract_current(obj)
    published = 0

    for var in station.variables:
        if var not in cur:
            continue
        _publish_observation(
            r,
            out_stream=out_stream,
            station_id=station.station_id,
            variable=var,
            value=cur[var],
            ts=ts,
            source=station.source,
            per_stream=per_stream,
        )
        published += 1

    if published > 0:
        _update_last_seen(r, station.station_id, silence_threshold_s)

    return {
        "station_id": station.station_id,
        "ok": True,
        "published": published,
        "ts": ts,
        "vars": list(cur.keys()),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True, help="Stations YAML path")
    p.add_argument("--redis-url", default="redis://localhost:6379/0")
    p.add_argument("--out-stream", default="meteovoid:observations")
    p.add_argument("--poll-seconds", type=int, default=60)
    p.add_argument("--once", action="store_true")
    p.add_argument("--per-stream", action="store_true")
    p.add_argument(
        "--silence-threshold-s",
        type=int,
        default=_DEFAULT_SILENCE_S,
        help="Seconds without data before a station is flagged as silent.",
    )
    args = p.parse_args(argv)

    cfg = load_stations_config(args.config)
    stations = cfg.stations

    r = redis.Redis.from_url(args.redis_url, decode_responses=True)

    cycle = 0
    while True:
        cycle += 1
        t0 = time.time()
        results: list[dict[str, Any]] = []

        for st in stations:
            try:
                res = ingest_once(
                    r=r,
                    station=st,
                    out_stream=args.out_stream,
                    per_stream=args.per_stream,
                    silence_threshold_s=args.silence_threshold_s,
                )
            except Exception as exc:
                res = {"station_id": st.station_id, "ok": False, "error": str(exc)}
            results.append(res)

        # Silence check after publishing
        try:
            for st in stations:
                if check_station_silence(
                    r, st.station_id, silence_threshold_s=args.silence_threshold_s
                ):
                    _log.warning(
                        "ingest.station_silent",
                        station_id=st.station_id,
                        threshold_s=args.silence_threshold_s,
                    )
        except Exception:
            pass

        ok = sum(1 for x in results if x.get("ok"))
        pub = sum(int(x.get("published", 0) or 0) for x in results if x.get("ok"))
        dt = round(time.time() - t0, 3)

        _log.info(
            "ingest.cycle",
            cycle=cycle,
            ok_stations=ok,
            stations=len(results),
            published=pub,
            seconds=dt,
        )

        if args.once:
            return 0

        sleep_s = max(1, int(args.poll_seconds - dt))
        time.sleep(sleep_s)


if __name__ == "__main__":
    raise SystemExit(main())
