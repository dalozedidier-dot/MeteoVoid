from __future__ import annotations

from pathlib import Path

import pytest

from meteovoid.core import scan_series_for_voids


def test_scan_detects_one_void(simple_series_csv: Path) -> None:
    report = scan_series_for_voids(simple_series_csv, max_gap_seconds=3600)
    assert report["void_count"] == 1
    assert len(report["voids"]) == 1
    v0 = report["voids"][0]
    assert v0["gap_seconds"] > 3600


def test_scan_no_void_with_large_threshold(simple_series_csv: Path) -> None:
    report = scan_series_for_voids(simple_series_csv, max_gap_seconds=999999)
    assert report["void_count"] == 0
    assert report["voids"] == []


def test_scan_handles_empty_file(empty_csv: Path) -> None:
    report = scan_series_for_voids(empty_csv, max_gap_seconds=3600)
    assert report["void_count"] == 0
    stats = report["value_stats"]
    assert stats["count"] == 0
    assert stats["nan_values"] == 0
    assert stats["min"] is None
    assert stats["max"] is None
    assert stats["mean"] is None
    assert stats["std"] is None


def test_scan_missing_time_column(tmp_path: Path) -> None:
    csv = tmp_path / "bad.csv"
    csv.write_text("t,value\n2026-01-01T00:00:00Z,1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Missing time column"):
        scan_series_for_voids(csv, time_col="timestamp", value_col="value")


def test_scan_missing_value_column(tmp_path: Path) -> None:
    csv = tmp_path / "bad.csv"
    csv.write_text("timestamp,v\n2026-01-01T00:00:00Z,1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Missing value column"):
        scan_series_for_voids(csv, time_col="timestamp", value_col="value")


def test_scan_rejects_unparseable_timestamps(tmp_path: Path) -> None:
    csv = tmp_path / "bad_ts.csv"
    csv.write_text(
        "\n".join(
            [
                "timestamp,value",
                "not-a-date,1.0",
                "2026-01-01T00:10:00Z,1.0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="timestamps could not be parsed"):
        scan_series_for_voids(csv)


def test_scan_counts_nan_values(tmp_path: Path) -> None:
    csv = tmp_path / "nan.csv"
    csv.write_text(
        "\n".join(
            [
                "timestamp,value",
                "2026-01-01T00:00:00Z,1.0",
                "2026-01-01T00:10:00Z,oops",
                "2026-01-01T00:20:00Z,2.0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    report = scan_series_for_voids(csv)
    assert report["value_stats"]["nan_values"] == 1
    assert report["value_stats"]["count"] == 3


@pytest.mark.parametrize("gap_s,expected", [(0, 3), (1, 3), (600, 0)])
def test_gap_threshold_behavior(tmp_path: Path, gap_s: int, expected: int) -> None:
    # If threshold is tiny, all consecutive gaps count as voids (except first row).
    csv = tmp_path / "x.csv"
    csv.write_text(
        "\n".join(
            [
                "timestamp,value",
                "2026-01-01T00:00:00Z,1",
                "2026-01-01T00:10:00Z,2",
                "2026-01-01T00:20:00Z,3",
                "2026-01-01T00:30:00Z,4",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    report = scan_series_for_voids(csv, max_gap_seconds=gap_s)
    assert report["void_count"] == expected
