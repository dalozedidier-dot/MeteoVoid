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

    Scores are normalized to [0..1]. Thresholds are therefore expressed in [0..1].
    """

    window_s: int = 300
    stable_threshold: float = 0.15
    unstable_threshold: float = 0.30

    # Volatility normalization (used by analyze_window only).
    # The score is std / (std + volatility_ref). Default is 1.0.
    volatility_ref: float = 1.0

    # Gap + imputation controls (used by stream.py)
    max_gap_s: float = 300.0
    impute_mode: ImputeMode = "none"
    use_imputed_for_score: bool = False
    max_imputed_frac: float = 0.20
    max_impute_points: int = 500

    # Optional overrides (if None, derived).
    watch_threshold: float | None = None
    alert_threshold: float | None = None

    def thresholds(self) -> dict[str, float]:
        watch = (
            float(self.watch_threshold)
            if self.watch_threshold is not None
            else float(
                self.stable_threshold + 0.5 * (self.unstable_threshold - self.stable_threshold)
            )
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
    """Keep (timestamp, value) samples within a sliding time window."""

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


def _clamp01(x: float) -> float:
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    return float(x)


def _score(values: list[float], volatility_ref: float) -> float:
    """Normalized volatility score in [0..1]."""
    if len(values) < 2:
        return 0.0
    std = float(pstdev(values))
    ref = float(volatility_ref) if float(volatility_ref) > 0.0 else 1.0
    return _clamp01(float(std / (std + ref)))


def analyze_window(values: list[float], cfg: LiveConfig | None = None) -> dict[str, Any]:
    """Compute a simple normalized stability score and state.

    This function is intentionally lightweight and kept for backwards compatibility.
    The live worker uses a richer composite score implemented in stream.py.
    """
    if cfg is None:
        cfg = LiveConfig()

    score = _score(values, cfg.volatility_ref)
    th = cfg.thresholds()

    if score < th["stable_threshold"]:
        state: State = "stable"
    elif score < th["unstable_threshold"]:
        state = "transition"
    else:
        state = "unstable"

    return {"ts": float(time.time()), "score": float(score), "state": state}
