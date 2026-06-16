from __future__ import annotations

import json
import os
import time
from typing import Any, Protocol, cast

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Path, Query, status
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse

from . import db as _db
from .log import get_logger
from .utils import make_redis

_log = get_logger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
OUT_STREAM = os.getenv("METEOVOID_OUT_STREAM", "meteovoid:reports")
API_TOKEN = os.getenv("METEOVOID_API_TOKEN", "").strip()


class RedisLike(Protocol):
    def get(self, key: str) -> str | bytes | bytearray | None: ...
    def keys(self, pattern: str) -> list[Any]: ...


def _require_write_token(
    authorization: str | None = Header(default=None),
    x_meteovoid_token: str | None = Header(default=None),
) -> None:
    """Protect write endpoints when METEOVOID_API_TOKEN is configured."""
    if not API_TOKEN:
        return
    bearer = ""
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization.split(" ", 1)[1].strip()
    candidate = x_meteovoid_token or bearer
    if candidate != API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing_or_invalid_meteovoid_api_token",
        )


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

    # Severity breakdown counters (live)
    sev_counts: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    for k in keys:
        raw2 = r.get(k)
        if raw2 is None:
            continue
        try:
            p2: Any = json.loads(raw2)
        except json.JSONDecodeError:
            continue
        if not isinstance(p2, dict):
            continue
        sev = str((p2.get("meteo") or {}).get("severity", "low"))
        sev_counts[sev] = sev_counts.get(sev, 0) + 1

    lines.append("# HELP meteovoid_stations_by_severity Number of stations at each severity level.")
    lines.append("# TYPE meteovoid_stations_by_severity gauge")
    for sev, cnt in sev_counts.items():
        lines.append(f'meteovoid_stations_by_severity{{severity="{sev}"}} {cnt}')

    # Station silence flags (Redis)
    silent_count = 0
    for k in keys:
        parts2 = k.split(":")
        if len(parts2) >= 3:
            sid2 = parts2[2]
            if r.get(f"meteovoid:silence:{sid2}") is not None:
                silent_count += 1
    lines.append("# HELP meteovoid_silent_stations Number of stations flagged as silent.")
    lines.append("# TYPE meteovoid_silent_stations gauge")
    lines.append(f"meteovoid_silent_stations {silent_count}")

    # Open alert count from DB
    db_summary = _db.query_summary()
    open_alerts = int(db_summary.get("open_alerts", 0)) if isinstance(db_summary, dict) else 0
    lines.append("# HELP meteovoid_open_alerts Number of currently open alerts.")
    lines.append("# TYPE meteovoid_open_alerts gauge")
    lines.append(f"meteovoid_open_alerts {open_alerts}")

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


# ---------------------------------------------------------------------------
# New API endpoints — Étape 3
# ---------------------------------------------------------------------------


@app.get("/alerts")
def alerts_http(
    limit: int = Query(50, ge=1, le=500),
    severity: str | None = Query(None, description="Filter by severity: low, medium, high"),
    station_id: str | None = Query(None),
) -> dict[str, Any]:  # pragma: no cover
    """Recent alerts from persistent storage, newest first."""
    items = _db.query_alerts(limit=limit, severity=severity, station_id=station_id)
    return {"status": "ok", "count": len(items), "items": items}


@app.get("/stations/{sid}/latest")
def station_latest_http(
    sid: str = Path(..., description="Station ID"),
) -> dict[str, Any]:  # pragma: no cover
    """Latest report for every variable of a station."""
    r = _make_redis(REDIS_URL)
    keys = _iter_latest_keys(r, f"meteovoid:latest:{sid}:*")
    result: dict[str, Any] = {}
    for k in keys:
        parts = k.split(":")
        if len(parts) < 4:
            continue
        variable = ":".join(parts[3:])
        raw = r.get(k)
        if raw is None:
            continue
        try:
            payload: Any = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            result[variable] = payload
    if not result:
        return {"status": "not_found", "station_id": sid}
    return {"status": "ok", "station_id": sid, "variables": result}


@app.get("/stations/{sid}/history")
def station_history_http(
    sid: str = Path(..., description="Station ID"),
    variable: str | None = Query(None),
    limit: int = Query(200, ge=1, le=2000),
    source: str = Query("db", description="db (PostgreSQL) or stream (Redis)"),
) -> dict[str, Any]:  # pragma: no cover
    """Historical reports for a station, newest first."""
    if source == "stream" and variable:
        return history(station_id=sid, variable=variable, limit=limit, redis_url=REDIS_URL)
    items = _db.query_station_history(station_id=sid, variable=variable, limit=limit)
    return {
        "status": "ok",
        "station_id": sid,
        "variable": variable,
        "count": len(items),
        "items": items,
    }


@app.get("/regions")
def regions_http() -> dict[str, Any]:  # pragma: no cover
    """List all regions and their stations derived from live Redis keys."""
    r = _make_redis(REDIS_URL)
    keys = _iter_latest_keys(r, "meteovoid:latest:*")
    regions: dict[str, list[str]] = {}
    for k in keys:
        parts = k.split(":")
        if len(parts) < 4:
            continue
        station_id = parts[2]
        raw = r.get(k)
        if raw is None:
            continue
        try:
            payload: Any = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        # Region comes from score_meta or we derive it from station_id prefix
        region = str(payload.get("region") or station_id.split("_")[0].lower())
        regions.setdefault(region, [])
        if station_id not in regions[region]:
            regions[region].append(station_id)
    for reg in regions:
        regions[reg].sort()
    return {"status": "ok", "regions": regions}


