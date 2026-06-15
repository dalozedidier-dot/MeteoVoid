from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for candidate in (PROJECT_ROOT, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


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
