from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from statistics import pstdev
from typing import Any, Literal

State = Literal["stable", "transition", "unstable"]
ImputeMode = Literal["none", "ffill", "mean"]


@dataclass(frozen=True)
class LiveConfig:
    """Configuration for live scoring and gap handling.

    window_s: rolling window size in seconds.
    stable_threshold / unstable_threshold: score thresholds.

    Gap + imputation controls (used in stream.py):
    - max_gap_s: if consecutive points exceed this gap, it's a hole.
    - impute_mode: none|ffill|mean
    - use_imputed_for_score: if True, score/state computed on imputed series.
    - max_imputed_frac: if imputation exceeds this fraction, flag high.
    - max_impute_points: safety cap for inserted points per report.

    Optional:
    - watch_threshold: derived midpoint if None.
    - alert_threshold: equals unstable_threshold if None.
    """

    window_s: int = 300
    stable_threshold: float = 0.15
    unstable_threshold: float = 0.30

    max_gap_s: float = 300.0
    impute_mode: ImputeMode = "none"
    use_imputed_for_score: bool = False
    max_imputed_frac: float = 0.20
    max_impute_points: int = 500

    watch_threshold: float | None = None
    alert_threshold: float | None = None

    def thresholds(self) -> dict[str, float]:
        watch = (
            float(self.watch_threshold)
            if self.watch_threshold is not None
            else float(self.stable_threshold + 0.5 * (self.unstable_threshold - self.stable_threshold))
        )
        alert = (
            float(self.alert_threshold)
            if self.alert_threshold is not None
            else float(self.unstable_threshold)
        )
        return {
            "stable_threshold": float(self.stable_threshold),
            "watch_threshold": float(watch),
            "unstable_threshold": float(self.unstable_threshold),
            "alert_threshold": float(alert),
        }


class RollingWindow:
    """Keep recent (timestamp, value) samples within a sliding time window."""

    def __init__(self, window_s: int) -> None:
        if window_s <= 0:
            raise ValueError("window_s must be > 0")
        self.window_s = int(window_s)
        self._buf: deque[tuple[datetime, float]] = deque()

    def push(self, ts: datetime, value: float) -> None:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        self._buf.append((ts, float(value)))

    def samples(self, now: datetime) -> list[tuple[datetime, float]]:
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        cutoff = now - timedelta(seconds=self.window_s)
        while self._buf and self._buf[0][0] < cutoff:
            self._buf.popleft()
        return list(self._buf)

    def values(self, now: datetime) -> list[float]:
        """Backward-compatible helper expected by tests."""
        return [v for _, v in self.samples(now)]


def _score(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    return float(pstdev(values))


def analyze_window(values: list[float], cfg: LiveConfig | None = None) -> dict[str, Any]:
    """Compute a simple stability score and state."""
    if cfg is None:
        cfg = LiveConfig()

    score = _score(values)
    th = cfg.thresholds()

    if score < th["stable_threshold"]:
        state: State = "stable"
    elif score < th["unstable_threshold"]:
        state = "transition"
    else:
        state = "unstable"

    return {"ts": float(time.time()), "score": float(score), "state": state}
