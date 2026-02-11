from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from statistics import pstdev
from typing import Any, Literal

State = Literal["stable", "transition", "unstable"]


@dataclass(frozen=True)
class LiveConfig:
    """Configuration for live scoring.

    - window_s: rolling window duration (seconds). Used by RollingWindow.
    - stable_threshold / unstable_threshold: thresholds on the score for state labeling.

    Optional:
    - watch_threshold: if None, derived as midpoint between stable and unstable thresholds.
    - alert_threshold: if None, equals unstable_threshold.
    """

    window_s: int = 300
    stable_threshold: float = 0.15
    unstable_threshold: float = 0.30
    watch_threshold: float | None = None
    alert_threshold: float | None = None

    def thresholds(self) -> dict[str, float]:
        watch = (
            float(self.watch_threshold)
            if self.watch_threshold is not None
            else float(self.stable_threshold + 0.5 * (self.unstable_threshold - self.stable_threshold))
        )
        alert = float(self.alert_threshold) if self.alert_threshold is not None else float(self.unstable_threshold)
        return {
            "stable_threshold": float(self.stable_threshold),
            "watch_threshold": float(watch),
            "unstable_threshold": float(self.unstable_threshold),
            "alert_threshold": float(alert),
        }


class RollingWindow:
    """Keep (timestamp, value) samples inside a sliding time window."""

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
    """Return a minimal scoring report for the given values."""
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

    return {
        "ts": float(time.time()),
        "score": float(score),
        "state": state,
        "thresholds": th,
    }
