from __future__ import annotations

import json
import os
import time
from typing import Any, Protocol, cast

from fastapi import FastAPI, Path, Query
from fastapi.responses import HTMLResponse, PlainTextResponse

from . import db as _db
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
    return {"status": "ok", "station_id": sid, "variable": variable, "count": len(items), "items": items}


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
      --bg: #0f1117;
      --surface: #1a1d27;
      --border: #2a2d3a;
      --text: #e2e4f0;
      --muted: #6b7194;
      --high: #ef4444;
      --medium: #f59e0b;
      --low: #22c55e;
      --accent: #6366f1;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: system-ui, -apple-system, Segoe UI, sans-serif;
      font-size: 14px;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 14px 20px;
      border-bottom: 1px solid var(--border);
      background: var(--surface);
    }
    header h1 { font-size: 18px; font-weight: 700; letter-spacing: .5px; }
    header h1 span { color: var(--accent); }
    #refresh-info { font-size: 12px; color: var(--muted); }
    #status-bar {
      display: flex; gap: 16px; padding: 10px 20px;
      background: var(--surface); border-bottom: 1px solid var(--border);
      flex-wrap: wrap;
    }
    .stat-pill {
      display: flex; align-items: center; gap: 6px;
      background: var(--bg); border-radius: 20px;
      padding: 4px 12px; font-size: 12px;
    }
    .stat-pill .dot {
      width: 8px; height: 8px; border-radius: 50%;
    }
    .dot-high { background: var(--high); }
    .dot-medium { background: var(--medium); }
    .dot-low { background: var(--low); }
    .dot-accent { background: var(--accent); }
    #controls {
      display: flex; gap: 10px; padding: 12px 20px;
      flex-wrap: wrap; align-items: center;
    }
    #controls select, #controls input {
      background: var(--surface); color: var(--text);
      border: 1px solid var(--border); border-radius: 6px;
      padding: 6px 10px; font-size: 13px;
    }
    #controls label { color: var(--muted); font-size: 12px; margin-right: 4px; }
    #grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
      gap: 12px;
      padding: 12px 20px;
    }
    .card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 14px;
      transition: border-color .2s;
      cursor: pointer;
    }
    .card:hover { border-color: var(--accent); }
    .card.sev-high { border-left: 3px solid var(--high); }
    .card.sev-medium { border-left: 3px solid var(--medium); }
    .card.sev-low { border-left: 3px solid var(--low); }
    .card-header {
      display: flex; justify-content: space-between; align-items: flex-start;
      margin-bottom: 8px;
    }
    .card-title { font-weight: 600; font-size: 13px; }
    .card-var { font-size: 11px; color: var(--muted); margin-top: 2px; }
    .badge {
      font-size: 10px; font-weight: 700; padding: 2px 8px;
      border-radius: 20px; text-transform: uppercase; letter-spacing: .5px;
    }
    .badge-high { background: rgba(239,68,68,.2); color: var(--high); }
    .badge-medium { background: rgba(245,158,11,.2); color: var(--medium); }
    .badge-low { background: rgba(34,197,94,.2); color: var(--low); }
    .score-bar-bg {
      height: 4px; background: var(--border); border-radius: 2px;
      margin: 6px 0;
    }
    .score-bar-fill { height: 100%; border-radius: 2px; transition: width .5s; }
    .fill-high { background: var(--high); }
    .fill-medium { background: var(--medium); }
    .fill-low { background: var(--low); }
    .interp {
      font-size: 12px; color: var(--muted); margin-top: 6px;
      line-height: 1.4; min-height: 34px;
    }
    .flags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
    .flag-chip {
      font-size: 10px; background: rgba(99,102,241,.15); color: #a5b4fc;
      border-radius: 4px; padding: 1px 6px;
    }
    .chart-wrap { margin-top: 10px; height: 70px; }
    .card-foot {
      margin-top: 8px; font-size: 11px; color: var(--muted);
      display: flex; justify-content: space-between;
    }
    #modal-overlay {
      display: none; position: fixed; inset: 0;
      background: rgba(0,0,0,.7); z-index: 100;
      align-items: center; justify-content: center;
    }
    #modal-overlay.open { display: flex; }
    #modal {
      background: var(--surface); border: 1px solid var(--border);
      border-radius: 12px; padding: 20px;
      width: min(700px, 95vw); max-height: 85vh; overflow-y: auto;
    }
    #modal h2 { font-size: 16px; margin-bottom: 14px; }
    #modal-chart-wrap { height: 200px; margin: 14px 0; }
    #modal-signals { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px,1fr)); gap: 8px; }
    .sig-item {
      background: var(--bg); border-radius: 6px; padding: 8px;
    }
    .sig-label { font-size: 11px; color: var(--muted); }
    .sig-val { font-size: 20px; font-weight: 700; margin-top: 2px; }
    #modal-close {
      float: right; background: none; border: 1px solid var(--border);
      color: var(--text); border-radius: 6px; padding: 4px 10px;
      cursor: pointer; font-size: 13px;
    }
    #empty { text-align: center; padding: 60px; color: var(--muted); }
    #empty h2 { font-size: 20px; margin-bottom: 8px; }
  </style>
