from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import pstdev
from typing import Any, Literal, TypeGuard

import pandas as pd


@dataclass(frozen=True)
class VoidSegment:
    start_ts: str
    end_ts: str
    gap_seconds: int


@dataclass(frozen=True)
class FlatlineSegment:
    start_ts: str
    end_ts: str
    run_length: int
    value: float


def detect_flatline_segments(
    timestamps: list[Any],
    values: list[float | None],
    *,
    eps: float = 1e-6,
    min_run: int = 30,
) -> list[FlatlineSegment]:
    """Detect consecutive values that stagnate abnormally."""
    if min_run < 2:
        min_run = 2
    if not values or len(values) != len(timestamps):
        return []

    eps = abs(float(eps))
    segments: list[FlatlineSegment] = []
    run_start = 0
    run_len = 1

    def _finite(value: float | None) -> TypeGuard[float]:
        return value is not None and value == value

    def _flush(end_index: int) -> None:
        nonlocal run_start, run_len
        if run_len >= int(min_run):
            val = values[run_start]
            if _finite(val):
                segments.append(
                    FlatlineSegment(
                        start_ts=str(timestamps[run_start]),
                        end_ts=str(timestamps[end_index]),
                        run_length=int(run_len),
                        value=float(val),
                    )
                )

    for i in range(1, len(values)):
        prev = values[i - 1]
        cur = values[i]
        if _finite(prev) and _finite(cur) and abs(float(cur) - float(prev)) <= eps:
            run_len += 1
            continue
        _flush(i - 1)
        run_start = i
        run_len = 1

    _flush(len(values) - 1)
    return segments


def interstation_spatial_consistency(
    rows: list[Mapping[str, Any]],
    *,
    station_key: str = "station_id",
    timestamp_key: str = "timestamp",
    value_key: str = "value",
    min_peer_count: int = 3,
    z_threshold: float = 3.0,
) -> dict[str, Any]:
    """Detect station values drifting away from same-timestamp peers."""
    by_time: dict[str, list[tuple[str, float]]] = {}
    for row in rows:
        station = str(row.get(station_key) or "").strip()
        ts = str(row.get(timestamp_key) or "").strip()
        if not station or not ts:
            continue
        raw_value = row.get(value_key)
        if raw_value is None:
            continue
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        by_time.setdefault(ts, []).append((station, value))

    flags: list[dict[str, Any]] = []
    for ts, points in sorted(by_time.items()):
        if len(points) < int(min_peer_count) + 1:
            continue
        for station, value in points:
            peers = [float(v) for sid, v in points if sid != station]
            if len(peers) < int(min_peer_count):
                continue
            peer_mean = float(sum(peers) / len(peers))
            peer_std = float(pstdev(peers))
            if peer_std <= 1e-12:
                z_score = float("inf") if abs(value - peer_mean) > 1e-12 else 0.0
            else:
                z_score = abs(float(value) - peer_mean) / peer_std
            if z_score >= float(z_threshold):
                flags.append(
                    {
                        "timestamp": ts,
                        "station_id": station,
                        "value": float(value),
                        "peer_mean": peer_mean,
                        "peer_std": peer_std,
                        "peer_count": len(peers),
                        "spatial_z": z_score,
                    }
                )

    return {
        "status": "ok",
        "timestamp_count": len(by_time),
        "flag_count": len(flags),
        "flags": flags,
        "z_threshold": float(z_threshold),
        "min_peer_count": int(min_peer_count),
    }


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
    flatline_eps: float = 1e-6,
    flatline_min_run: int = 30,
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
    value_list: list[float | None] = [None if pd.isna(v) else float(v) for v in values.tolist()]
    ts_list = [str(v.isoformat()) for v in df["_ts"].tolist()]
    flatlines = detect_flatline_segments(
        ts_list, value_list, eps=float(flatline_eps), min_run=int(flatline_min_run)
    )

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
        "flatline_eps": float(flatline_eps),
        "flatline_min_run": int(flatline_min_run),
        "flatline_count": len(flatlines),
        "flatlines": [asdict(v) for v in flatlines],
        "value_stats": stats,
    }
    return report
