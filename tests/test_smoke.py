from __future__ import annotations

import json
from pathlib import Path

from meteovoid.core import scan_series_for_voids


def test_scan_series_for_voids(tmp_path: Path) -> None:
    csv = tmp_path / "x.csv"
    csv.write_text(
        "\n".join(
            [
                "timestamp,value",
                "2026-01-01T00:00:00Z,1",
                "2026-01-01T00:10:00Z,2",
                "2026-01-01T02:30:00Z,3",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    report = scan_series_for_voids(csv, max_gap_seconds=3600)
    assert report["void_count"] == 1
    # JSON serializable
    json.dumps(report)
