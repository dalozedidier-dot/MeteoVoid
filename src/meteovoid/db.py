"""PostgreSQL persistence layer for MeteoVoid.

Tables
------
observations      raw ingested values
reports           full computed anomaly reports
alerts            alert events (deduplicated per station/variable, with lifecycle)
alert_lifecycle   history of alert state transitions (per alert_id)
ingest_failures   per-cycle ingest errors
thresholds        per-station/variable scoring thresholds (operator-managed)

Design principles
-----------------
* psycopg2 only — no ORM, no migrations framework.
* All schema changes use ADD COLUMN IF NOT EXISTS / CREATE TABLE IF NOT EXISTS.
* All public functions are silent no-ops when DATABASE_URL is unset.
* All DB errors are caught, logged, and swallowed so they never crash workers.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from .log import get_logger

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

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
    flags       TEXT NOT NULL,
    interpretation TEXT NOT NULL,
    payload     TEXT NOT NULL,
    inserted_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rep_station_var_ts
    ON reports (station_id, variable, ts DESC);
CREATE INDEX IF NOT EXISTS idx_rep_severity_ts
    ON reports (severity, ts DESC);

CREATE TABLE IF NOT EXISTS alerts (
    id              BIGSERIAL PRIMARY KEY,
    station_id      TEXT NOT NULL,
    variable        TEXT NOT NULL,
    ts              DOUBLE PRECISION NOT NULL,
    severity        TEXT NOT NULL,
    flags           TEXT NOT NULL,
    interpretation  TEXT NOT NULL,
    score           DOUBLE PRECISION NOT NULL,
    status          TEXT NOT NULL DEFAULT 'open',
    operator_comment TEXT,
    status_changed_at DOUBLE PRECISION,
    inserted_at     DOUBLE PRECISION NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_alerts_open_dedupe
    ON alerts (station_id, variable)
    WHERE status = 'open';
CREATE INDEX IF NOT EXISTS idx_alerts_ts       ON alerts (ts DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_status   ON alerts (status, ts DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_sev_ts   ON alerts (severity, ts DESC);

ALTER TABLE alerts ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'open';
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS operator_comment TEXT;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS status_changed_at DOUBLE PRECISION;

CREATE TABLE IF NOT EXISTS alert_lifecycle (
    id          BIGSERIAL PRIMARY KEY,
    alert_id    BIGINT NOT NULL,
    status      TEXT NOT NULL,
    comment     TEXT,
    changed_at  DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lifecycle_alert ON alert_lifecycle (alert_id, changed_at DESC);

CREATE TABLE IF NOT EXISTS ingest_failures (
    id          BIGSERIAL PRIMARY KEY,
    station_id  TEXT NOT NULL,
    source      TEXT NOT NULL DEFAULT 'openmeteo',
    ts          DOUBLE PRECISION NOT NULL,
    error       TEXT NOT NULL,
    url         TEXT,
    inserted_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ingest_fail_station ON ingest_failures (station_id, ts DESC);

CREATE TABLE IF NOT EXISTS thresholds (
    id                  BIGSERIAL PRIMARY KEY,
    station_id          TEXT,
    variable            TEXT NOT NULL,
    watch_threshold     DOUBLE PRECISION,
    alert_threshold     DOUBLE PRECISION,
    updated_at          DOUBLE PRECISION NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_thresholds_unique
    ON thresholds (COALESCE(station_id, ''), variable);
"""


def ensure_schema() -> None:
    """Create / migrate tables. Safe to call repeatedly."""
    if not _get_db_url():
        return
    try:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(_SCHEMA_SQL)
            conn.commit()
            _log.info("db.schema_ok")
        finally:
            conn.close()
    except Exception as exc:
        _log.error("db.schema_failed", exc=str(exc))


# ---------------------------------------------------------------------------
# Writes — reports
# ---------------------------------------------------------------------------


def insert_report(report: dict[str, Any]) -> None:
    """Persist a full anomaly report and manage the alert lifecycle."""
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
                _manage_alert_lifecycle(
                    cur, station_id, variable, ts, severity, flags, interpretation, score
                )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        _log.error("db.insert_report_failed", exc=str(exc), station_id=report.get("station_id"))


