from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class VoidSegment:
    start_ts: str
    end_ts: str
    gap_seconds: int


def scan_series_for_voids(
    csv_path: Path,
    time_col: str = "timestamp",
    value_col: str = "value",
    max_gap_seconds: int = 3600,
) -> dict[str, Any]:
    df = pd.read_csv(csv_path)
    if time_col not in df.columns:
        raise ValueError(f"Missing time column: {time_col}")
    if value_col not in df.columns:
        raise ValueError(f"Missing value column: {value_col}")

    ts = pd.to_datetime(df[time_col], utc=True, errors="coerce", format="ISO8601")
    if ts.isna().any():
        bad = int(ts.isna().sum())
        raise ValueError(f"{bad} timestamps could not be parsed in column {time_col}")

    df = df.assign(_ts=ts).sort_values("_ts").reset_index(drop=True)
    diffs = df["_ts"].diff().dt.total_seconds().fillna(0).astype(int)

    voids: list[VoidSegment] = []
    for i in range(1, len(df)):
        gap = int(diffs.iloc[i])
        if gap > max_gap_seconds:
            voids.append(
                VoidSegment(
                    start_ts=df["_ts"].iloc[i - 1].isoformat(),
                    end_ts=df["_ts"].iloc[i].isoformat(),
                    gap_seconds=gap,
                )
            )

    # Simple anomaly proxies
    values = pd.to_numeric(df[value_col], errors="coerce")
    n_nan = int(values.isna().sum())
    finite = values.dropna()
    stats = {
        "count": int(len(values)),
        "nan_values": n_nan,
        "min": float(finite.min()) if not finite.empty else None,
        "max": float(finite.max()) if not finite.empty else None,
        "mean": float(finite.mean()) if not finite.empty else None,
        "std": float(finite.std(ddof=0)) if not finite.empty else None,
    }

    report = {
        "input": str(csv_path),
        "time_col": time_col,
        "value_col": value_col,
        "max_gap_seconds": int(max_gap_seconds),
        "void_count": len(voids),
        "voids": [asdict(v) for v in voids],
        "value_stats": stats,
    }
    return report
