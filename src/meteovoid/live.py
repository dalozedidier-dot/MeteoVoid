from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from statistics import pstdev
from typing import Any


@dataclass(frozen=True)
class LiveConfig:
    """Runtime configuration for live scoring.

    window_s is a time window in seconds.
    The score is the population standard deviation of values in that window.
    """

    window_s: int = 300
    stable_threshold: float = 0.15
    unstable_threshold: float = 0.30

    # Optional overrides (if None, derived from stable/unstable).
    watch_threshold: float | None = None
    alert_threshold: float | None = None

    def thresholds(self) -> dict[str, float]:
        watch = (
            self.watch_threshold
            if self.watch_threshold is not None
            else (self.stable_threshold + 0.5 * (self.unstable_threshold - self.stable_threshold))
        )
        alert = self.alert_threshold if self.alert_threshold is not None else self.unstable_threshold
        return {
            "stable_threshold": float(self.stable_threshold),
            "watch_threshold": float(watch),
            "unstable_threshold": float(self.unstable_threshold),
            "alert_threshold": float(alert),
        }


class RollingWindow:
    """Keep recent (timestamp, value) pairs within a sliding time window."""

    def __init__(self, window_s: int) -> None:
        self.window_s = int(window_s)
        self._buf: deque[tuple[datetime, float]] = deque()

    def push(self, ts: datetime, value: float) -> None:
        if ts.tzinfo is None:
            # Always store timezone-aware timestamps to avoid subtle bugs.
            ts = ts.replace(tzinfo=UTC)
        self._buf.append((ts, float(value)))

    def samples(self, now: datetime) -> list[tuple[datetime, float]]:
        """Return the samples within the last window_s seconds."""
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


def analyze_window(values: list[float], cfg: LiveConfig) -> dict[str, Any]:
    score = _score(values)
    th = cfg.thresholds()

    if score < th["stable_threshold"]:
        state = "stable"
    elif score < th["unstable_threshold"]:
        state = "transition"
    else:
        state = "unstable"

    flags: list[str] = []
    if score >= th["alert_threshold"]:
        flags.append("alert")
    elif score >= th["watch_threshold"]:
        flags.append("watch")

    interpretation = "Conditions stables."
    severity = "low"
    if state == "transition":
        interpretation = "Variabilité en hausse, surveillance recommandée."
        severity = "medium"
    elif state == "unstable":
        interpretation = "Variabilité forte, alerte recommandée."
        severity = "high"

    return {
        "score": score,
        "state": state,
        "thresholds": th,
        "meteo": {
            "interpretation": interpretation,
            "flags": flags,
            "severity": severity,
            "score_hint": "plus le score est haut, plus la variabilité est forte",
            "state_hint": "stable, transition, unstable",
        },
    }
