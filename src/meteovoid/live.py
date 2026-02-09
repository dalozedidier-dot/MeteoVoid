from __future__ import annotations

import statistics
import time
from typing import Literal, TypedDict


class WindowReport(TypedDict, total=False):
    ts: float
    score: float
    state: Literal["stable", "transition", "unstable"]


def analyze_window(values: list[float]) -> WindowReport:
    if not values:
        return {"score": 0.0, "state": "stable"}

    w = values[-180:]
    score = min(1.0, abs(statistics.pstdev(w)))
    state = "stable" if score < 0.15 else "unstable" if score > 0.30 else "transition"
    return {"ts": time.time(), "score": score, "state": state}
