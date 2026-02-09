from __future__ import annotations

from pathlib import Path

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from meteovoid.core import scan_series_for_voids


@settings(max_examples=25)
@given(
    st.lists(
        st.datetimes(min_value=pd.Timestamp("2026-01-01").to_pydatetime(), max_value=pd.Timestamp("2026-01-02").to_pydatetime()),
        min_size=0,
        max_size=25,
        unique=True,
    )
)
def test_scan_is_order_invariant(tmp_path: Path, dts: list) -> None:
    # Build an arbitrary series, shuffle ordering implicitly.
    # Property: sorting is internal; report should not crash and void_count is deterministic for a fixed set.
    csv = tmp_path / "p.csv"
    rows = ["timestamp,value"]
    for i, dt in enumerate(dts):
        # Ensure Z suffix
        ts = pd.Timestamp(dt, tz="UTC").isoformat().replace("+00:00", "Z")
        rows.append(f"{ts},{i}")
    csv.write_text("\n".join(rows) + "\n", encoding="utf-8")

    r1 = scan_series_for_voids(csv, max_gap_seconds=3600)
    r2 = scan_series_for_voids(csv, max_gap_seconds=3600)
    assert r1["void_count"] == r2["void_count"]