@app.get("/summary")
def summary_http() -> dict[str, Any]:  # pragma: no cover
    """Global summary: counters, alert stats, average score last hour."""
    db_summary = _db.query_summary()
    r = _make_redis(REDIS_URL)
    keys = _iter_latest_keys(r, "meteovoid:latest:*")
    live_high = 0
    live_medium = 0
    live_low = 0
    for k in keys:
        raw = r.get(k)
        if raw is None:
            continue
        try:
            p: Any = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(p, dict):
            continue
        sev = str((p.get("meteo") or {}).get("severity", "low"))
        if sev == "high":
            live_high += 1
        elif sev == "medium":
            live_medium += 1
        else:
            live_low += 1
    return {
        "status": "ok",
        "live": {
            "stations_active": len(keys),
            "severity_high": live_high,
            "severity_medium": live_medium,
            "severity_low": live_low,
        },
        "historical": db_summary,
    }


@app.get("/top_anomalies")
def top_anomalies_http(
    limit: int = Query(10, ge=1, le=100),
    hours: float = Query(1.0, ge=0.1, le=168.0, description="Lookback window in hours"),
) -> dict[str, Any]:  # pragma: no cover
    """Top anomalies by score in the last N hours (from PostgreSQL)."""
    items = _db.query_top_anomalies(limit=limit, hours=hours)
    if not items:
        # Fallback: build from live Redis keys
        r2 = _make_redis(REDIS_URL)
        keys2 = _iter_latest_keys(r2, "meteovoid:latest:*")
        live_items: list[dict[str, Any]] = []
        for k in keys2:
            raw = r2.get(k)
            if raw is None:
                continue
            try:
                p: Any = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(p, dict):
                live_items.append(p)
        live_items.sort(key=lambda x: float(x.get("score") or 0.0), reverse=True)
        items = live_items[:limit]
    return {"status": "ok", "hours": hours, "count": len(items), "items": items}


# ---------------------------------------------------------------------------
# SSE — real-time stream of reports
# ---------------------------------------------------------------------------


@app.get("/events")
def events_sse() -> StreamingResponse:  # pragma: no cover
    """Server-Sent Events: pushes every new report as it's computed by the worker.

    Clients connect once and receive events without polling.
    Each event is a JSON-encoded report followed by two newlines.
    A keepalive comment (': keepalive') is emitted every 2 s when idle.
    """

    def _generate() -> Any:
        r = make_redis(REDIS_URL)
        xread = getattr(r, "xread", None)
        if not callable(xread):
            yield ": unsupported\n\n"
            return
        last_id = "$"
        while True:
            try:
                resp_any = xread({OUT_STREAM: last_id}, block=2000, count=20)
                if not resp_any:
                    yield ": keepalive\n\n"
                    continue
                for _stream, messages in resp_any:
                    for msg_id, fields in messages:
                        last_id = msg_id
                        payload_raw = fields.get(b"payload") or fields.get("payload")
                        if payload_raw is None:
                            continue
                        try:
                            data = json.loads(payload_raw)
                        except (json.JSONDecodeError, TypeError):
                            continue
                        yield f"data: {json.dumps(data, separators=(',', ':'))}\n\n"
            except Exception as exc:
                _log.warning("sse.error", exc=str(exc))
                time.sleep(1)
                yield ": retry\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# Alert lifecycle endpoints
# ---------------------------------------------------------------------------


@app.get("/alerts/{alert_id}")
def alert_detail_http(
    alert_id: int = Path(..., description="Alert ID"),
) -> dict[str, Any]:  # pragma: no cover
    """Fetch one alert with its full lifecycle history."""
    detail = _db.get_alert_detail(alert_id)
    if detail is None:
        return {"status": "not_found", "alert_id": alert_id}
    return {"status": "ok", "alert": detail}


def _alert_action(
    alert_id: int, status: str, comment: str | None
) -> dict[str, Any]:  # pragma: no cover
    ok = _db.update_alert_status(alert_id, status, comment)
    if not ok:
        return {"status": "not_found_or_invalid", "alert_id": alert_id}
    return {"status": "ok", "alert_id": alert_id, "new_status": status}


@app.post("/alerts/{alert_id}/ack")
def alert_ack_http(
    alert_id: int = Path(...),
    comment: str | None = Body(None, embed=True),
    _token: None = Depends(_require_write_token),
) -> dict[str, Any]:  # pragma: no cover
    """Acknowledge an alert (operator has seen it)."""
    return _alert_action(alert_id, "acknowledged", comment)


@app.post("/alerts/{alert_id}/resolve")
def alert_resolve_http(
    alert_id: int = Path(...),
    comment: str | None = Body(None, embed=True),
    _token: None = Depends(_require_write_token),
) -> dict[str, Any]:  # pragma: no cover
    """Mark alert as resolved by operator."""
    return _alert_action(alert_id, "resolved", comment)


@app.post("/alerts/{alert_id}/ignore")
def alert_ignore_http(
    alert_id: int = Path(...),
    comment: str | None = Body(None, embed=True),
    _token: None = Depends(_require_write_token),
) -> dict[str, Any]:  # pragma: no cover
    """Ignore an alert (false positive or not actionable)."""
    return _alert_action(alert_id, "ignored", comment)


# ---------------------------------------------------------------------------
# Station enriched endpoints
# ---------------------------------------------------------------------------


