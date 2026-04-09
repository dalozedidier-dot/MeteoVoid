"""PostgreSQL persistence layer for MeteoVoid.

Tables:
  observations  – raw ingested values (station_id, variable, ts, value)
  reports       – computed anomaly reports (full JSON payload)
  alerts        – emitted alerts (severity >= medium)

Uses psycopg2 directly to avoid pulling a full ORM for 3 tables.
Schema is created automatically on first connection (idempotent).
"""
from __future__ import annotations

import json
import os
import time
from typing import Any


def _get_db_url() -> str:
    return os.getenv("DATABASE_URL", "")


def _connect() -> Any:
    try:
        import psycopg2  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "psycopg2 is required for database persistence. "
            "Install with: pip install psycopg2-binary"
        ) from exc
    url = _get_db_url()
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    return psycopg2.connect(url)


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS observations (
    id          BIGSERIAL PRIMARY KEY,
    station_id  TEXT NOT NULL,
    variable    TEXT NOT NULL,
    ts          DOUBLE PRECISION NOT NULL,
    value       DOUBLE PRECISION NOT NULL,
    source      TEXT NOT NULL DEFAULT 'unknown',
    inserted_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_obs_station_var_ts
    ON observations (station_id, variable, ts DESC);

CREATE TABLE IF NOT EXISTS reports (
    id          BIGSERIAL PRIMARY KEY,
    station_id  TEXT NOT NULL,
    variable    TEXT NOT NULL,
    ts          DOUBLE PRECISION NOT NULL,
    ts_ingest   DOUBLE PRECISION NOT NULL,
    score       DOUBLE PRECISION NOT NULL,
    state       TEXT NOT NULL,
    severity    TEXT NOT NULL,
    flags       TEXT NOT NULL,          -- JSON array serialised as text
    interpretation TEXT NOT NULL,
    payload     TEXT NOT NULL,          -- full JSON report
    inserted_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rep_station_var_ts
    ON reports (station_id, variable, ts DESC);
CREATE INDEX IF NOT EXISTS idx_rep_severity_ts
    ON reports (severity, ts DESC);

CREATE TABLE IF NOT EXISTS alerts (
    id          BIGSERIAL PRIMARY KEY,
    station_id  TEXT NOT NULL,
    variable    TEXT NOT NULL,
    ts          DOUBLE PRECISION NOT NULL,
    severity    TEXT NOT NULL,
    flags       TEXT NOT NULL,
    interpretation TEXT NOT NULL,
    score       DOUBLE PRECISION NOT NULL,
    inserted_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alerts_ts
    ON alerts (ts DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_severity_ts
    ON alerts (severity, ts DESC);
"""


def ensure_schema() -> None:
    """Create tables if they don't exist. Safe to call repeatedly."""
    if not _get_db_url():
        return
    try:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(_SCHEMA_SQL)
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:  # pragma: no cover
        # DB is optional; log and continue.
        print(f"[db] schema init failed: {exc}", flush=True)


def insert_observation(
    *,
    station_id: str,
    variable: str,
    ts: float,
    value: float,
    source: str = "unknown",
) -> None:
    """Insert one raw observation. No-ops if DATABASE_URL is unset."""
    if not _get_db_url():
        return
    try:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO observations
                        (station_id, variable, ts, value, source, inserted_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (station_id, variable, ts, value, source, time.time()),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:  # pragma: no cover
        print(f"[db] insert_observation failed: {exc}", flush=True)


def insert_report(report: dict[str, Any]) -> None:
    """Persist a full anomaly report. No-ops if DATABASE_URL is unset."""
    if not _get_db_url():
        return
    try:
        meteo = report.get("meteo") or {}
        severity = str(meteo.get("severity", "low"))
        flags = json.dumps(meteo.get("flags", []))
        interpretation = str(meteo.get("interpretation", ""))
        station_id = str(report.get("station_id", ""))
        variable = str(report.get("variable", ""))
        ts = float(report.get("ts") or 0.0)
        ts_ingest = float(report.get("ts_ingest") or ts)
        score = float(report.get("score") or 0.0)
        state = str(report.get("state", "stable"))

        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO reports
                        (station_id, variable, ts, ts_ingest, score, state,
                         severity, flags, interpretation, payload, inserted_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        station_id,
                        variable,
                        ts,
                        ts_ingest,
                        score,
                        state,
                        severity,
                        flags,
                        interpretation,
                        json.dumps(report, separators=(",", ":")),
                        time.time(),
                    ),
                )
                # Mirror to alerts table when severity >= medium
                if severity in ("medium", "high"):
                    cur.execute(
                        """
                        INSERT INTO alerts
                            (station_id, variable, ts, severity, flags,
                             interpretation, score, inserted_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            station_id,
                            variable,
                            ts,
                            severity,
                            flags,
                            interpretation,
                            score,
                            time.time(),
                        ),
                    )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:  # pragma: no cover
        print(f"[db] insert_report failed: {exc}", flush=True)


# ---------------------------------------------------------------------------
# Read helpers used by the API
# ---------------------------------------------------------------------------

def query_alerts(
    *,
    limit: int = 50,
    severity: str | None = None,
    station_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return recent alerts from the DB, newest first."""
    if not _get_db_url():
        return []
    try:
        conn = _connect()
        try:
            clauses: list[str] = []
            params: list[Any] = []
            if severity:
                clauses.append("severity = %s")
                params.append(severity)
            if station_id:
                clauses.append("station_id = %s")
                params.append(station_id)
            where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
            params.append(max(1, min(500, int(limit))))
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT station_id, variable, ts, severity, flags,
                           interpretation, score, inserted_at
                    FROM alerts
                    {where}
                    ORDER BY ts DESC
                    LIMIT %s
                    """,
                    params,
                )
                rows = cur.fetchall()
            return [
                {
                    "station_id": r[0],
                    "variable": r[1],
                    "ts": r[2],
                    "severity": r[3],
                    "flags": json.loads(r[4]) if r[4] else [],
                    "interpretation": r[5],
                    "score": r[6],
                    "inserted_at": r[7],
                }
                for r in rows
            ]
        finally:
            conn.close()
    except Exception as exc:  # pragma: no cover
        print(f"[db] query_alerts failed: {exc}", flush=True)
        return []


def query_station_history(
    *,
    station_id: str,
    variable: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Return recent reports for a station from the DB, newest first."""
    if not _get_db_url():
        return []
    try:
        conn = _connect()
        try:
            params: list[Any] = [station_id]
            var_clause = ""
            if variable:
                var_clause = "AND variable = %s"
                params.append(variable)
            params.append(max(1, min(2000, int(limit))))
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT station_id, variable, ts, score, state,
                           severity, flags, interpretation
                    FROM reports
                    WHERE station_id = %s {var_clause}
                    ORDER BY ts DESC
                    LIMIT %s
                    """,
                    params,
                )
                rows = cur.fetchall()
            return [
                {
                    "station_id": r[0],
                    "variable": r[1],
                    "ts": r[2],
                    "score": r[3],
                    "state": r[4],
                    "severity": r[5],
                    "flags": json.loads(r[6]) if r[6] else [],
                    "interpretation": r[7],
                }
                for r in rows
            ]
        finally:
            conn.close()
    except Exception as exc:  # pragma: no cover
        print(f"[db] query_station_history failed: {exc}", flush=True)
        return []


def query_top_anomalies(*, limit: int = 10, hours: float = 1.0) -> list[dict[str, Any]]:
    """Return top anomalies by score in the last N hours."""
    if not _get_db_url():
        return []
    try:
        since = time.time() - hours * 3600
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT station_id, variable, ts, score, state,
                           severity, flags, interpretation
                    FROM reports
                    WHERE ts >= %s
                    ORDER BY score DESC
                    LIMIT %s
                    """,
                    (since, max(1, min(100, int(limit)))),
                )
                rows = cur.fetchall()
            return [
                {
                    "station_id": r[0],
                    "variable": r[1],
                    "ts": r[2],
                    "score": r[3],
                    "state": r[4],
                    "severity": r[5],
                    "flags": json.loads(r[6]) if r[6] else [],
                    "interpretation": r[7],
                }
                for r in rows
            ]
        finally:
            conn.close()
    except Exception as exc:  # pragma: no cover
        print(f"[db] query_top_anomalies failed: {exc}", flush=True)
        return []


def query_summary() -> dict[str, Any]:
    """Return global summary counters."""
    if not _get_db_url():
        return {"db": "unavailable"}
    try:
        since_1h = time.time() - 3600
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM reports")
                total_reports = (cur.fetchone() or [0])[0]
                cur.execute(
                    "SELECT COUNT(*) FROM reports WHERE ts >= %s AND severity = 'high'",
                    (since_1h,),
                )
                high_1h = (cur.fetchone() or [0])[0]
                cur.execute(
                    "SELECT COUNT(*) FROM reports WHERE ts >= %s AND severity = 'medium'",
                    (since_1h,),
                )
                medium_1h = (cur.fetchone() or [0])[0]
                cur.execute("SELECT COUNT(DISTINCT station_id) FROM reports")
                stations_seen = (cur.fetchone() or [0])[0]
                cur.execute("SELECT AVG(score) FROM reports WHERE ts >= %s", (since_1h,))
                avg_score_1h = (cur.fetchone() or [None])[0]
            return {
                "total_reports": int(total_reports),
                "stations_seen": int(stations_seen),
                "last_1h": {
                    "high_alerts": int(high_1h),
                    "medium_alerts": int(medium_1h),
                    "avg_score": round(float(avg_score_1h), 4) if avg_score_1h is not None else None,
                },
            }
        finally:
            conn.close()
    except Exception as exc:  # pragma: no cover
        print(f"[db] query_summary failed: {exc}", flush=True)
        return {"db": "error", "detail": str(exc)}
