from __future__ import annotations

import json
import os
from typing import Any, Protocol, cast

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

from .config import env_config_path, load_station_config, resolve_variable_overrides
from .utils import make_redis

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")


class RedisLike(Protocol):
    def get(self, key: str) -> str | bytes | bytearray | None: ...

    def keys(self, pattern: str) -> list[Any]: ...


def _make_redis(url: str) -> RedisLike:
    """Module-level hook, monkeypatched in tests."""
    return cast(RedisLike, make_redis(url))


def latest(station_id: str, variable: str, redis_url: str = REDIS_URL) -> dict[str, Any]:
    r = _make_redis(redis_url)
    key = f"meteovoid:latest:{station_id}:{variable}"
    raw = r.get(key)
    if raw is None:
        return {"status": "not_found"}

    try:
        payload: Any = json.loads(raw)
    except json.JSONDecodeError:
        return {"status": "invalid_payload"}

    return payload if isinstance(payload, dict) else {"status": "invalid_payload"}


def stations(pattern: str = "*", redis_url: str = REDIS_URL) -> dict[str, dict[str, list[str]]]:
    r = _make_redis(redis_url)
    keys_any = r.keys(pattern)

    keys = [
        k.decode("utf-8") if isinstance(k, bytes | bytearray) else str(k)
        for k in keys_any
        if str(k).startswith("meteovoid:latest:")
    ]

    out: dict[str, list[str]] = {}
    for k in keys:
        parts = k.split(":")
        if len(parts) < 4:
            continue
        station_id = parts[2]
        variable = ":".join(parts[3:])
        out.setdefault(station_id, [])
        if variable not in out[station_id]:
            out[station_id].append(variable)

    for sid in out:
        out[sid].sort()

    return {"stations": out}


def _ts_ingest(payload: dict[str, Any]) -> float:
    v = payload.get("ts_ingest")
    try:
        return float(v)
    except (TypeError, ValueError):
        # Backward compatibility: try ts as float (epoch)
        vv = payload.get("ts")
        try:
            return float(vv)
        except (TypeError, ValueError):
            return 0.0


def latest_any(redis_url: str = REDIS_URL) -> dict[str, Any]:
    """Return the most recently ingested report across all stations/variables."""
    r = _make_redis(redis_url)
    keys_any = r.keys("meteovoid:latest:*")

    keys = [
        k.decode("utf-8") if isinstance(k, bytes | bytearray) else str(k)
        for k in keys_any
        if str(k).startswith("meteovoid:latest:")
    ]

    best: dict[str, Any] | None = None
    best_ts = -1.0

    for k in keys:
        raw = r.get(k)
        if raw is None:
            continue
        try:
            payload_any: Any = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload_any, dict):
            continue
        ts = _ts_ingest(payload_any)
        if ts > best_ts:
            best_ts = ts
            best = payload_any

    return best if best is not None else {"status": "not_found"}


def latest_station(station_id: str, redis_url: str = REDIS_URL) -> dict[str, Any]:
    """Return all variables for a station + a simple weighted global score."""
    r = _make_redis(redis_url)
    keys_any = r.keys(f"meteovoid:latest:{station_id}:*")
    keys = [
        k.decode("utf-8") if isinstance(k, bytes | bytearray) else str(k)
        for k in keys_any
        if str(k).startswith(f"meteovoid:latest:{station_id}:")
    ]

    variables: dict[str, dict[str, Any]] = {}
    for k in keys:
        parts = k.split(":")
        if len(parts) < 4:
            continue
        var = ":".join(parts[3:])
        payload = latest(station_id=station_id, variable=var, redis_url=redis_url)
        if payload.get("status") in {"not_found", "invalid_payload"}:
            continue
        variables[var] = payload

    cfg = load_station_config(env_config_path())
    weights: dict[str, float] = {}
    for var in variables:
        ov = resolve_variable_overrides(cfg, station_id=station_id, variable=var)
        w = ov.get("weight", 1.0)
        try:
            weights[var] = float(w)
        except (TypeError, ValueError):
            weights[var] = 1.0

    num = 0.0
    den = 0.0
    for var, payload in variables.items():
        try:
            s = float(payload.get("score", 0.0))
        except (TypeError, ValueError):
            continue
        w = weights.get(var, 1.0)
        num += w * s
        den += w

    score_global = float(num / den) if den > 0 else 0.0

    # Global thresholds: prefer station defaults (or global '*'), else fall back to common defaults.
    ov_global = resolve_variable_overrides(cfg, station_id=station_id, variable="*")
    stable_th = float(ov_global.get("stable_threshold", 0.15))
    unstable_th = float(ov_global.get("unstable_threshold", 0.30))

    state_global = "stable"
    if score_global < stable_th:
        state_global = "stable"
    elif score_global > unstable_th:
        state_global = "unstable"
    else:
        state_global = "transition"

    return {
        "station_id": station_id,
        "variables": variables,
        "global": {
            "score": score_global,
            "state": state_global,
            "weights": weights,
            "stable_threshold": stable_th,
            "unstable_threshold": unstable_th,
        },
    }


app = FastAPI()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/stations")
def stations_http(pattern: str = Query("*")) -> dict[str, dict[str, list[str]]]:  # pragma: no cover
    return stations(pattern=pattern, redis_url=REDIS_URL)


@app.get("/latest")
def latest_http(
    station_id: str | None = Query(None),
    variable: str | None = Query(None),
) -> dict[str, Any]:  # pragma: no cover
    if station_id and variable:
        return latest(station_id=station_id, variable=variable, redis_url=REDIS_URL)
    if station_id and not variable:
        return latest_station(station_id=station_id, redis_url=REDIS_URL)
    # no station_id: return newest report across all keys
    return latest_any(redis_url=REDIS_URL)


@app.get("/", response_class=HTMLResponse)
def root() -> HTMLResponse:  # pragma: no cover
    return dashboard()


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:  # pragma: no cover
    st = stations(pattern="*", redis_url=REDIS_URL).get("stations", {})
    rows = []
    if isinstance(st, dict):
        for sid in sorted(st.keys()):
            vars_ = st.get(sid, [])
            if not isinstance(vars_, list):
                continue
            links = []
            for v in vars_:
                vv = str(v)
                links.append(
                    f'<a href="/latest?station_id={sid}&variable={vv}">{vv}</a>'
                )
            rows.append(
                "<tr>"
                f"<td><b>{sid}</b></td>"
                f"<td>{', '.join(links)}</td>"
                f'<td><a href="/latest?station_id={sid}">station global</a></td>'
                "</tr>"
            )

    html = """<!doctype html>
<html>
  <head>
    <meta charset="utf-8"/>
    <title>MeteoVoid Dashboard</title>
    <style>
      body { font-family: ui-sans-serif, system-ui; margin: 24px; }
      table { border-collapse: collapse; width: 100%; }
      td, th { border: 1px solid #ddd; padding: 8px; vertical-align: top; }
      th { background: #f5f5f5; text-align: left; }
      code { background: #f5f5f5; padding: 2px 4px; }
    </style>
  </head>
  <body>
    <h2>MeteoVoid</h2>
    <p>Endpoints: <code>/latest</code>, <code>/stations</code>, <code>/dashboard</code></p>
    <table>
      <thead><tr><th>Station</th><th>Variables</th><th>Global</th></tr></thead>
      <tbody>
        {rows}
      </tbody>
    </table>
  </body>
</html>""".format(rows="\n".join(rows) if rows else "<tr><td colspan='3'>(no data)</td></tr>")

    return HTMLResponse(content=html)
