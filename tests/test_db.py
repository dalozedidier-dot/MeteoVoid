"""Tests for meteovoid.db using mocked psycopg2."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import meteovoid.db as db_mod

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_conn(fetchone_side_effect=None, fetchall_return=None, rowcount=1):
    """Return a mock psycopg2 connection + cursor."""
    cur = MagicMock()
    cur.rowcount = rowcount
    if fetchone_side_effect is not None:
        cur.fetchone.side_effect = fetchone_side_effect
    if fetchall_return is not None:
        cur.fetchall.return_value = fetchall_return
    # Make cursor usable as a context manager
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)

    conn = MagicMock()
    conn.cursor.return_value = cur
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    return conn, cur


# ---------------------------------------------------------------------------
# _get_db_url / _connect
# ---------------------------------------------------------------------------


def test_get_db_url_missing(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert db_mod._get_db_url() == ""


def test_get_db_url_present(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    assert db_mod._get_db_url() == "postgresql://u:p@h/db"


def test_connect_no_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        db_mod._connect()


def test_connect_with_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    mock_conn = MagicMock()
    with patch("psycopg2.connect", return_value=mock_conn) as mock_connect:
        result = db_mod._connect()
    mock_connect.assert_called_once_with("postgresql://u:p@h/db")
    assert result is mock_conn


# ---------------------------------------------------------------------------
# ensure_schema
# ---------------------------------------------------------------------------


def test_ensure_schema_no_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    # Should be a no-op
    db_mod.ensure_schema()


def test_ensure_schema_ok(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    conn, cur = _make_conn()
    with patch("psycopg2.connect", return_value=conn):
        db_mod.ensure_schema()
    cur.execute.assert_called_once()
    conn.commit.assert_called_once()
    conn.close.assert_called_once()


def test_ensure_schema_error(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    with patch("psycopg2.connect", side_effect=Exception("boom")):
        # Should not raise
        db_mod.ensure_schema()


# ---------------------------------------------------------------------------
# insert_report
# ---------------------------------------------------------------------------


def test_insert_report_no_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_mod.insert_report({"station_id": "X", "variable": "temp"})


def test_insert_report_low_severity(monkeypatch):
    """Low severity: insert report but don't open alert (no existing open alert)."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    conn, cur = _make_conn(fetchone_side_effect=[None])  # no open alert
    with patch("psycopg2.connect", return_value=conn):
        db_mod.insert_report(
            {
                "station_id": "BE_UCCLE",
                "variable": "temperature_2m",
                "ts": 1700000000.0,
                "ts_ingest": 1700000001.0,
                "score": 0.2,
                "state": "stable",
                "meteo": {
                    "severity": "low",
                    "flags": ["ok"],
                    "interpretation": "Tout va bien",
                },
            }
        )
    conn.commit.assert_called_once()


def test_insert_report_medium_severity_new_alert(monkeypatch):
    """Medium severity, no existing open alert → opens a new one."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    conn, cur = _make_conn(fetchone_side_effect=[None, (42,)])  # no open; RETURNING id=42
    with patch("psycopg2.connect", return_value=conn):
        db_mod.insert_report(
            {
                "station_id": "BE_UCCLE",
                "variable": "temperature_2m",
                "ts": 1700000000.0,
                "score": 0.8,
                "state": "anomaly",
                "meteo": {
                    "severity": "medium",
                    "flags": ["spike"],
                    "interpretation": "Anomalie détectée",
                },
            }
        )
    conn.commit.assert_called_once()


def test_insert_report_high_severity_existing_alert(monkeypatch):
    """High severity, existing open alert → update it."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    conn, cur = _make_conn(fetchone_side_effect=[(99,)])  # existing alert id=99
    with patch("psycopg2.connect", return_value=conn):
        db_mod.insert_report(
            {
                "station_id": "DE_BERLIN",
                "variable": "wind_speed_10m",
                "ts": 1700000000.0,
                "score": 0.95,
                "state": "anomaly",
                "meteo": {
                    "severity": "high",
                    "flags": ["extreme"],
                    "interpretation": "Vent extrême",
                },
            }
        )
    conn.commit.assert_called_once()


def test_insert_report_low_severity_auto_resolves(monkeypatch):
    """Low severity, existing open alert → auto-resolve it."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    conn, cur = _make_conn(fetchone_side_effect=[(77,)])  # existing alert id=77
    with patch("psycopg2.connect", return_value=conn):
        db_mod.insert_report(
            {
                "station_id": "FR_PARIS",
                "variable": "precipitation",
                "ts": 1700000000.0,
                "score": 0.1,
                "state": "stable",
                "meteo": {
                    "severity": "low",
                    "flags": [],
                    "interpretation": "Normal",
                },
            }
        )
    conn.commit.assert_called_once()


def test_insert_report_exception(monkeypatch):
    """DB error should be swallowed, not raised."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    with patch("psycopg2.connect", side_effect=Exception("db down")):
        db_mod.insert_report({"station_id": "X"})  # Should not raise


