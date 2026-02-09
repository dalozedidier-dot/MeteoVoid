from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def simple_series_csv(tmp_path: Path) -> Path:
    """Small CSV with one intentional gap."""
    p = tmp_path / "series.csv"
    p.write_text(
        "\n".join(
            [
                "timestamp,value",
                "2026-01-01T00:00:00Z,1.0",
                "2026-01-01T00:10:00Z,1.2",
                "2026-01-01T02:45:00Z,1.0",
                "2026-01-01T02:55:00Z,1.3",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture()
def empty_csv(tmp_path: Path) -> Path:
    p = tmp_path / "empty.csv"
    p.write_text("timestamp,value\n", encoding="utf-8")
    return p
