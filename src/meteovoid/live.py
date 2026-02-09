from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Deque, Iterable, Tuple

from collections import deque

import numpy as np


def _utc_iso(ts: datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class LiveScoreConfig:
    window_s: int = 1800
    expected_interval_s: int = 60
    stable_threshold: float = 0.15
    unstable_threshold: float = 0.30


@dataclass(frozen=True)
class LiveReport:
    ts: str
    station_id: str
    variable: str
    window_s: int
    score: float
    state: str
    data_points: int
    missing_frac: float
    p95: float | None
    trend: float | None
    explain: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RollingWindow:
    """Stateful rolling buffer of (epoch_seconds, value)."""

    def __init__(self, window_s: int) -> None:
        self.window_s = int(window_s)
        self._buf: Deque[Tuple[float, float]] = deque()

    def add(self, t: float, x: float) -> None:
        self._buf.append((float(t), float(x)))
        self._trim(t)

    def _trim(self, now_t: float) -> None:
        cutoff = float(now_t) - float(self.window_s)
        while self._buf and self._buf[0][0] < cutoff:
            self._buf.popleft()

    def values(self) -> np.ndarray:
        if not self._buf:
            return np.array([], dtype=float)
        return np.array([v for _, v in self._buf], dtype=float)

    def times(self) -> np.ndarray:
        if not self._buf:
            return np.array([], dtype=float)
        return np.array([t for t, _ in self._buf], dtype=float)

    def __len__(self) -> int:
        return len(self._buf)


def compute_live_report(
    *,
    now_ts: datetime,
    station_id: str,
    variable: str,
    window: RollingWindow,
    cfg: LiveScoreConfig,
) -> LiveReport:
    """Compute a simple, robust instability score over the rolling window.

    This is intentionally lightweight and explainable:
      - variance_jump: std(second half) vs std(first half)
      - slope_change: difference of mean derivative (second vs first half)
      - outlier_frac: robust outlier rate via MAD
    """
    xs = window.values()
    ts = window.times()

    n = int(xs.size)
    if n < 10:
        return LiveReport(
            ts=_utc_iso(now_ts),
            station_id=station_id,
            variable=variable,
            window_s=cfg.window_s,
            score=0.0,
            state="insufficient_data",
            data_points=n,
            missing_frac=1.0,
            p95=float(np.nan) if n == 0 else float(np.percentile(xs, 95)),
            trend=float(np.nan) if n < 2 else float((xs[-1] - xs[0]) / max(ts[-1] - ts[0], 1.0)),
            explain={"variance_jump": 0.0, "slope_change": 0.0, "outlier_frac": 0.0},
        )

    # Missing fraction (expected points based on time span)
    span_s = max(float(ts[-1] - ts[0]), 1.0)
    expected = max(int(round(span_s / max(cfg.expected_interval_s, 1))) + 1, 1)
    missing_frac = float(max(expected - n, 0) / expected)

    # Split halves
    mid = n // 2
    x1, x2 = xs[:mid], xs[mid:]
    t1, t2 = ts[:mid], ts[mid:]

    eps = 1e-9
    std1 = float(np.std(x1) + eps)
    std2 = float(np.std(x2) + eps)
    variance_jump = float(np.clip((std2 / std1 - 1.0) / 2.0, 0.0, 1.0))

    # Trend / slope change (mean derivative)
    def mean_derivative(t: np.ndarray, x: np.ndarray) -> float:
        dt = np.diff(t)
        dx = np.diff(x)
        dt = np.where(dt == 0, 1.0, dt)
        return float(np.mean(dx / dt))

    d1 = mean_derivative(t1, x1) if x1.size >= 3 else 0.0
    d2 = mean_derivative(t2, x2) if x2.size >= 3 else 0.0
    slope_change = float(np.clip(abs(d2 - d1) / (std1 + std2 + eps), 0.0, 1.0))

    # Robust outliers via MAD
    med = float(np.median(xs))
    mad = float(np.median(np.abs(xs - med)) + eps)
    z = np.abs(xs - med) / (1.4826 * mad + eps)
    outlier_frac = float(np.clip(np.mean(z > 3.5), 0.0, 1.0))

    score = float(np.clip(0.50 * variance_jump + 0.30 * slope_change + 0.20 * outlier_frac, 0.0, 1.0))

    if score < cfg.stable_threshold:
        state = "stable"
    elif score >= cfg.unstable_threshold:
        state = "unstable"
    else:
        state = "transition"

    trend = float((xs[-1] - xs[0]) / max(ts[-1] - ts[0], 1.0))
    p95 = float(np.percentile(xs, 95))

    return LiveReport(
        ts=_utc_iso(now_ts),
        station_id=station_id,
        variable=variable,
        window_s=cfg.window_s,
        score=score,
        state=state,
        data_points=n,
        missing_frac=missing_frac,
        p95=p95,
        trend=trend,
        explain={
            "variance_jump": variance_jump,
            "slope_change": slope_change,
            "outlier_frac": outlier_frac,
        },
    )