# ---------------------------------------------------------------------------
# update_alert_status
# ---------------------------------------------------------------------------


def test_update_alert_status_invalid_status(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    assert db_mod.update_alert_status(1, "unknown_status") is False


def test_update_alert_status_no_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert db_mod.update_alert_status(1, "acknowledged") is False


def test_update_alert_status_ok(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    conn, cur = _make_conn(rowcount=1)
    with patch("psycopg2.connect", return_value=conn):
        result = db_mod.update_alert_status(42, "acknowledged", comment="Checked")
    assert result is True
    conn.commit.assert_called_once()


def test_update_alert_status_not_found(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    conn, cur = _make_conn(rowcount=0)
    with patch("psycopg2.connect", return_value=conn):
        result = db_mod.update_alert_status(9999, "resolved")
    assert result is False


def test_update_alert_status_exception(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    with patch("psycopg2.connect", side_effect=Exception("boom")):
        assert db_mod.update_alert_status(1, "resolved") is False


# ---------------------------------------------------------------------------
# get_alert_detail
# ---------------------------------------------------------------------------


def test_get_alert_detail_no_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert db_mod.get_alert_detail(1) is None


def test_get_alert_detail_not_found(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    conn, cur = _make_conn(fetchone_side_effect=[None])
    with patch("psycopg2.connect", return_value=conn):
        assert db_mod.get_alert_detail(999) is None


def test_get_alert_detail_found(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    alert_row = (
        1,
        "BE_UCCLE",
        "temperature_2m",
        1700000000.0,
        "high",
        '["spike"]',
        "Anomalie",
        0.9,
        "open",
        None,
        None,
        1700000001.0,
    )
    lifecycle_rows = [("open", None, 1700000001.0)]
    conn, cur = _make_conn(
        fetchone_side_effect=[alert_row],
        fetchall_return=lifecycle_rows,
    )
    with patch("psycopg2.connect", return_value=conn):
        result = db_mod.get_alert_detail(1)
    assert result is not None
    assert result["station_id"] == "BE_UCCLE"
    assert result["flags"] == ["spike"]
    assert len(result["lifecycle"]) == 1


def test_get_alert_detail_exception(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    with patch("psycopg2.connect", side_effect=Exception("boom")):
        assert db_mod.get_alert_detail(1) is None


# ---------------------------------------------------------------------------
# log_ingest_failure
# ---------------------------------------------------------------------------


def test_log_ingest_failure_no_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_mod.log_ingest_failure(station_id="X", source="openmeteo", error="err")


def test_log_ingest_failure_ok(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    conn, cur = _make_conn()
    with patch("psycopg2.connect", return_value=conn):
        db_mod.log_ingest_failure(
            station_id="BE_UCCLE", source="openmeteo", error="timeout", url="http://x"
        )
    conn.commit.assert_called_once()


def test_log_ingest_failure_exception(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    with patch("psycopg2.connect", side_effect=Exception("boom")):
        db_mod.log_ingest_failure(station_id="X", source="s", error="e")


# ---------------------------------------------------------------------------
# query_ingest_health
# ---------------------------------------------------------------------------


def test_query_ingest_health_no_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert db_mod.query_ingest_health() == []


def test_query_ingest_health_ok(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    # Two fetchall calls: success rows, then failure rows
    conn, cur = _make_conn()
    cur.fetchall.side_effect = [
        [("BE_UCCLE", 1700000000.0, "ok", None)],  # successes
        [("BE_UCCLE", 1699999000.0, "old error")],  # failures (older than success)
    ]
    with patch("psycopg2.connect", return_value=conn):
        result = db_mod.query_ingest_health()
    assert isinstance(result, list)
    assert result[0]["station_id"] == "BE_UCCLE"
    assert result[0]["status"] == "ok"


def test_query_ingest_health_failure_newer(monkeypatch):
    """When last failure is newer than last success, status should be 'failing'."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    conn, cur = _make_conn()
    cur.fetchall.side_effect = [
        [("BE_UCCLE", 1700000000.0, "ok", None)],
        [("BE_UCCLE", 1700001000.0, "recent error")],  # failure is NEWER
    ]
    with patch("psycopg2.connect", return_value=conn):
        result = db_mod.query_ingest_health()
    assert result[0]["status"] == "failing"


def test_query_ingest_health_exception(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    with patch("psycopg2.connect", side_effect=Exception("boom")):
        assert db_mod.query_ingest_health() == []


# ---------------------------------------------------------------------------
# get_thresholds
# ---------------------------------------------------------------------------


def test_get_thresholds_no_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert db_mod.get_thresholds() == []


def test_get_thresholds_all(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    rows = [(1, None, "temperature_2m", 0.5, 0.8, 1700000000.0)]
    conn, cur = _make_conn(fetchall_return=rows)
    with patch("psycopg2.connect", return_value=conn):
        result = db_mod.get_thresholds()
    assert len(result) == 1
    assert result[0]["variable"] == "temperature_2m"


def test_get_thresholds_filtered(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    rows = [(2, "BE_UCCLE", "wind_speed_10m", 0.6, 0.9, 1700000000.0)]
    conn, cur = _make_conn(fetchall_return=rows)
    with patch("psycopg2.connect", return_value=conn):
        result = db_mod.get_thresholds(station_id="BE_UCCLE", variable="wind_speed_10m")
    assert len(result) == 1
    assert result[0]["station_id"] == "BE_UCCLE"


def test_get_thresholds_exception(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    with patch("psycopg2.connect", side_effect=Exception("boom")):
        assert db_mod.get_thresholds() == []


# ---------------------------------------------------------------------------
# upsert_threshold
# ---------------------------------------------------------------------------


def test_upsert_threshold_no_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert db_mod.upsert_threshold(variable="temperature_2m") is False


def test_upsert_threshold_ok(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    conn, cur = _make_conn()
    with patch("psycopg2.connect", return_value=conn):
        result = db_mod.upsert_threshold(
            variable="temperature_2m",
            watch_threshold=0.5,
            alert_threshold=0.8,
            station_id="BE_UCCLE",
        )
    assert result is True
    conn.commit.assert_called_once()


def test_upsert_threshold_exception(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    with patch("psycopg2.connect", side_effect=Exception("boom")):
        assert db_mod.upsert_threshold(variable="temperature_2m") is False


# ---------------------------------------------------------------------------
# apply_retention
# ---------------------------------------------------------------------------


def test_apply_retention_no_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert db_mod.apply_retention(retention_days=30) == {}


def test_apply_retention_ok(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    conn, cur = _make_conn(rowcount=5)
    with patch("psycopg2.connect", return_value=conn):
        result = db_mod.apply_retention(retention_days=7)
    # 3 tables: reports, observations, ingest_failures
    assert set(result.keys()) == {"reports", "observations", "ingest_failures"}
    assert all(v == 5 for v in result.values())
    conn.commit.assert_called_once()


def test_apply_retention_exception(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    with patch("psycopg2.connect", side_effect=Exception("boom")):
        result = db_mod.apply_retention(retention_days=30)
    assert result == {}


# ---------------------------------------------------------------------------
# query_timeseries
# ---------------------------------------------------------------------------


def test_query_timeseries_no_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert db_mod.query_timeseries(station_id="X", variable="y") == []


def test_query_timeseries_ok(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    rows = [(1700000000.0, 0.7, "anomaly", "high")]
    conn, cur = _make_conn(fetchall_return=rows)
    with patch("psycopg2.connect", return_value=conn):
        result = db_mod.query_timeseries(
            station_id="BE_UCCLE",
            variable="temperature_2m",
            since=1699990000.0,
            until=1700100000.0,
        )
    assert len(result) == 1
    assert result[0]["score"] == 0.7
    assert result[0]["state"] == "anomaly"


def test_query_timeseries_exception(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    with patch("psycopg2.connect", side_effect=Exception("boom")):
        assert db_mod.query_timeseries(station_id="X", variable="y") == []


# ---------------------------------------------------------------------------
# query_alerts
# ---------------------------------------------------------------------------


def test_query_alerts_no_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert db_mod.query_alerts() == []


def test_query_alerts_ok(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    rows = [
        (
            1,
            "BE_UCCLE",
            "temperature_2m",
            1700000000.0,
            "high",
            '["spike"]',
            "Anomalie",
            0.9,
            "open",
            None,
            None,
            1700000001.0,
        )
    ]
    conn, cur = _make_conn(fetchall_return=rows)
    with patch("psycopg2.connect", return_value=conn):
        result = db_mod.query_alerts(severity="high", status="open", station_id="BE_UCCLE")
    assert len(result) == 1
    assert result[0]["id"] == 1
    assert result[0]["flags"] == ["spike"]


def test_query_alerts_empty_flags(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    rows = [
        (
            2,
            "FR_PARIS",
            "wind_speed_10m",
            1700000000.0,
            "medium",
            None,  # null flags
            "Vent",
            0.7,
            "open",
            None,
            None,
            1700000001.0,
        )
    ]
    conn, cur = _make_conn(fetchall_return=rows)
    with patch("psycopg2.connect", return_value=conn):
        result = db_mod.query_alerts()
    assert result[0]["flags"] == []


def test_query_alerts_exception(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    with patch("psycopg2.connect", side_effect=Exception("boom")):
        assert db_mod.query_alerts() == []


# ---------------------------------------------------------------------------
# query_station_history
# ---------------------------------------------------------------------------


def test_query_station_history_no_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert db_mod.query_station_history(station_id="X") == []


def test_query_station_history_ok(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    rows = [
        (
            "BE_UCCLE",
            "temperature_2m",
            1700000000.0,
            0.7,
            "anomaly",
            "high",
            '["spike"]',
            "Anomalie",
        )
    ]
    conn, cur = _make_conn(fetchall_return=rows)
    with patch("psycopg2.connect", return_value=conn):
        result = db_mod.query_station_history(station_id="BE_UCCLE", variable="temperature_2m")
    assert len(result) == 1
    assert result[0]["station_id"] == "BE_UCCLE"


def test_query_station_history_no_variable(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    conn, cur = _make_conn(fetchall_return=[])
    with patch("psycopg2.connect", return_value=conn):
        result = db_mod.query_station_history(station_id="BE_UCCLE")
    assert result == []


def test_query_station_history_exception(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    with patch("psycopg2.connect", side_effect=Exception("boom")):
        assert db_mod.query_station_history(station_id="X") == []


# ---------------------------------------------------------------------------
# query_top_anomalies
# ---------------------------------------------------------------------------


def test_query_top_anomalies_no_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert db_mod.query_top_anomalies() == []


def test_query_top_anomalies_ok(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    rows = [
        (
            "DE_BERLIN",
            "wind_speed_10m",
            1700000000.0,
            0.95,
            "anomaly",
            "high",
            '["extreme"]',
            "Vent extrême",
        )
    ]
    conn, cur = _make_conn(fetchall_return=rows)
    with patch("psycopg2.connect", return_value=conn):
        result = db_mod.query_top_anomalies(limit=5, hours=2.0)
    assert len(result) == 1
    assert result[0]["score"] == 0.95


def test_query_top_anomalies_exception(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    with patch("psycopg2.connect", side_effect=Exception("boom")):
        assert db_mod.query_top_anomalies() == []


# ---------------------------------------------------------------------------
# query_summary
# ---------------------------------------------------------------------------


def test_query_summary_no_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    result = db_mod.query_summary()
    assert result == {"db": "unavailable"}


def test_query_summary_ok(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    conn, cur = _make_conn()
    # 6 fetchone calls: total_reports, high_1h, medium_1h, stations_seen, avg_score, open_alerts
    cur.fetchone.side_effect = [(100,), (5,), (10,), (20,), (0.65,), (3,)]
    with patch("psycopg2.connect", return_value=conn):
        result = db_mod.query_summary()
    assert result["total_reports"] == 100
    assert result["open_alerts"] == 3
    assert result["last_1h"]["high_alerts"] == 5
    assert result["last_1h"]["avg_score"] == 0.65


def test_query_summary_avg_none(monkeypatch):
    """avg_score can be None when no data."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    conn, cur = _make_conn()
    cur.fetchone.side_effect = [(0,), (0,), (0,), (0,), (None,), (0,)]
    with patch("psycopg2.connect", return_value=conn):
        result = db_mod.query_summary()
    assert result["last_1h"]["avg_score"] is None


def test_query_summary_exception(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    with patch("psycopg2.connect", side_effect=Exception("boom")):
        result = db_mod.query_summary()
    assert result["db"] == "error"


# ---------------------------------------------------------------------------
# query_region_summary
# ---------------------------------------------------------------------------


def test_query_region_summary_no_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    result = db_mod.query_region_summary("BE")
    assert result == {"db": "unavailable"}


def test_query_region_summary_ok(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    rows = [("BE_UCCLE", 50, 0.72, 1, 0)]
    conn, cur = _make_conn(fetchall_return=rows)
    with patch("psycopg2.connect", return_value=conn):
        result = db_mod.query_region_summary("BE")
    assert result["region"] == "be"
    assert len(result["stations"]) == 1
    assert result["stations"][0]["had_high_alert"] is True
    assert result["stations"][0]["had_medium_alert"] is False


def test_query_region_summary_no_score(monkeypatch):
    """avg_score can be None/falsy for stations with no data."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    rows = [("FR_PARIS", 0, None, 0, 0)]
    conn, cur = _make_conn(fetchall_return=rows)
    with patch("psycopg2.connect", return_value=conn):
        result = db_mod.query_region_summary("FR")
    assert result["stations"][0]["avg_score_1h"] is None


def test_query_region_summary_exception(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    with patch("psycopg2.connect", side_effect=Exception("boom")):
        result = db_mod.query_region_summary("BE")
    assert result["db"] == "error"