def _manage_alert_lifecycle(
    cur: Any,
    station_id: str,
    variable: str,
    ts: float,
    severity: str,
    flags: str,
    interpretation: str,
    score: float,
) -> None:
    """Open, update or auto-resolve the open alert for this station/variable."""
    now = time.time()

    # Is there an open alert for this station/variable?
    cur.execute(
        "SELECT id FROM alerts WHERE station_id = %s AND variable = %s AND status = 'open'",
        (station_id, variable),
    )
    row = cur.fetchone()
    existing_id: int | None = row[0] if row else None

    if severity in ("medium", "high"):
        if existing_id is None:
            # Open a new alert
            cur.execute(
                """
                INSERT INTO alerts
                    (station_id, variable, ts, severity, flags,
                     interpretation, score, status, inserted_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'open', %s)
                RETURNING id
                """,
                (station_id, variable, ts, severity, flags, interpretation, score, now),
            )
            alert_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO alert_lifecycle (alert_id, status, comment, changed_at) VALUES (%s, 'open', NULL, %s)",
                (alert_id, now),
            )
        else:
            # Keep alert open; refresh score and interpretation
            cur.execute(
                """
                UPDATE alerts
                   SET ts = %s, severity = %s, flags = %s,
                       interpretation = %s, score = %s
                 WHERE id = %s
                """,
                (ts, severity, flags, interpretation, score, existing_id),
            )
    elif existing_id is not None:
        # Severity dropped to low — auto-resolve
        cur.execute(
            """
            UPDATE alerts
               SET status = 'auto_resolved',
                   status_changed_at = %s
             WHERE id = %s
            """,
            (now, existing_id),
        )
        cur.execute(
            "INSERT INTO alert_lifecycle (alert_id, status, comment, changed_at) VALUES (%s, 'auto_resolved', 'score normalised', %s)",
            (existing_id, now),
        )


# ---------------------------------------------------------------------------
# Alert lifecycle — operator actions
# ---------------------------------------------------------------------------


