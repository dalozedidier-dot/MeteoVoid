from __future__ import annotations

from datetime import UTC, datetime

from meteovoid.stream import _parse_ts


def test_parse_ts_epoch() -> None:
    epoch_dt = _parse_ts("0")
    assert epoch_dt == datetime(1970, 1, 1, tzinfo=UTC)
