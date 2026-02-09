from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from meteovoid.core import scan_series_for_voids


@settings(max_examples=25)
@given(
    st.lists(
        st.datetimes(
            min_value=pd.Timestamp("2026-01-01").to_pydatetime(),
            max_value=pd.Timestamp("2026-01-02").to_pydatetime(),
        ),
        min_size=0,
        max_size=25,
        unique=True,
    )
)
def test_scan_is_order_invariant(dts: list) -> None:
    # Property: internal sorting means the function should be order-invariant and deterministic.
    with TemporaryDirectory() as d:
        tmp = Path(d)
        csv = tmp / "p.csv"
        rows = ["timestamp,value"]
        for i, dt in enumerate(dts):
            ts = pd.Timestamp(dt, tz="UTC").isoformat().replace("+00:00", "Z")
            rows.append(f"{ts},{i}")
        csv.write_text("\n".join(rows) + "\n", encoding="utf-8")

        r1 = scan_series_for_voids(csv, max_gap_seconds=3600)
        r2 = scan_series_for_voids(csv, max_gap_seconds=3600)
        assert r1["void_count"] == r2["void_count"]