def update_alert_status(
    alert_id: int,
    status: str,
    comment: str | None = None,
) -> bool:
    """Operator changes alert status. Returns True on success."""
    valid = {"acknowledged", "ignored", "resolved", "open"}
    if status not in valid:
        return False
    if not _get_db_url():
        return False
    try:
        now = time.time()
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE alerts
                       SET status = %s,
                           operator_comment = COALESCE(%s, operator_comment),
                           status_changed_at = %s
                     WHERE id = %s
                    """,
                    (status, comment, now, alert_id),
                )
                affected = cur.rowcount
                if affected:
                    cur.execute(
                        "INSERT INTO alert_lifecycle (alert_id, status, comment, changed_at) VALUES (%s, %s, %s, %s)",
                        (alert_id, status, comment, now),
                    )
            conn.commit()
            return bool(affected)
        finally:
            conn.close()
    except Exception as exc:
        _log.error("db.update_alert_status_failed", exc=str(exc), alert_id=alert_id)
        return False


def get_alert_detail(alert_id: int) -> dict[str, Any] | None:
    """Fetch one alert with its full lifecycle history."""
    if not _get_db_url():
        return None
    try:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, station_id, variable, ts, severity, flags,
                           interpretation, score, status, operator_comment,
                           status_changed_at, inserted_at
                    FROM alerts WHERE id = %s
                    """,
                    (alert_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                alert = {
                    "id": row[0],
                    "station_id": row[1],
                    "variable": row[2],
                    "ts": row[3],
                    "severity": row[4],
                    "flags": json.loads(row[5]) if row[5] else [],
                    "interpretation": row[6],
                    "score": row[7],
                    "status": row[8],
                    "operator_comment": row[9],
                    "status_changed_at": row[10],
                    "inserted_at": row[11],
                }
                cur.execute(
                    """
                    SELECT status, comment, changed_at FROM alert_lifecycle
                    WHERE alert_id = %s ORDER BY changed_at ASC
                    """,
                    (alert_id,),
                )
                alert["lifecycle"] = [
                    {"status": r[0], "comment": r[1], "changed_at": r[2]} for r in cur.fetchall()
                ]
            return alert
        finally:
            conn.close()
    except Exception as exc:
        _log.error("db.get_alert_detail_failed", exc=str(exc), alert_id=alert_id)
        return None


# ---------------------------------------------------------------------------
# Ingest failure journal
# ---------------------------------------------------------------------------


def log_ingest_failure(
    *,
    station_id: str,
    source: str,
    error: str,
    url: str = "",
) -> None:
    """Write one ingest failure. No-ops if DATABASE_URL unset."""
    if not _get_db_url():
        return
    try:
        now = time.time()
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ingest_failures
                        (station_id, source, ts, error, url, inserted_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (station_id, source, now, error, url, now),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        _log.error("db.log_ingest_failure_failed", exc=str(exc))


def query_ingest_health(*, limit_per_station: int = 1) -> list[dict[str, Any]]:
    """Return the latest ingest result per station (success from reports + failures)."""
    if not _get_db_url():
        return []
    try:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                # Most recent successful report per station
                cur.execute(
                    """
                    SELECT DISTINCT ON (station_id)
                           station_id, ts_ingest, 'ok' AS status, NULL AS error
                    FROM reports
                    ORDER BY station_id, ts_ingest DESC
                    """
                )
                success_rows = {
                    r[0]: {"station_id": r[0], "last_success": r[1], "status": "ok"}
                    for r in cur.fetchall()
                }

                # Most recent failure per station
                cur.execute(
                    """
                    SELECT DISTINCT ON (station_id)
                           station_id, ts, error
                    FROM ingest_failures
                    ORDER BY station_id, ts DESC
                    """
                )
                for r in cur.fetchall():
                    sid = r[0]
                    entry = success_rows.setdefault(sid, {"station_id": sid, "last_success": None})
                    last_fail = r[1]
                    last_success = entry.get("last_success") or 0
                    entry["last_failure"] = last_fail
                    entry["last_failure_error"] = r[2]
                    if last_fail > last_success:
                        entry["status"] = "failing"

            result = list(success_rows.values())
            result.sort(key=lambda x: x["station_id"])
            return result
        finally:
            conn.close()
    except Exception as exc:
        _log.error("db.query_ingest_health_failed", exc=str(exc))
        return []


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------


def get_thresholds(
    station_id: str | None = None,
    variable: str | None = None,
) -> list[dict[str, Any]]:
    """Return configured thresholds, optionally filtered."""
    if not _get_db_url():
        return []
    try:
        conn = _connect()
        try:
            clauses: list[str] = []
            params: list[Any] = []
            if station_id is not None:
                clauses.append("(station_id = %s OR station_id IS NULL)")
                params.append(station_id)
            if variable:
                clauses.append("variable = %s")
                params.append(variable)
            where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT id, station_id, variable, watch_threshold, alert_threshold, updated_at FROM thresholds {where} ORDER BY variable",
                    params,
                )
                return [
                    {
                        "id": r[0],
                        "station_id": r[1],
                        "variable": r[2],
                        "watch_threshold": r[3],
                        "alert_threshold": r[4],
                        "updated_at": r[5],
                    }
                    for r in cur.fetchall()
                ]
        finally:
            conn.close()
    except Exception as exc:
        _log.error("db.get_thresholds_failed", exc=str(exc))
        return []


def upsert_threshold(
    *,
    variable: str,
    watch_threshold: float | None = None,
    alert_threshold: float | None = None,
    station_id: str | None = None,
) -> bool:
    """Insert or update a threshold. Returns True on success."""
    if not _get_db_url():
        return False
    try:
        now = time.time()
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO thresholds
                        (station_id, variable, watch_threshold, alert_threshold, updated_at)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (COALESCE(station_id, ''), variable)
                    DO UPDATE SET watch_threshold = EXCLUDED.watch_threshold,
                                  alert_threshold = EXCLUDED.alert_threshold,
                                  updated_at      = EXCLUDED.updated_at
                    """,
                    (station_id, variable, watch_threshold, alert_threshold, now),
                )
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception as exc:
        _log.error("db.upsert_threshold_failed", exc=str(exc))
        return False


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------


def apply_retention(*, retention_days: int = 30) -> dict[str, int]:
    """Delete old rows from reports, observations, ingest_failures.
    Returns counts of deleted rows. No-op if DATABASE_URL unset."""
    if not _get_db_url():
        return {}
    cutoff = time.time() - retention_days * 86400
    deleted: dict[str, int] = {}
    try:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                for table in ("reports", "observations", "ingest_failures"):
                    cur.execute(f"DELETE FROM {table} WHERE inserted_at < %s", (cutoff,))
                    deleted[table] = cur.rowcount
            conn.commit()
            _log.info("db.retention_applied", cutoff=cutoff, deleted=deleted)
        finally:
            conn.close()
    except Exception as exc:
        _log.error("db.retention_failed", exc=str(exc))
    return deleted


# ---------------------------------------------------------------------------
# Timeseries
# ---------------------------------------------------------------------------


def query_timeseries(
    *,
    station_id: str,
    variable: str,
    since: float | None = None,
    until: float | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Return score + state timeseries for a station/variable, oldest first."""
    if not _get_db_url():
        return []
    now = time.time()
    since = since if since is not None else now - 6 * 3600
    until = until if until is not None else now
    try:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT ts, score, state, severity
                    FROM reports
                    WHERE station_id = %s AND variable = %s
                      AND ts BETWEEN %s AND %s
                    ORDER BY ts ASC
                    LIMIT %s
                    """,
                    (station_id, variable, since, until, max(1, min(5000, int(limit)))),
                )
                return [
                    {"ts": r[0], "score": r[1], "state": r[2], "severity": r[3]}
                    for r in cur.fetchall()
                ]
        finally:
            conn.close()
    except Exception as exc:
        _log.error("db.query_timeseries_failed", exc=str(exc))
        return []


# ---------------------------------------------------------------------------
# Read helpers (used by API)
# ---------------------------------------------------------------------------


def query_alerts(
    *,
    limit: int = 50,
    severity: str | None = None,
    station_id: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """Return alerts from the DB, newest first."""
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
            if status:
                clauses.append("status = %s")
                params.append(status)
            where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
            params.append(max(1, min(500, int(limit))))
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT id, station_id, variable, ts, severity, flags,
                           interpretation, score, status, operator_comment,
                           status_changed_at, inserted_at
                    FROM alerts {where}
                    ORDER BY ts DESC LIMIT %s
                    """,
                    params,
                )
                return [
                    {
                        "id": r[0],
                        "station_id": r[1],
                        "variable": r[2],
                        "ts": r[3],
                        "severity": r[4],
                        "flags": json.loads(r[5]) if r[5] else [],
                        "interpretation": r[6],
                        "score": r[7],
                        "status": r[8],
                        "operator_comment": r[9],
                        "status_changed_at": r[10],
                        "inserted_at": r[11],
                    }
                    for r in cur.fetchall()
                ]
        finally:
            conn.close()
    except Exception as exc:
        _log.error("db.query_alerts_failed", exc=str(exc))
        return []


