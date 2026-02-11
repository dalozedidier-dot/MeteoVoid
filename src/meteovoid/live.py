from __future__ import annotations

import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, TypedDict

State = Literal["stable", "transition", "unstable"]


class WindowReport(TypedDict, total=False):
    ts: float
    score: float
    state: State


@dataclass(frozen=True, slots=True)
class LiveConfig:
    """Configuration for live scoring.

    window_s: rolling time window size in seconds (used by RollingWindow).
    stable_threshold / unstable_threshold: score thresholds for state labeling.
    max_gap_s: if consecutive samples exceed this gap (in seconds), they count as a data hole.

    impute_mode: none|ffill|mean. Imputation applies only to gaps above max_gap_s.
    use_imputed_for_score: if True, score/state are computed on imputed series when gaps exist.
    max_imputed_frac: if imputed fraction exceeds this, meteo flags should highlight it.
    max_impute_points: safety cap for inserted points per report.
    """

    window_s: int = 180
    stable_threshold: float = 0.15
    unstable_threshold: float = 0.30
    max_gap_s: float = 300.0

    impute_mode: Literal["none", "ffill", "mean"] = "none"
    use_imputed_for_score: bool = False
    max_imputed_frac: float = 0.20
    max_impute_points: int = 500


class RollingWindow:
    """Rolling time-window over (timestamp, value) pairs."""

    def __init__(self, window_s: int = 180) -> None:
        if window_s <= 0:
            raise ValueError("window_s must be > 0")
        self.window_s = window_s
        self._buf: list[tuple[datetime, float]] = []

    def push(self, ts: datetime, value: float) -> None:
        if ts.tzinfo is None:
            raise ValueError
        self._buf.append((ts, value))
        cutoff = ts - timedelta(seconds=float(self.window_s))
        while self._buf and self._buf[0][0] < cutoff:
            self._buf.pop(0)

    def samples(self, now: datetime) -> list[tuple[datetime, float]]:
        cutoff = now - timedelta(seconds=float(self.window_s))
        return [(t, v) for (t, v) in self._buf if t >= cutoff]


def analyze_window(values: list[float], cfg: LiveConfig | None = None) -> WindowReport:
    """Compute a lightweight stability score + state for the last window."""
    if cfg is None:
        cfg = LiveConfig()

    if not values:
        return {"score": 0.0, "state": "stable"}

    # Note: uses cfg.window_s as a max number of points, while RollingWindow uses seconds.
    w = values[-max(1, cfg.window_s) :]
    score = min(1.0, abs(statistics.pstdev(w)))

    state: State
    if score < cfg.stable_threshold:
        state = "stable"
    elif score > cfg.unstable_threshold:
        state = "unstable"
    else:
        state = "transition"

    return {"ts": time.time(), "score": score, "state": state}
