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


def _read_table(path: Path) -> pd.DataFrame:
    suf = path.suffix.lower()
    if suf == ".csv":
        return pd.read_csv(path)
    if suf in {".parquet", ".pq"}:
        return pd.read_parquet(path)  # requires pyarrow or fastparquet
    if suf in {".jsonl", ".ndjson"}:
        return pd.read_json(path, lines=True)
    if suf == ".json":
        return pd.read_json(path)
    raise ValueError(f"Unsupported input format: {path.name}")


def _parse_timestamps(col: pd.Series) -> pd.Series:
    """Parse timestamps robustly.

    Pandas has edge cases parsing ISO8601 strings with fractional seconds + timezone (e.g. ...000001Z).
    We first try format="ISO8601" (fast + robust for the common case), then fall back.
    """
    # 1) ISO8601 (handles microseconds + 'Z' reliably)
    ts = pd.to_datetime(col, utc=True, errors="coerce", format="ISO8601")

    # 2) Fallback: generic parser (mixed inputs)
    if ts.isna().any():
        ts2 = pd.to_datetime(col, utc=True, errors="coerce")
        ts = ts.fillna(ts2)

    # 3) Fallback for numeric epochs (seconds/ms/ns heuristic)
    if ts.isna().any():
        num = pd.to_numeric(col, errors="coerce")
        if num.notna().any():
            mx = float(num.max())
            # Heuristic: choose the most likely unit by magnitude.
            if mx > 1e14:
                unit = "ns"
            elif mx > 1e11:
                unit = "ms"
            else:
                unit = "s"
            ts3 = pd.to_datetime(num, utc=True, errors="coerce", unit=unit)
            ts = ts.fillna(ts3)

    return ts


def scan_series_for_voids(
    csv_path: Path,
    time_col: str = "timestamp",
    value_col: str = "value",
    max_gap_seconds: int = 3600,
) -> dict[str, Any]:
    """Detect void segments (large gaps) in a time series file.

    Supported inputs:
      - CSV (.csv)
      - Parquet (.parquet, .pq) if pyarrow/fastparquet is installed
      - JSON Lines (.jsonl, .ndjson)
      - JSON (.json)

    The output schema remains stable for CI + reproducibility.
    """
    df = _read_table(csv_path)
    if time_col not in df.columns:
        raise ValueError(f"Missing time column: {time_col}")
    if value_col not in df.columns:
        raise ValueError(f"Missing value column: {value_col}")

    ts = _parse_timestamps(df[time_col])
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
        "void_count": int(len(voids)),
        "voids": [asdict(v) for v in voids],
        "value_stats": stats,
    }
    return report
