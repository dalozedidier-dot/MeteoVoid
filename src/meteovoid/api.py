from __future__ import annotations

import json
import os
import time
from typing import Any, Protocol, cast

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, PlainTextResponse

from .utils import make_redis

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
OUT_STREAM = os.getenv("METEOVOID_OUT_STREAM", "meteovoid:reports")


class RedisLike(Protocol):
    def get(self, key: str) -> str | bytes | bytearray | None: ...
    def keys(self, pattern: str) -> list[Any]: ...


def _make_redis(url: str) -> RedisLike:
    return cast(RedisLike, make_redis(url))


def _decode_key(k: Any) -> str:
    if isinstance(k, bytes | bytearray):
        return k.decode("utf-8", errors="replace")
    return str(k)


def _iter_latest_keys(r: RedisLike, pattern: str) -> list[str]:
    keys_any = r.keys(pattern)
    keys: list[str] = []
    for k in keys_any:
        dk = _decode_key(k)
        if dk.startswith("meteovoid:latest:"):
            keys.append(dk)
    return keys


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

    # Keep backward compatibility: allow callers to pass "*" but we only care about latest keys.
    keys = _iter_latest_keys(r, pattern)

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
    if v is not None:
        try:
            return float(v)
        except (TypeError, ValueError):
            pass

    vv = payload.get("ts")
    if vv is not None:
        try:
            return float(vv)
        except (TypeError, ValueError):
            pass

    return 0.0


def latest_any(redis_url: str = REDIS_URL) -> dict[str, Any]:
    r = _make_redis(redis_url)
    keys = _iter_latest_keys(r, "meteovoid:latest:*")

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


def _prom_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def metrics(redis_url: str = REDIS_URL) -> str:
    """Prometheus text format metrics computed from latest payloads."""
    r = _make_redis(redis_url)
    keys = _iter_latest_keys(r, "meteovoid:latest:*")

    now = time.time()
    lines: list[str] = []
    lines.append("# HELP meteovoid_latest_keys Number of meteovoid:latest:* keys.")
    lines.append("# TYPE meteovoid_latest_keys gauge")
    lines.append(f"meteovoid_latest_keys {len(keys)}")

    # Per-station/variable age + score
    lines.append("# HELP meteovoid_latest_age_seconds Age of latest report since ts_ingest.")
    lines.append("# TYPE meteovoid_latest_age_seconds gauge")
    lines.append("# HELP meteovoid_latest_score Latest composite score.")
    lines.append("# TYPE meteovoid_latest_score gauge")

    for k in keys:
        parts = k.split(":")
        if len(parts) < 4:
            continue
        station_id = parts[2]
        variable = ":".join(parts[3:])
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
        age = max(0.0, float(now - ts)) if ts > 0.0 else float("nan")
        score_any = payload_any.get("score")
        if score_any is None:
            score_f = float("nan")
        else:
            try:
                score_f = float(score_any)
            except (TypeError, ValueError):
                score_f = float("nan")

        labels = f'station_id="{_prom_escape(station_id)}",variable="{_prom_escape(variable)}"'
        lines.append(f"meteovoid_latest_age_seconds{{{labels}}} {age:.6f}")
        lines.append(f"meteovoid_latest_score{{{labels}}} {score_f:.6f}")

    # Stream backlog, if supported by the redis client
    try:
        xlen = getattr(r, "xlen", None)
        if callable(xlen):
            n = int(xlen(OUT_STREAM))
            lines.append("# HELP meteovoid_out_stream_len Length of the out stream.")
            lines.append("# TYPE meteovoid_out_stream_len gauge")
            lines.append(f'meteovoid_out_stream_len{{stream="{_prom_escape(OUT_STREAM)}"}} {n}')
    except Exception:
        pass

    return "\n".join(lines).strip() + "\n"