@app.get("/stations/{sid}/status")
def station_status_http(
    sid: str = Path(..., description="Station ID"),
) -> dict[str, Any]:  # pragma: no cover
    """Comprehensive status for a station: live snapshot + open alerts + freshness."""
    r = _make_redis(REDIS_URL)
    keys = _iter_latest_keys(r, f"meteovoid:latest:{sid}:*")

    variables: dict[str, Any] = {}
    worst_severity = "low"
    oldest_ts: float | None = None
    sev_order = {"high": 2, "medium": 1, "low": 0}

    for k in keys:
        parts = k.split(":")
        if len(parts) < 4:
            continue
        variable = ":".join(parts[3:])
        raw = r.get(k)
        if raw is None:
            continue
        try:
            p: Any = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(p, dict):
            continue
        sev = str((p.get("meteo") or {}).get("severity", "low"))
        if sev_order.get(sev, 0) > sev_order.get(worst_severity, 0):
            worst_severity = sev
        ts_val = float(p.get("ts_ingest") or p.get("ts") or 0.0)
        if oldest_ts is None or ts_val < oldest_ts:
            oldest_ts = ts_val
        variables[variable] = {
            "score": p.get("score"),
            "state": p.get("state"),
            "severity": sev,
            "ts": p.get("ts"),
            "ts_ingest": p.get("ts_ingest"),
            "interpretation": (p.get("meteo") or {}).get("interpretation"),
            "flags": (p.get("meteo") or {}).get("flags", []),
        }

    now = time.time()
    last_seen_raw = r.get(f"meteovoid:ingest_last_seen:{sid}")
    silence_raw = r.get(f"meteovoid:silence:{sid}")
    last_seen_s: float | None = None
    try:
        last_seen_s = float(last_seen_raw) if last_seen_raw else None
    except (TypeError, ValueError):
        pass

    open_alerts = _db.query_alerts(station_id=sid, status="open", limit=20)

    return {
        "status": "ok",
        "station_id": sid,
        "severity": worst_severity,
        "variables": variables,
        "freshness": {
            "last_ingest_ts": last_seen_s,
            "age_s": round(now - last_seen_s, 1) if last_seen_s else None,
            "is_silent": silence_raw is not None,
        },
        "open_alerts": open_alerts,
    }


@app.get("/stations/{sid}/timeseries")
def station_timeseries_http(
    sid: str = Path(..., description="Station ID"),
    variable: str = Query(..., description="Variable name"),
    hours: float = Query(6.0, ge=0.1, le=168.0),
    limit: int = Query(500, ge=1, le=5000),
) -> dict[str, Any]:  # pragma: no cover
    """Score timeseries for a station/variable. Suitable for charting."""
    since = time.time() - hours * 3600
    items = _db.query_timeseries(station_id=sid, variable=variable, since=since, limit=limit)
    return {
        "status": "ok",
        "station_id": sid,
        "variable": variable,
        "hours": hours,
        "count": len(items),
        "items": items,
    }


# ---------------------------------------------------------------------------
# Region summary
# ---------------------------------------------------------------------------


@app.get("/regions/{region}/summary")
def region_summary_http(
    region: str = Path(..., description="Region prefix (e.g. BE, FR, DE)"),
) -> dict[str, Any]:  # pragma: no cover
    """Aggregate score/alert stats for all stations in a region (last 1h)."""
    return _db.query_region_summary(region)


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------


@app.get("/thresholds")
def thresholds_http(
    station_id: str | None = Query(None),
    variable: str | None = Query(None),
) -> dict[str, Any]:  # pragma: no cover
    """List configured scoring thresholds."""
    items = _db.get_thresholds(station_id=station_id, variable=variable)
    return {"status": "ok", "count": len(items), "items": items}


@app.post("/thresholds")
def thresholds_upsert_http(
    variable: str = Body(..., embed=True),
    watch_threshold: float | None = Body(None, embed=True),
    alert_threshold: float | None = Body(None, embed=True),
    station_id: str | None = Body(None, embed=True),
    _token: None = Depends(_require_write_token),
) -> dict[str, Any]:  # pragma: no cover
    """Create or update a threshold for a variable (optionally per-station)."""
    ok = _db.upsert_threshold(
        variable=variable,
        watch_threshold=watch_threshold,
        alert_threshold=alert_threshold,
        station_id=station_id,
    )
    return {"status": "ok" if ok else "error", "variable": variable, "station_id": station_id}


# ---------------------------------------------------------------------------
# Sources health
# ---------------------------------------------------------------------------


@app.get("/sources/health")
def sources_health_http() -> dict[str, Any]:  # pragma: no cover
    """Latest ingest success/failure per station.
    Augmented with live Redis silence flags."""
    r = _make_redis(REDIS_URL)
    items = _db.query_ingest_health()
    now = time.time()

    for item in items:
        sid = item.get("station_id", "")
        last_seen_raw = r.get(f"meteovoid:ingest_last_seen:{sid}")
        silence_raw = r.get(f"meteovoid:silence:{sid}")
        last_seen_s: float | None = None
        try:
            last_seen_s = float(last_seen_raw) if last_seen_raw else None
        except (TypeError, ValueError):
            pass
        item["last_ingest_ts"] = last_seen_s
        item["age_s"] = round(now - last_seen_s, 1) if last_seen_s else None
        item["is_silent"] = silence_raw is not None

    return {"status": "ok", "count": len(items), "items": items}


@app.get("/", response_class=HTMLResponse)
def root() -> HTMLResponse:  # pragma: no cover
    return dashboard()


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:  # pragma: no cover
    html = _build_dashboard_html()
    return HTMLResponse(html)


