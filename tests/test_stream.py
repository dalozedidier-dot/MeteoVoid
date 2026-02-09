from __future__ import annotations

from datetime import datetime, timezone

from meteovoid.stream import _parse_float, _parse_ts


def test_parse_float() -> None:
    assert _parse_float("1.25") == 1.25
    assert _parse_float(2) == 2.0


def test_parse_ts_iso_and_epoch() -> None:
    dt = _parse_ts("2026-01-01T00:00:00Z")
    assert dt.tzinfo is not None
    assert dt.year == 2026

    epoch_dt = _parse_ts("0")
    assert epoch_dt == datetime(1970, 1, 1, tzinfo=timezone.utc)