def query_station_history(
    *,
    station_id: str,
    variable: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Return recent reports for a station, newest first."""
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
                    ORDER BY ts DESC LIMIT %s
                    """,
                    params,
                )
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
                    for r in cur.fetchall()
                ]
        finally:
            conn.close()
    except Exception as exc:
        _log.error("db.query_station_history_failed", exc=str(exc))
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
                    ORDER BY score DESC LIMIT %s
                    """,
                    (since, max(1, min(100, int(limit)))),
                )
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
                    for r in cur.fetchall()
                ]
        finally:
            conn.close()
    except Exception as exc:
        _log.error("db.query_top_anomalies_failed", exc=str(exc))
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
                    "SELECT COUNT(*) FROM reports WHERE ts >= %s AND severity = 'high'", (since_1h,)
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
                cur.execute("SELECT COUNT(*) FROM alerts WHERE status = 'open'")
                open_alerts = (cur.fetchone() or [0])[0]
            return {
                "total_reports": int(total_reports),
                "stations_seen": int(stations_seen),
                "open_alerts": int(open_alerts),
                "last_1h": {
                    "high_alerts": int(high_1h),
                    "medium_alerts": int(medium_1h),
                    "avg_score": (
                        round(float(avg_score_1h), 4) if avg_score_1h is not None else None
                    ),
                },
            }
        finally:
            conn.close()
    except Exception as exc:
        _log.error("db.query_summary_failed", exc=str(exc))
        return {"db": "error", "detail": str(exc)}


def query_region_summary(region_prefix: str) -> dict[str, Any]:
    """Return per-station summary for stations whose ID starts with region_prefix."""
    if not _get_db_url():
        return {"db": "unavailable"}
    try:
        since_1h = time.time() - 3600
        prefix_like = region_prefix.upper() + "_%"
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT station_id,
                           COUNT(*) AS report_count,
                           AVG(score) AS avg_score,
                           MAX(CASE WHEN severity='high' THEN 1 ELSE 0 END) AS had_high,
                           MAX(CASE WHEN severity='medium' THEN 1 ELSE 0 END) AS had_medium
                    FROM reports
                    WHERE ts >= %s AND station_id ILIKE %s
                    GROUP BY station_id
                    ORDER BY avg_score DESC
                    """,
                    (since_1h, prefix_like),
                )
                stations = [
                    {
                        "station_id": r[0],
                        "report_count": r[1],
                        "avg_score_1h": round(float(r[2]), 4) if r[2] else None,
                        "had_high_alert": bool(r[3]),
                        "had_medium_alert": bool(r[4]),
                    }
                    for r in cur.fetchall()
                ]
            return {"region": region_prefix.lower(), "stations": stations}
        finally:
            conn.close()
    except Exception as exc:
        _log.error("db.query_region_summary_failed", exc=str(exc))
        return {"db": "error", "detail": str(exc)}
