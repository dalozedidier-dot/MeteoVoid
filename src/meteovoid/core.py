from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import pandas as pd


@dataclass(frozen=True)
class VoidSegment:
    start_ts: str
    end_ts: str
    gap_seconds: int


def _read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".jsonl", ".ndjson"}:
        return pd.read_json(path, lines=True)
    if suffix == ".json":
        return pd.read_json(path)
    if suffix == ".parquet":
        # Requires pyarrow or fastparquet in the environment.
        return pd.read_parquet(path)
    raise ValueError(f"Unsupported input format: {suffix}")


def _parse_timestamps(series: pd.Series[Any]) -> pd.Series[Any]:
    # First: ISO 8601 (handles Z, fractional seconds, etc.).
    ts = pd.to_datetime(series, utc=True, errors="coerce", format="ISO8601")
    if not ts.isna().all():
        return ts

    # Fallback: numeric epoch (s/ms/ns).
    num = pd.to_numeric(series, errors="coerce")
    if num.isna().all():
        return ts

    mx = float(num.max())
    unit: Literal["ns", "ms", "s"]
    if mx > 1e14:
        unit = "ns"
    elif mx > 1e11:
        unit = "ms"
    else:
        unit = "s"

    # IMPORTANT: pass by keyword (arg=...) so mypy matches pandas overloads.
    ts2 = pd.to_datetime(arg=num, utc=True, errors="coerce", unit=unit)
    return ts2


def scan_series_for_voids(
    csv_path: Path,
    time_col: str = "timestamp",
    value_col: str = "value",
    max_gap_seconds: int = 3600,
) -> dict[str, Any]:
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
        "void_count": len(voids),
        "voids": [asdict(v) for v in voids],
        "value_stats": stats,
    }
    return report
