from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from meteovoid.core import scan_series_for_voids


def test_scan_parses_iso8601_with_microseconds_and_z() -> None:
    # Pandas has edge cases parsing ...000001Z unless format="ISO8601" is used.
    with TemporaryDirectory() as d:
        p = Path(d) / "t.csv"
        p.write_text(
            "timestamp,value\n"
            "2026-01-01T00:00:00Z,0\n"
            "2026-01-01T00:00:00.000001Z,1\n",
            encoding="utf-8",
        )
        out = scan_series_for_voids(p, max_gap_seconds=3600)
        assert out["void_count"] == 0