def history(
    *,
    station_id: str,
    variable: str,
    limit: int = 200,
    redis_url: str = REDIS_URL,
) -> dict[str, Any]:
    """Return recent reports from the output stream, filtered in Python.

    This is meant for troubleshooting and small-scale dashboards.
    """
    r = make_redis(redis_url)
    xrevrange = getattr(r, "xrevrange", None)
    if not callable(xrevrange):
        return {"status": "unsupported"}

    limit = max(1, min(2000, int(limit)))

    # Pull a bit more than we need, since we filter client-side.
    raw_msgs = xrevrange(OUT_STREAM, count=min(limit * 10, 5000))
    out: list[dict[str, Any]] = []
    for msg_id, fields in raw_msgs:
        try:
            sid = fields.get(b"station_id") if isinstance(fields, dict) else None
            var = fields.get(b"variable") if isinstance(fields, dict) else None
            payload = fields.get(b"payload") if isinstance(fields, dict) else None
        except Exception:
            continue

        sid_s = (
            sid.decode("utf-8", errors="replace")
            if isinstance(sid, bytes | bytearray)
            else str(sid or "")
        )
        var_s = (
            var.decode("utf-8", errors="replace")
            if isinstance(var, bytes | bytearray)
            else str(var or "")
        )
        if sid_s != station_id or var_s != variable:
            continue

        try:
            payload_any: Any = json.loads(payload) if payload is not None else {}
        except Exception:
            payload_any = {}
        if not isinstance(payload_any, dict):
            payload_any = {}

        msg_id_s = (
            msg_id.decode("utf-8", errors="replace")
            if isinstance(msg_id, bytes | bytearray)
            else str(msg_id)
        )
        payload_any["stream_id"] = payload_any.get("stream_id", msg_id_s)

        out.append(payload_any)
        if len(out) >= limit:
            break

    out.reverse()
    return {"status": "ok", "station_id": station_id, "variable": variable, "items": out}


app = FastAPI()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics", response_class=PlainTextResponse)
def metrics_http() -> PlainTextResponse:  # pragma: no cover
    return PlainTextResponse(metrics(redis_url=REDIS_URL))


@app.get("/stations")
def stations_http(pattern: str = Query("*")) -> dict[str, dict[str, list[str]]]:  # pragma: no cover
    # Normalize: user-facing /stations should list stations; ignore arbitrary patterns from callers.
    return stations(pattern="meteovoid:latest:*", redis_url=REDIS_URL)


@app.get("/latest")
def latest_http(
    station_id: str | None = Query(None),
    variable: str | None = Query(None),
) -> dict[str, Any]:  # pragma: no cover
    if station_id and variable:
        return latest(station_id=station_id, variable=variable, redis_url=REDIS_URL)

    if station_id and not variable:
        r = _make_redis(REDIS_URL)
        keys = _iter_latest_keys(r, f"meteovoid:latest:{station_id}:*")

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

    return latest_any(redis_url=REDIS_URL)


@app.get("/history")
def history_http(
    station_id: str = Query(...),
    variable: str = Query(...),
    limit: int = Query(200, ge=1, le=2000),
) -> dict[str, Any]:  # pragma: no cover
    return history(station_id=station_id, variable=variable, limit=limit, redis_url=REDIS_URL)


@app.get("/", response_class=HTMLResponse)
def root() -> HTMLResponse:  # pragma: no cover
    return dashboard()


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:  # pragma: no cover
    st = stations(pattern="meteovoid:latest:*", redis_url=REDIS_URL).get("stations", {})
    rows: list[str] = []
    if isinstance(st, dict):
        for sid in sorted(st.keys()):
            vars_ = st.get(sid, [])
            if not isinstance(vars_, list):
                continue
            links: list[str] = []
            for v in vars_:
                vv = str(v)
                links.append(f'<a href="/latest?station_id={sid}&variable={vv}">{vv}</a>')
            rows.append(f"<tr><td>{sid}</td><td>{' , '.join(links)}</td></tr>")

    body = "\n".join(rows) if rows else "<tr><td colspan='2'>No data</td></tr>"

    html = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>MeteoVoid</title>
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; padding: 16px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; }}
    th {{ text-align: left; background: #f5f5f5; }}
    code {{ background: #f0f0f0; padding: 2px 4px; border-radius: 4px; }}
  </style>
</head>
<body>
  <h1>MeteoVoid</h1>
  <p>Endpoints: <code>/health</code> <code>/stations</code> <code>/latest</code> <code>/history</code> <code>/metrics</code></p>
  <table>
    <thead><tr><th>Station</th><th>Variables</th></tr></thead>
    <tbody>{body}</tbody>
  </table>
</body>
</html>
""".strip()

    return HTMLResponse(html)
