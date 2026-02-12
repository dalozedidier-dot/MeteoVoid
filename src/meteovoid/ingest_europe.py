from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from typing import Any, cast
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import redis

from .stations_config import StationSpec, load_stations_config


def _http_json(url: str, timeout_s: float = 8.0) -> dict[str, Any]:
    req = Request(url, headers={"Accept": "application/json"})
    with urlopen(req, timeout=timeout_s) as r:  # noqa: S310
        data = r.read().decode("utf-8", errors="replace")
    obj = json.loads(data)
    if not isinstance(obj, dict):
        raise ValueError("HTTP response is not a JSON object")
    return obj


def _build_openmeteo_url(st: StationSpec) -> str:
    # Open-Meteo Forecast API supports current=<vars>
    # wind_speed_unit supports ms, mph, kn, kmh
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
    ts: int | None
    if ts_any is None:
        ts = None
    else:
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
    r: redis.Redis,
    *,
    out_stream: str,
    station_id: str,
    variable: str,
    value: float,
    ts: int | None,
    source: str,
    per_stream: bool,
) -> None:
    fields: dict[str, str | int | float] = {
        "station_id": station_id,
        "variable": variable,
        "value": f"{value}",
        "source": source,
    }
    if ts is not None:
        fields["ts"] = int(ts)

    payload = cast("dict[Any, Any]", fields)
    r.xadd(out_stream, payload, maxlen=50000, approximate=True)

    if per_stream:
        per = f"{out_stream}:{station_id}:{variable}"
        r.xadd(per, payload, maxlen=50000, approximate=True)


def ingest_once(
    *,
    r: redis.Redis,
    station: StationSpec,
    out_stream: str,
    per_stream: bool,
) -> dict[str, Any]:
    if station.source != "openmeteo":
        return {"station_id": station.station_id, "ok": False, "error": "unsupported source"}

    url = _build_openmeteo_url(station)
    obj = _http_json(url)
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

    return {
        "station_id": station.station_id,
        "ok": True,
        "published": published,
        "ts": ts,
        "vars": list(cur.keys()),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True, help="Stations YAML path, ex: config/stations_europe.yaml")
    p.add_argument("--redis-url", default="redis://localhost:6379/0", help="Redis URL")
    p.add_argument("--out-stream", default="meteovoid:observations", help="Redis stream for observations")
    p.add_argument("--poll-seconds", type=int, default=600, help="Polling interval in seconds")
    p.add_argument("--once", action="store_true", help="Fetch once and exit")
    p.add_argument(
        "--per-stream", action="store_true", help="Also write per station/variable stream"
    )
    args = p.parse_args(argv)

    cfg = load_stations_config(args.config)
    stations = cfg.stations

    r = redis.Redis.from_url(args.redis_url, decode_responses=True)

    while True:
        t0 = time.time()
        results: list[dict[str, Any]] = []
        for st in stations:
            try:
                res = ingest_once(
                    r=r, station=st, out_stream=args.out_stream, per_stream=args.per_stream
                )
            except (URLError, TimeoutError, ValueError, OSError) as e:
                res = {"station_id": st.station_id, "ok": False, "error": str(e)}
            results.append(res)

        ok = sum(1 for x in results if x.get("ok"))
        pub = sum(int(x.get("published", 0) or 0) for x in results if x.get("ok"))
        dt = time.time() - t0
        print(
            json.dumps(
                {
                    "ok_stations": ok,
                    "stations": len(results),
                    "published": pub,
                    "seconds": round(dt, 3),
                },
                sort_keys=True,
            )
        )

        if args.once:
            return 0

        sleep_s = max(1, int(args.poll_seconds - dt))
        time.sleep(sleep_s)


if __name__ == "__main__":
    raise SystemExit(main())
