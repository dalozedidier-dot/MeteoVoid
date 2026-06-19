from __future__ import annotations

import json
from pathlib import Path

from meteovoid.core import scan_series_for_voids

csv_path = Path("examples/sample_timeseries.csv")
report = scan_series_for_voids(csv_path, max_gap_seconds=3600, flatline_min_run=5)
print(json.dumps(report, indent=2, ensure_ascii=False))