</head>
<body>

<header>
  <div>
    <h1>Meteo<span>Void</span></h1>
    <div style="font-size:11px;color:var(--muted);margin-top:2px;">
      Surveillance des anomalies et ruptures de cohérence des flux météo
    </div>
  </div>
  <div id="refresh-info">Actualisation dans <span id="countdown">15</span>s</div>
</header>

<div id="status-bar">
  <div class="stat-pill">
    <div class="dot dot-accent"></div>
    <span id="stat-stations">— stations</span>
  </div>
  <div class="stat-pill">
    <div class="dot dot-high"></div>
    <span id="stat-high">— alerte haute</span>
  </div>
  <div class="stat-pill">
    <div class="dot dot-medium"></div>
    <span id="stat-medium">— surveillance</span>
  </div>
  <div class="stat-pill">
    <div class="dot dot-low"></div>
    <span id="stat-low">— stables</span>
  </div>
  <div class="stat-pill" style="margin-left:auto">
    <div class="dot dot-accent"></div>
    <span id="stat-time">—</span>
  </div>
</div>

<div id="controls">
  <div>
    <label>Région</label>
    <select id="filter-region">
      <option value="">Toutes</option>
    </select>
  </div>
  <div>
    <label>Variable</label>
    <select id="filter-var">
      <option value="">Toutes</option>
    </select>
  </div>
  <div>
    <label>Sévérité min</label>
    <select id="filter-sev">
      <option value="">Toutes</option>
      <option value="high">Haute</option>
      <option value="medium">Moyenne</option>
      <option value="low">Basse</option>
    </select>
  </div>
  <div>
    <label>Recherche</label>
    <input id="filter-search" type="text" placeholder="Station...">
  </div>
</div>

<div id="grid"></div>
<div id="empty" style="display:none">
  <h2>Aucune donnée en direct</h2>
  <p>L'ingestion n'a pas encore produit de rapports, ou aucun résultat ne correspond aux filtres.</p>
</div>

<div id="modal-overlay">
  <div id="modal">
    <button id="modal-close" onclick="closeModal()">Fermer</button>
    <h2 id="modal-title"></h2>
    <div id="modal-interp" style="color:var(--muted);font-size:13px;margin-bottom:10px;"></div>
    <div id="modal-chart-wrap"><canvas id="modal-chart"></canvas></div>
    <div style="font-size:12px;color:var(--muted);margin-bottom:8px;">Signaux détecteurs</div>
    <div id="modal-signals"></div>
  </div>
</div>