def _build_dashboard_html() -> str:  # pragma: no cover
    return """<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MeteoVoid — Surveillance des flux météo</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
  <style>
    :root {
      --bg:#0f1117; --surface:#1a1d27; --border:#2a2d3a;
      --text:#e2e4f0; --muted:#6b7194;
      --high:#ef4444; --medium:#f59e0b; --low:#22c55e; --accent:#6366f1;
    }
    *{box-sizing:border-box;margin:0;padding:0}
    body{background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,Segoe UI,sans-serif;font-size:14px;display:flex;flex-direction:column;height:100vh}
    header{display:flex;align-items:center;justify-content:space-between;padding:12px 20px;border-bottom:1px solid var(--border);background:var(--surface);flex-shrink:0}
    header h1{font-size:17px;font-weight:700} header h1 span{color:var(--accent)}
    #sse-dot{width:8px;height:8px;border-radius:50%;background:#4b5563;display:inline-block;margin-right:6px;transition:background .3s}
    #sse-dot.live{background:var(--low);box-shadow:0 0 6px var(--low)}
    #status-bar{display:flex;gap:12px;padding:8px 20px;background:var(--surface);border-bottom:1px solid var(--border);flex-wrap:wrap;flex-shrink:0}
    .stat-pill{display:flex;align-items:center;gap:5px;background:var(--bg);border-radius:20px;padding:4px 12px;font-size:12px}
    .dot{width:8px;height:8px;border-radius:50%}
    .dot-high{background:var(--high)} .dot-medium{background:var(--medium)} .dot-low{background:var(--low)} .dot-accent{background:var(--accent)} .dot-warn{background:#f97316}
    #main-layout{display:flex;flex:1;overflow:hidden}
    #left{flex:1;overflow-y:auto;padding:12px 16px}
    #right{width:340px;border-left:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden;flex-shrink:0}
    #controls{display:flex;gap:8px;padding:8px 0;flex-wrap:wrap;align-items:center;flex-shrink:0}
    #controls select,#controls input{background:var(--surface);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:5px 8px;font-size:12px}
    #controls label{color:var(--muted);font-size:11px;margin-right:2px}
    #grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:10px}
    .card{background:var(--surface);border:1px solid var(--border);border-radius:9px;padding:12px;cursor:pointer;transition:border-color .2s}
    .card:hover{border-color:var(--accent)}
    .card.sev-high{border-left:3px solid var(--high)} .card.sev-medium{border-left:3px solid var(--medium)} .card.sev-low{border-left:3px solid var(--low)}
    .card-header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px}
    .card-title{font-weight:600;font-size:13px} .card-var{font-size:11px;color:var(--muted);margin-top:1px}
    .badge{font-size:10px;font-weight:700;padding:2px 7px;border-radius:20px;text-transform:uppercase;letter-spacing:.4px}
    .badge-high{background:rgba(239,68,68,.2);color:var(--high)} .badge-medium{background:rgba(245,158,11,.2);color:var(--medium)} .badge-low{background:rgba(34,197,94,.2);color:var(--low)}
    .score-bar-bg{height:3px;background:var(--border);border-radius:2px;margin:5px 0}
    .score-bar-fill{height:100%;border-radius:2px;transition:width .5s}
    .fill-high{background:var(--high)} .fill-medium{background:var(--medium)} .fill-low{background:var(--low)}
    .interp{font-size:11px;color:var(--muted);margin-top:5px;line-height:1.4;min-height:30px}
    .flags{display:flex;flex-wrap:wrap;gap:3px;margin-top:5px}
    .flag-chip{font-size:10px;background:rgba(99,102,241,.15);color:#a5b4fc;border-radius:4px;padding:1px 5px}
    .chart-wrap{margin-top:8px;height:60px}
    .card-foot{margin-top:7px;font-size:11px;color:var(--muted);display:flex;justify-content:space-between;align-items:center}
    .freshness{font-size:10px;padding:1px 5px;border-radius:3px}
    .fresh{background:rgba(34,197,94,.15);color:var(--low)} .aging{background:rgba(245,158,11,.15);color:var(--medium)} .stale{background:rgba(239,68,68,.15);color:var(--high)}
    /* Right panel */
    #right-tabs{display:flex;border-bottom:1px solid var(--border);flex-shrink:0}
    .rtab{flex:1;padding:9px;text-align:center;font-size:12px;cursor:pointer;color:var(--muted);border-bottom:2px solid transparent;transition:color .2s}
    .rtab.active{color:var(--text);border-bottom-color:var(--accent)}
    .rpanel{display:none;flex:1;overflow-y:auto;padding:10px}
    .rpanel.active{display:block}
    /* Alert items */
    .alert-item{background:var(--bg);border:1px solid var(--border);border-radius:7px;padding:10px;margin-bottom:8px}
    .alert-item.sev-high{border-left:3px solid var(--high)} .alert-item.sev-medium{border-left:3px solid var(--medium)}
    .alert-meta{display:flex;justify-content:space-between;font-size:11px;color:var(--muted);margin-top:4px}
    .alert-interp{font-size:12px;margin-top:4px;line-height:1.4}
    .alert-actions{display:flex;gap:5px;margin-top:7px}
    .btn-sm{font-size:11px;padding:3px 9px;border-radius:5px;border:1px solid var(--border);background:var(--surface);color:var(--text);cursor:pointer;transition:background .2s}
    .btn-sm:hover{background:var(--border)}
    .btn-ack{border-color:#6366f1;color:#a5b4fc} .btn-resolve{border-color:var(--low);color:var(--low)} .btn-ignore{border-color:var(--muted);color:var(--muted)}
    /* Source health */
    .src-item{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border);font-size:12px}
    .src-status{padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600}
    .src-ok{background:rgba(34,197,94,.15);color:var(--low)} .src-fail{background:rgba(239,68,68,.15);color:var(--high)} .src-silent{background:rgba(245,158,11,.15);color:var(--medium)}
    /* Modal */
    #modal-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:100;align-items:center;justify-content:center}
    #modal-overlay.open{display:flex}
    #modal{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:18px;width:min(720px,95vw);max-height:88vh;overflow-y:auto}
    #modal h2{font-size:15px;margin-bottom:10px}
    #modal-chart-wrap{height:180px;margin:12px 0}
    #modal-signals{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:7px}
    .sig-item{background:var(--bg);border-radius:6px;padding:7px}
    .sig-label{font-size:10px;color:var(--muted)} .sig-val{font-size:18px;font-weight:700;margin-top:1px}
    #modal-close{float:right;background:none;border:1px solid var(--border);color:var(--text);border-radius:6px;padding:3px 9px;cursor:pointer;font-size:12px}
    #empty{text-align:center;padding:50px;color:var(--muted)}
    .section-title{font-size:12px;font-weight:600;color:var(--muted);margin-bottom:8px;text-transform:uppercase;letter-spacing:.5px}
  </style>
</head>
<body>
<header>
  <div>
    <h1>Meteo<span>Void</span></h1>
    <div style="font-size:10px;color:var(--muted);margin-top:1px">Surveillance des anomalies et ruptures de cohérence des flux météo</div>
  </div>
  <div style="display:flex;align-items:center;gap:10px">
    <span id="sse-dot"></span><span id="sse-label" style="font-size:11px;color:var(--muted)">Connexion…</span>
    <span id="stat-time" style="font-size:11px;color:var(--muted)"></span>
  </div>
</header>

<div id="status-bar">
  <div class="stat-pill"><div class="dot dot-accent"></div><span id="stat-stations">—</span></div>
  <div class="stat-pill"><div class="dot dot-high"></div><span id="stat-high">—</span></div>
  <div class="stat-pill"><div class="dot dot-medium"></div><span id="stat-medium">—</span></div>
  <div class="stat-pill"><div class="dot dot-low"></div><span id="stat-low">—</span></div>
  <div class="stat-pill"><div class="dot dot-warn"></div><span id="stat-open-alerts">— alertes ouvertes</span></div>
  <div class="stat-pill"><div class="dot dot-medium"></div><span id="stat-silent">— silencieuse(s)</span></div>
</div>

<div id="main-layout">
  <div id="left">
    <div id="controls">
      <div><label>Région</label><select id="filter-region"><option value="">Toutes</option></select></div>
      <div><label>Variable</label><select id="filter-var"><option value="">Toutes</option></select></div>
      <div><label>Sévérité min</label>
        <select id="filter-sev">
          <option value="">Toutes</option>
          <option value="high">Haute</option>
          <option value="medium">Moyenne</option>
          <option value="low">Basse</option>
        </select>
      </div>
      <div><label>Station</label><input id="filter-search" type="text" placeholder="Rechercher…" style="width:130px"></div>
    </div>
    <div id="grid"></div>
    <div id="empty" style="display:none"><h2>Aucune donnée</h2><p>L'ingestion n'a pas encore produit de rapports, ou aucun filtre ne correspond.</p></div>
  </div>

  <div id="right">
    <div id="right-tabs">
      <div class="rtab active" onclick="switchTab('alerts')">Alertes ouvertes</div>
      <div class="rtab" onclick="switchTab('sources')">Sources</div>
      <div class="rtab" onclick="switchTab('top')">Top anomalies</div>
    </div>
    <div id="panel-alerts" class="rpanel active"></div>
    <div id="panel-sources" class="rpanel"></div>
    <div id="panel-top" class="rpanel"></div>
  </div>
</div>

<div id="modal-overlay">
  <div id="modal">
    <button id="modal-close" onclick="closeModal()">Fermer</button>
    <h2 id="modal-title"></h2>
    <div id="modal-interp" style="color:var(--muted);font-size:12px;margin-bottom:8px"></div>
    <div id="modal-chart-wrap"><canvas id="modal-chart"></canvas></div>
    <div style="font-size:11px;color:var(--muted);margin-bottom:6px">Signaux détecteurs</div>
    <div id="modal-signals"></div>
    <div id="modal-alerts" style="margin-top:12px"></div>
  </div>
</div>

<script>
const SEV={high:2,medium:1,low:0};
const REFRESH_SIDEBAR=20000;
let allData={};  // keyed by "sid:var"
let charts={};
let modalChart=null;

function sevClass(s){return s==='high'?'sev-high':s==='medium'?'sev-medium':'sev-low'}
function badgeClass(s){return s==='high'?'badge-high':s==='medium'?'badge-medium':'badge-low'}
function fillClass(s){return s==='high'?'fill-high':s==='medium'?'fill-medium':'fill-low'}
function sevLabel(s){return s==='high'?'Alerte':s==='medium'?'Surveiller':'Stable'}
function scoreColor(s){return s>=.7?'var(--high)':s>=.35?'var(--medium)':'var(--low)'}

function fmtTs(ts){
  if(!ts)return'—';
  return new Date(ts*1000).toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
}
function fmtAge(ts){
  if(!ts)return'';
  const age=Math.round(Date.now()/1000-ts);
  if(age<90)return'à l'instant';
  if(age<3600)return`il y a ${Math.round(age/60)} min`;
  return`il y a ${Math.round(age/3600)} h`;
}
function freshClass(ts){
  if(!ts)return'stale';
  const age=Date.now()/1000-ts;
  if(age<120)return'fresh';
  if(age<600)return'aging';
  return'stale';
}

// ---------------------------------------------------------------------------
// SSE
// ---------------------------------------------------------------------------
let sseConnected=false;
function startSSE(){
  const es=new EventSource('/events');
  es.onopen=()=>{
    sseConnected=true;
    document.getElementById('sse-dot').className='dot dot-accent';
    document.getElementById('sse-dot').id='sse-dot';
    document.getElementById('sse-dot').classList.add('live');
    document.getElementById('sse-label').textContent='Temps réel';
  };
  es.onmessage=(e)=>{
    try{
      const report=JSON.parse(e.data);
      const key=`${report.station_id}:${report.variable}`;
      allData[key]=report;
      updateCard(report);
      updateStatusBar();
      document.getElementById('stat-time').textContent=new Date().toLocaleTimeString('fr-FR');
    }catch(err){}
  };
  es.onerror=()=>{
    sseConnected=false;
    document.getElementById('sse-dot').classList.remove('live');
    document.getElementById('sse-label').textContent='Reconnexion…';
  };
}

// ---------------------------------------------------------------------------
// Initial REST load
// ---------------------------------------------------------------------------
async function initialLoad(){
  try{
    const resp=await fetch('/stations');
    const data=await resp.json();
    const stMap=data.stations||{};
    const promises=[];
    for(const[sid,vars]of Object.entries(stMap)){
      for(const v of vars){
        promises.push(
          fetch(`/latest?station_id=${encodeURIComponent(sid)}&variable=${encodeURIComponent(v)}`)
            .then(r=>r.json()).catch(()=>null)
        );
      }
    }
    const results=await Promise.all(promises);
    for(const r of results){
      if(r&&r.station_id){
        allData[`${r.station_id}:${r.variable}`]=r;
      }
    }
    populateFilters();
    renderAll();
    updateStatusBar();
  }catch(e){console.error('initialLoad',e)}
}

// ---------------------------------------------------------------------------
// Card rendering
// ---------------------------------------------------------------------------
function getFilters(){
  return{
    region:document.getElementById('filter-region').value,
    variable:document.getElementById('filter-var').value,
    sev:document.getElementById('filter-sev').value,
    search:document.getElementById('filter-search').value.toLowerCase().trim()
  };
}

function filteredData(){
  const f=getFilters();
  return Object.values(allData).filter(item=>{
    const sid=(item.station_id||'').toLowerCase();
    const variable=(item.variable||'').toLowerCase();
    const sev=(item.meteo||{}).severity||'low';
    const region=(item.station_id||'').split('_')[0].toLowerCase();
    if(f.region&&region!==f.region)return false;
    if(f.variable&&variable!==f.variable)return false;
    if(f.sev&&sev!==f.sev)return false;
    if(f.search&&!sid.includes(f.search)&&!variable.includes(f.search))return false;
    return true;
  }).sort((a,b)=>{
    const sa=(a.meteo||{}).severity||'low', sb=(b.meteo||{}).severity||'low';
    const d=(SEV[sb]||0)-(SEV[sa]||0);
    return d!==0?d:(b.score||0)-(a.score||0);
  });
}

function populateFilters(){
  const all=Object.values(allData);
  const regions=[...new Set(all.map(d=>(d.station_id||'').split('_')[0].toLowerCase()))].sort();
  const variables=[...new Set(all.map(d=>d.variable||''))].sort();
  const rSel=document.getElementById('filter-region');
  const vSel=document.getElementById('filter-var');
  const cr=rSel.value,cv=vSel.value;
  rSel.innerHTML='<option value="">Toutes</option>'+regions.map(r=>`<option value="${r}">${r.toUpperCase()}</option>`).join('');
  vSel.innerHTML='<option value="">Toutes</option>'+variables.map(v=>`<option value="${v}">${v}</option>`).join('');
  if(cr)rSel.value=cr;
  if(cv)vSel.value=cv;
}

function renderAll(){
  const filtered=filteredData();
  const grid=document.getElementById('grid');
  const empty=document.getElementById('empty');
  for(const id in charts){try{charts[id].destroy()}catch(e){}}
  charts={};
  grid.innerHTML='';
  if(!filtered.length){empty.style.display='block';return}
  empty.style.display='none';
  for(const item of filtered) renderCardInto(item,grid);
}

function renderCardInto(item,container){
  const sid=item.station_id||'';
  const variable=item.variable||'';
  const meteo=item.meteo||{};
  const sev=meteo.severity||'low';
  const score=+(item.score||0);
  const flags=meteo.flags||[];
  const interp=meteo.interpretation||'';
  const cardId=`card-${sid}-${variable}`.replace(/[^a-zA-Z0-9-]/g,'_');
  const chartId=`chart-${cardId}`;
  const tsIngest=+(item.ts_ingest||item.ts||0);
  const fc=freshClass(tsIngest);

  const div=document.createElement('div');
  div.className=`card ${sevClass(sev)}`;
  div.id=cardId;
  div.dataset.sid=sid;
  div.dataset.var=variable;
  div.innerHTML=`
    <div class="card-header">
      <div><div class="card-title">${sid}</div><div class="card-var">${variable}</div></div>
      <span class="badge ${badgeClass(sev)}">${sevLabel(sev)}</span>
    </div>
    <div class="score-bar-bg"><div class="score-bar-fill ${fillClass(sev)}" id="bar-${cardId}" style="width:${Math.round(score*100)}%"></div></div>
    <div style="font-size:11px;color:var(--muted);margin-top:2px">Score&thinsp;<strong style="color:${scoreColor(score)}">${score.toFixed(3)}</strong></div>
    <div class="interp">${interp||'—'}</div>
    <div class="flags">${flags.map(f=>`<span class="flag-chip">${f}</span>`).join('')}</div>
    <div class="chart-wrap"><canvas id="${chartId}"></canvas></div>
    <div class="card-foot">
      <span>${fmtTs(item.ts)}</span>
      <span class="freshness ${fc}">${fmtAge(tsIngest)}</span>
    </div>`;
  div.addEventListener('click',()=>openModal(item));
  container.appendChild(div);
}

function updateCard(item){
  const sid=item.station_id||'';
  const variable=item.variable||'';
  const cardId=`card-${sid}-${variable}`.replace(/[^a-zA-Z0-9-]/g,'_');
  const existing=document.getElementById(cardId);
  const meteo=item.meteo||{};
  const sev=meteo.severity||'low';
  const score=+(item.score||0);
  const tsIngest=+(item.ts_ingest||item.ts||0);

  // If card is visible, update it in place; otherwise re-render grid
  if(existing){
    existing.className=`card ${sevClass(sev)}`;
    const bar=document.getElementById(`bar-${cardId}`);
    if(bar){bar.style.width=`${Math.round(score*100)}%`; bar.className=`score-bar-fill ${fillClass(sev)}`}
    const interp=existing.querySelector('.interp');
    if(interp) interp.textContent=(meteo.interpretation||'—');
    const flags=existing.querySelector('.flags');
    if(flags) flags.innerHTML=(meteo.flags||[]).map(f=>`<span class="flag-chip">${f}</span>`).join('');
    const foot=existing.querySelectorAll('.card-foot span');
    if(foot[0]) foot[0].textContent=fmtTs(item.ts);
    if(foot[1]){foot[1].textContent=fmtAge(tsIngest);foot[1].className=`freshness ${freshClass(tsIngest)}`}
    const badge=existing.querySelector('.badge');
    if(badge){badge.textContent=sevLabel(sev);badge.className=`badge ${badgeClass(sev)}`}
    const scoreEl=existing.querySelector('strong');
    if(scoreEl){scoreEl.textContent=score.toFixed(3);scoreEl.style.color=scoreColor(score)}
  } else {
    // Card not visible — may need to add it (filter might now match)
    populateFilters();
    renderAll();
  }
}

function updateStatusBar(){
  const all=Object.values(allData);
  const high=all.filter(d=>(d.meteo||{}).severity==='high').length;
  const medium=all.filter(d=>(d.meteo||{}).severity==='medium').length;
  const low=all.filter(d=>(d.meteo||{}).severity==='low').length;
  document.getElementById('stat-stations').textContent=`${all.length} station${all.length>1?'s':''}`;
  document.getElementById('stat-high').textContent=`${high} alerte haute`;
  document.getElementById('stat-medium').textContent=`${medium} surveillance`;
  document.getElementById('stat-low').textContent=`${low} stable${low>1?'s':''}`;
}

// ---------------------------------------------------------------------------
// Right panel
// ---------------------------------------------------------------------------
function switchTab(name){
  document.querySelectorAll('.rtab').forEach((t,i)=>{
    const names=['alerts','sources','top'];
    t.classList.toggle('active',names[i]===name);
  });
  document.querySelectorAll('.rpanel').forEach(p=>p.classList.remove('active'));
  document.getElementById(`panel-${name}`).classList.add('active');
  if(name==='alerts')loadOpenAlerts();
  else if(name==='sources')loadSources();
  else loadTopAnomalies();
}

async function loadOpenAlerts(){
  const panel=document.getElementById('panel-alerts');
  try{
    const r=await fetch('/alerts?status=open&limit=30');
    const data=await r.json();
    const items=data.items||[];
    document.getElementById('stat-open-alerts').textContent=`${items.length} alerte${items.length>1?'s':''} ouverte${items.length>1?'s':''}`;
    if(!items.length){panel.innerHTML='<p style="color:var(--muted);font-size:12px;padding:10px">Aucune alerte ouverte.</p>';return}
    panel.innerHTML='<div class="section-title">Alertes ouvertes</div>'+items.map(a=>`
      <div class="alert-item sev-${a.severity}" id="alert-item-${a.id}">
        <div style="display:flex;justify-content:space-between;align-items:flex-start">
          <strong style="font-size:12px">${a.station_id} — ${a.variable}</strong>
          <span class="badge badge-${a.severity}" style="margin-left:6px">${a.severity==='high'?'Alerte':'Surveiller'}</span>
        </div>
        <div class="alert-interp">${a.interpretation||'—'}</div>
        <div class="alert-meta">
          <span>Score ${(a.score||0).toFixed(3)}</span>
          <span>${fmtTs(a.ts)}</span>
        </div>
        <div class="alert-actions">
          <button class="btn-sm btn-ack" onclick="alertAction(${a.id},'ack')">Acquitter</button>
          <button class="btn-sm btn-resolve" onclick="alertAction(${a.id},'resolve')">Résoudre</button>
          <button class="btn-sm btn-ignore" onclick="alertAction(${a.id},'ignore')">Ignorer</button>
        </div>
      </div>`).join('');
  }catch(e){panel.innerHTML=`<p style="color:var(--muted);font-size:12px;padding:10px">Erreur: ${e}</p>`}
}

async function alertAction(id,action){
  const ep=action==='ack'?'ack':action==='resolve'?'resolve':'ignore';
  try{
    const r=await fetch(`/alerts/${id}/${ep}`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    const data=await r.json();
    if(data.status==='ok'){
      const el=document.getElementById(`alert-item-${id}`);
      if(el)el.remove();
    }
  }catch(e){}
}

async function loadSources(){
  const panel=document.getElementById('panel-sources');
  try{
    const r=await fetch('/sources/health');
    const data=await r.json();
    const items=data.items||[];
    const silent=items.filter(i=>i.is_silent).length;
    document.getElementById('stat-silent').textContent=`${silent} silencieuse${silent>1?'s':''}`;
    if(!items.length){panel.innerHTML='<p style="color:var(--muted);font-size:12px;padding:10px">Aucune donnée d'ingestion.</p>';return}
    panel.innerHTML='<div class="section-title">Santé des sources</div>'+items.map(s=>{
      const stClass=s.is_silent?'src-silent':s.status==='failing'?'src-fail':'src-ok';
      const stLabel=s.is_silent?'Silencieuse':s.status==='failing'?'Erreur':'OK';
      const age=s.age_s!=null?`${Math.round(s.age_s)}s`:'—';
      return`<div class="src-item">
        <div><div style="font-size:12px;font-weight:600">${s.station_id}</div><div style="font-size:11px;color:var(--muted)">Dernière: ${age} ago</div></div>
        <span class="src-status ${stClass}">${stLabel}</span>
      </div>`;
    }).join('');
  }catch(e){panel.innerHTML=`<p style="color:var(--muted);font-size:12px;padding:10px">Erreur: ${e}</p>`}
}

async function loadTopAnomalies(){
  const panel=document.getElementById('panel-top');
  try{
    const r=await fetch('/top_anomalies?limit=15&hours=1');
    const data=await r.json();
    const items=data.items||[];
    if(!items.length){panel.innerHTML='<p style="color:var(--muted);font-size:12px;padding:10px">Aucune anomalie dans la dernière heure.</p>';return}
    panel.innerHTML='<div class="section-title">Top anomalies (1h)</div>'+items.map(i=>`
      <div style="display:flex;justify-content:space-between;padding:7px 0;border-bottom:1px solid var(--border);font-size:12px">
        <div>
          <div style="font-weight:600">${i.station_id}</div>
          <div style="color:var(--muted);font-size:11px">${i.variable}</div>
          <div style="color:var(--muted);font-size:11px;margin-top:2px">${(i.interpretation||'').substring(0,60)}</div>
        </div>
        <div style="text-align:right;flex-shrink:0;margin-left:8px">
          <div style="color:${scoreColor(i.score||0)};font-weight:700">${(i.score||0).toFixed(3)}</div>
          <span class="badge badge-${i.severity||'low'}" style="font-size:9px">${i.severity||'low'}</span>
        </div>
      </div>`).join('');
  }catch(e){panel.innerHTML=`<p style="color:var(--muted);font-size:12px;padding:10px">Erreur: ${e}</p>`}
}

// ---------------------------------------------------------------------------
// Modal
// ---------------------------------------------------------------------------
async function openModal(item){
  const sid=item.station_id||'';
  const variable=item.variable||'';
  const meteo=item.meteo||{};
  const signals=item.signals||{};
  document.getElementById('modal-title').textContent=`${sid} — ${variable}`;
  document.getElementById('modal-interp').textContent=meteo.interpretation||'';
  document.getElementById('modal-overlay').classList.add('open');

  // Signals
  const sigDiv=document.getElementById('modal-signals');
  sigDiv.innerHTML='';
  ['gap','volatility','outlier','flatline','spike','drift','spatial','multivar'].forEach(sig=>{
    const val=+(signals[sig]||0);
    const d=document.createElement('div');
    d.className='sig-item';
    d.innerHTML=`<div class="sig-label">${sig}</div><div class="sig-val" style="color:${scoreColor(val)}">${val.toFixed(3)}</div>`;
    sigDiv.appendChild(d);
  });

  // Timeseries chart
  if(modalChart){modalChart.destroy();modalChart=null}
  const canvas=document.getElementById('modal-chart');
  try{
    const tr=await fetch(`/stations/${encodeURIComponent(sid)}/timeseries?variable=${encodeURIComponent(variable)}&hours=6&limit=300`);
    const td=await tr.json();
    const pts=(td.items||[]);
    if(pts.length>1&&canvas){
      modalChart=new Chart(canvas,{
        type:'line',
        data:{
          labels:pts.map(p=>fmtTs(p.ts)),
          datasets:[{
            label:'Score',
            data:pts.map(p=>+(p.score||0).toFixed(4)),
            borderColor:'#6366f1',backgroundColor:'rgba(99,102,241,.1)',
            borderWidth:2,pointRadius:1,fill:true,tension:.3
          }]
        },
        options:{
          animation:false,
          plugins:{legend:{display:false}},
          scales:{
            x:{ticks:{color:'#6b7194',maxTicksLimit:6},grid:{color:'rgba(255,255,255,.05)'}},
            y:{min:0,max:1,ticks:{color:'#6b7194'},grid:{color:'rgba(255,255,255,.05)'}}
          },
          responsive:true,maintainAspectRatio:false
        }
      });
    }
  }catch(e){}

  // Open alerts for this station
  const alertsDiv=document.getElementById('modal-alerts');
  try{
    const ar=await fetch(`/stations/${encodeURIComponent(sid)}/status`);
    const ad=await ar.json();
    const openAlerts=(ad.open_alerts||[]);
    if(openAlerts.length){
      alertsDiv.innerHTML=`<div style="font-size:11px;color:var(--muted);margin-bottom:6px">Alertes ouvertes (${openAlerts.length})</div>`
        +openAlerts.map(a=>`<div class="alert-item sev-${a.severity}" style="margin-bottom:6px">
          <strong style="font-size:11px">${a.variable}</strong> — ${a.interpretation||''}
          <div style="font-size:10px;color:var(--muted);margin-top:3px">Score ${(a.score||0).toFixed(3)} · ${fmtTs(a.ts)}</div>
        </div>`).join('');
    } else {
      alertsDiv.innerHTML='';
    }
  }catch(e){}
}

function closeModal(){
  document.getElementById('modal-overlay').classList.remove('open');
  if(modalChart){modalChart.destroy();modalChart=null}
}
document.getElementById('modal-overlay').addEventListener('click',e=>{
  if(e.target===document.getElementById('modal-overlay'))closeModal();
});

// ---------------------------------------------------------------------------
// Filter listeners
// ---------------------------------------------------------------------------
['filter-region','filter-var','filter-sev'].forEach(id=>{
  document.getElementById(id).addEventListener('change',()=>{renderAll()})
});
document.getElementById('filter-search').addEventListener('input',()=>{renderAll()});

// ---------------------------------------------------------------------------
// Sidebar refresh (alerts, sources, top) — independent of SSE
// ---------------------------------------------------------------------------
setInterval(()=>{
  const active=document.querySelector('.rtab.active');
  if(active){
    const panels=['alerts','sources','top'];
    const idx=[...document.querySelectorAll('.rtab')].indexOf(active);
    if(idx>=0)switchTab(panels[idx]);
  }
},REFRESH_SIDEBAR);

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------
startSSE();
initialLoad();
loadOpenAlerts();
</script>
</body>
</html>"""
