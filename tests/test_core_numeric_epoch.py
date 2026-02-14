from __future__ import annotations

from pathlib import Path

import pytest

from meteovoid.core import scan_series_for_voids


def test_scan_parses_numeric_epoch_units(tmp_path: Path) -> None:
    # Seconds
    p_s = tmp_path / "s.csv"
    p_s.write_text("timestamp,value\n1700000000,0\n1700000001,1\n", encoding="utf-8")
    out_s = scan_series_for_voids(p_s, max_gap_seconds=3600)
    assert out_s["void_count"] == 0

    # Milliseconds (heuristic should choose ms)
    p_ms = tmp_path / "ms.csv"
    p_ms.write_text("timestamp,value\n1700000000000,0\n1700000001000,1\n", encoding="utf-8")
    out_ms = scan_series_for_voids(p_ms, max_gap_seconds=3600)
    assert out_ms["void_count"] == 0

    # Nanoseconds (heuristic should choose ns)
    p_ns = tmp_path / "ns.csv"
    p_ns.write_text(
        "timestamp,value\n1700000000000000000,0\n1700000000000001000,1\n",
        encoding="utf-8",
    )
    out_ns = scan_series_for_voids(p_ns, max_gap_seconds=3600)
    assert out_ns["void_count"] == 0


def test_scan_errors_on_unparseable_timestamps(tmp_path: Path) -> None:
    p = tmp_path / "bad.csv"
    p.write_text("timestamp,value\nnot-a-ts,0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="could not be parsed"):
        scan_series_for_voids(p)