<script>
  const SEV_ORDER = {high:2, medium:1, low:0};
  const REFRESH_S = 15;
  let allData = [];
  let charts = {};
  let modalChart = null;
  let countdown = REFRESH_S;
  let selectedCard = null;

  function sevClass(s){ return s==='high'?'sev-high':s==='medium'?'sev-medium':'sev-low'; }
  function badgeClass(s){ return s==='high'?'badge-high':s==='medium'?'badge-medium':'badge-low'; }
  function fillClass(s){ return s==='high'?'fill-high':s==='medium'?'fill-medium':'fill-low'; }
  function sevLabel(s){ return s==='high'?'Alerte':s==='medium'?'Surveillance':'Stable'; }

  function fmtTs(ts){
    if(!ts) return '—';
    const d = new Date(ts*1000);
    return d.toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
  }

  function scoreColor(s){
    if(s>=0.7) return 'var(--high)';
    if(s>=0.35) return 'var(--medium)';
    return 'var(--low)';
  }

  async function fetchAllLatest(){
    const resp = await fetch('/stations');
    const data = await resp.json();
    const stMap = data.stations || {};
    const promises = [];
    for(const [sid, vars] of Object.entries(stMap)){
      for(const v of vars){
        promises.push(
          fetch(`/latest?station_id=${encodeURIComponent(sid)}&variable=${encodeURIComponent(v)}`)
            .then(r=>r.json())
            .catch(()=>null)
        );
      }
    }
    const results = await Promise.all(promises);
    return results.filter(r=>r && r.station_id);
  }

  async function fetchHistory(sid, variable){
    try{
      const r = await fetch(`/stations/${encodeURIComponent(sid)}/history?variable=${encodeURIComponent(variable)}&limit=40&source=stream`);
      return await r.json();
    }catch(e){ return null; }
  }

  function buildMiniChart(canvasId, histItems){
    if(charts[canvasId]){ charts[canvasId].destroy(); }
    const canvas = document.getElementById(canvasId);
    if(!canvas) return;
    const labels = histItems.map(i=>fmtTs(i.ts));
    const scores = histItems.map(i=>+(i.score||0).toFixed(3));
    charts[canvasId] = new Chart(canvas, {
      type:'line',
      data:{
        labels,
        datasets:[{
          data: scores,
          borderColor:'#6366f1',
          backgroundColor:'rgba(99,102,241,.08)',
          borderWidth:1.5,
          pointRadius:0,
          fill:true,
          tension:0.3
        }]
      },
      options:{
        animation:false,
        plugins:{legend:{display:false},tooltip:{enabled:false}},
        scales:{
          x:{display:false},
          y:{display:false,min:0,max:1}
        },
        responsive:true,
        maintainAspectRatio:false
      }
    });
  }

  async function renderCard(item, container){
    const sid = item.station_id || '';
    const variable = item.variable || '';
    const meteo = item.meteo || {};
    const sev = meteo.severity || 'low';
    const score = +(item.score||0);
    const flags = meteo.flags || [];
    const interp = meteo.interpretation || '';
    const cardId = `card-${sid}-${variable}`.replace(/[^a-zA-Z0-9-]/g,'_');
    const chartId = `chart-${cardId}`;

    const flagsHtml = flags.map(f=>`<span class="flag-chip">${f}</span>`).join('');

    const div = document.createElement('div');
    div.className = `card ${sevClass(sev)}`;
    div.id = cardId;
    div.dataset.sid = sid;
    div.dataset.var = variable;
    div.dataset.sev = sev;
    div.dataset.region = (sid.split('_')[0]||'').toLowerCase();
    div.innerHTML = `
      <div class="card-header">
        <div>
          <div class="card-title">${sid}</div>
          <div class="card-var">${variable}</div>
        </div>
        <span class="badge ${badgeClass(sev)}">${sevLabel(sev)}</span>
      </div>
      <div class="score-bar-bg">
        <div class="score-bar-fill ${fillClass(sev)}" style="width:${Math.round(score*100)}%"></div>
      </div>
      <div style="font-size:11px;color:var(--muted);margin-top:2px;">Score : <strong style="color:${scoreColor(score)}">${score.toFixed(3)}</strong></div>
      <div class="interp">${interp || '—'}</div>
      <div class="flags">${flagsHtml}</div>
      <div class="chart-wrap"><canvas id="${chartId}"></canvas></div>
      <div class="card-foot">
        <span>${fmtTs(item.ts)}</span>
        <span>${item.state||'—'}</span>
      </div>
    `;
    div.addEventListener('click', ()=>openModal(item));
    container.appendChild(div);

    // Mini history chart
    const hist = await fetchHistory(sid, variable);
    const histItems = (hist && hist.items) ? hist.items : [];
    if(histItems.length > 1){
      buildMiniChart(chartId, histItems);
    }
  }

  function getFilters(){
    return {
      region: document.getElementById('filter-region').value,
      variable: document.getElementById('filter-var').value,
      sev: document.getElementById('filter-sev').value,
      search: document.getElementById('filter-search').value.toLowerCase().trim()
    };
  }

  function applyFilters(data){
    const f = getFilters();
    return data.filter(item=>{
      const sid = (item.station_id||'').toLowerCase();
      const variable = (item.variable||'').toLowerCase();
      const sev = (item.meteo||{}).severity||'low';
      const region = (sid.split('_')[0]||'');
      if(f.region && region !== f.region) return false;
      if(f.variable && variable !== f.variable) return false;
      if(f.sev && sev !== f.sev) return false;
      if(f.search && !sid.includes(f.search) && !variable.includes(f.search)) return false;
      return true;
    });
  }

  function populateFilters(data){
    const regions = [...new Set(data.map(d=>(d.station_id||'').split('_')[0].toLowerCase()))].sort();
    const variables = [...new Set(data.map(d=>d.variable||''))].sort();
    const rSel = document.getElementById('filter-region');
    const vSel = document.getElementById('filter-var');
    const curR = rSel.value; const curV = vSel.value;
    rSel.innerHTML = '<option value="">Toutes</option>' + regions.map(r=>`<option value="${r}">${r}</option>`).join('');
    vSel.innerHTML = '<option value="">Toutes</option>' + variables.map(v=>`<option value="${v}">${v}</option>`).join('');
    if(curR) rSel.value = curR;
    if(curV) vSel.value = curV;
  }

  async function render(data){
    const filtered = applyFilters(data);
    filtered.sort((a,b)=>{
      const sa = (a.meteo||{}).severity||'low';
      const sb = (b.meteo||{}).severity||'low';
      const diff = (SEV_ORDER[sb]||0)-(SEV_ORDER[sa]||0);
      if(diff!==0) return diff;
      return (b.score||0)-(a.score||0);
    });

    const grid = document.getElementById('grid');
    const empty = document.getElementById('empty');
    grid.innerHTML = '';
    // Destroy all old mini charts
    for(const id in charts){ try{ charts[id].destroy(); }catch(e){} }
    charts = {};

    if(filtered.length === 0){
      empty.style.display = 'block';
      return;
    }
    empty.style.display = 'none';

    const frag = document.createDocumentFragment();
    const tempDiv = document.createElement('div');
    // Render cards one by one (async for charts)
    const renderPromises = filtered.map(item=>renderCard(item, grid));
    await Promise.all(renderPromises);

    updateStatusBar(data);
  }

  function updateStatusBar(data){
    const high = data.filter(d=>(d.meteo||{}).severity==='high').length;
    const medium = data.filter(d=>(d.meteo||{}).severity==='medium').length;
    const low = data.filter(d=>(d.meteo||{}).severity==='low').length;
    document.getElementById('stat-stations').textContent = `${data.length} station${data.length>1?'s':''}`;
    document.getElementById('stat-high').textContent = `${high} alerte haute`;
    document.getElementById('stat-medium').textContent = `${medium} surveillance`;
    document.getElementById('stat-low').textContent = `${low} stable${low>1?'s':''}`;
    document.getElementById('stat-time').textContent = new Date().toLocaleTimeString('fr-FR');
  }

  async function refresh(){
    try{
      allData = await fetchAllLatest();
      populateFilters(allData);
      await render(allData);
    }catch(e){
      console.error('refresh error', e);
    }
  }

  // Countdown timer
  setInterval(()=>{
    countdown--;
    if(countdown <= 0){
      countdown = REFRESH_S;
      refresh();
    }
    document.getElementById('countdown').textContent = countdown;
  }, 1000);

  // Filter change -> re-render from cached data (no new fetch)
  ['filter-region','filter-var','filter-sev','filter-search'].forEach(id=>{
    document.getElementById(id).addEventListener('change', ()=>render(allData));
    if(id==='filter-search'){
      document.getElementById(id).addEventListener('input', ()=>render(allData));
    }
  });

  // Modal
  async function openModal(item){
    selectedCard = item;
    const sid = item.station_id||'';
    const variable = item.variable||'';
    const meteo = item.meteo||{};
    const signals = item.signals||{};
    document.getElementById('modal-title').textContent = `${sid} — ${variable}`;
    document.getElementById('modal-interp').textContent = meteo.interpretation||'';
    document.getElementById('modal-overlay').classList.add('open');

    // Signals
    const sigDiv = document.getElementById('modal-signals');
    sigDiv.innerHTML = '';
    const sigOrder = ['gap','volatility','outlier','flatline','spike','drift','spatial','multivar'];
    for(const sig of sigOrder){
      const val = +(signals[sig]||0);
      const item2 = document.createElement('div');
      item2.className = 'sig-item';
      item2.innerHTML = `<div class="sig-label">${sig}</div><div class="sig-val" style="color:${scoreColor(val)}">${val.toFixed(3)}</div>`;
      sigDiv.appendChild(item2);
    }

    // History chart in modal
    if(modalChart){ modalChart.destroy(); modalChart=null; }
    const hist = await fetchHistory(sid, variable);
    const histItems = (hist && hist.items) ? [...hist.items].reverse() : [];
    const canvas = document.getElementById('modal-chart');
    if(histItems.length > 1 && canvas){
      modalChart = new Chart(canvas, {
        type:'line',
        data:{
          labels: histItems.map(i=>fmtTs(i.ts)),
          datasets:[{
            label:'Score',
            data: histItems.map(i=>+(i.score||0).toFixed(3)),
            borderColor:'#6366f1',
            backgroundColor:'rgba(99,102,241,.1)',
            borderWidth:2,
            pointRadius:2,
            fill:true,
            tension:0.3
          }]
        },
        options:{
          animation:false,
          plugins:{legend:{display:false}},
          scales:{
            x:{ticks:{color:'#6b7194',maxTicksLimit:8},grid:{color:'rgba(255,255,255,.05)'}},
            y:{min:0,max:1,ticks:{color:'#6b7194'},grid:{color:'rgba(255,255,255,.05)'}}
          },
          responsive:true,
          maintainAspectRatio:false
        }
      });
    }
  }

  function closeModal(){
    document.getElementById('modal-overlay').classList.remove('open');
    if(modalChart){ modalChart.destroy(); modalChart=null; }
  }
  document.getElementById('modal-overlay').addEventListener('click',e=>{
    if(e.target===document.getElementById('modal-overlay')) closeModal();
  });

  // Initial load
  refresh();
</script>
</body>
</html>"""
