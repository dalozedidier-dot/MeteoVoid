from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from math import sqrt
from typing import Any


def clamp01(x: float) -> float:
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    return float(x)


def safe_float(x: Any) -> float | None:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


@dataclass(frozen=True)
class OutlierResult:
    frac: float
    max_score: float
    method: str
    details: dict[str, Any]


def _median(xs: list[float]) -> float:
    if not xs:
        return 0.0
    ys = sorted(xs)
    n = len(ys)
    mid = n // 2
    if n % 2 == 1:
        return float(ys[mid])
    return float((ys[mid - 1] + ys[mid]) / 2.0)


def _mad(xs: list[float], med: float) -> float:
    if not xs:
        return 0.0
    dev = [abs(x - med) for x in xs]
    return _median(dev)


def robust_zscore_outliers(values: list[float], z_thresh: float = 3.5) -> OutlierResult:
    """Robust outlier fraction via median + MAD (approx sigma=1.4826*MAD).

    Returns:
      frac: fraction of points flagged
      max_score: max |z| observed
    """
    if len(values) < 5:
        return OutlierResult(frac=0.0, max_score=0.0, method="robust_z", details={})

    med = _median(values)
    mad = _mad(values, med)

    # If MAD=0 but not all values equal, we still want to flag non-median points.
    # This happens with "mostly constant + one extreme" patterns, which are meaningful anomalies.
    if mad <= 1e-12:
        non_med = [x for x in values if abs(x - med) > 1e-12]
        frac = float(len(non_med) / len(values)) if values else 0.0
        return OutlierResult(
            frac=clamp01(frac),
            max_score=1.0 if non_med else 0.0,
            method="robust_z",
            details={"median": med, "mad": mad, "fallback": "non_median"},
        )

    sigma = 1.4826 * mad
    zs = [abs((x - med) / sigma) for x in values]
    flagged = [z for z in zs if z >= float(z_thresh)]
    frac = float(len(flagged) / len(values))
    return OutlierResult(
        frac=clamp01(frac),
        max_score=float(max(zs)) if zs else 0.0,
        method="robust_z",
        details={"median": med, "mad": mad, "sigma": sigma, "z_thresh": float(z_thresh)},
    )


def iqr_outliers(values: list[float], k: float = 1.5) -> OutlierResult:
    """Outlier fraction using Tukey IQR fences."""
    if len(values) < 8:
        return OutlierResult(frac=0.0, max_score=0.0, method="iqr", details={})

    xs = sorted(values)
    n = len(xs)
    q1 = xs[int(0.25 * (n - 1))]
    q3 = xs[int(0.75 * (n - 1))]
    iqr = float(q3 - q1)

    # If IQR=0 but not all values equal, flag points that differ from the quartiles.
    if iqr <= 1e-12:
        non_q = [x for x in values if abs(x - float(q1)) > 1e-12]
        frac = float(len(non_q) / len(values)) if values else 0.0
        return OutlierResult(
            frac=clamp01(frac),
            max_score=1.0 if non_q else 0.0,
            method="iqr",
            details={"q1": float(q1), "q3": float(q3), "iqr": iqr, "fallback": "non_quartile"},
        )

    lo = float(q1 - float(k) * iqr)
    hi = float(q3 + float(k) * iqr)
    flagged = [x for x in values if x < lo or x > hi]
    frac = float(len(flagged) / len(values))

    # "max_score" is normalized distance beyond fence
    dist = 0.0
    for x in flagged:
        if x < lo:
            dist = max(dist, float((lo - x) / iqr))
        else:
            dist = max(dist, float((x - hi) / iqr))

    return OutlierResult(
        frac=clamp01(frac),
        max_score=float(dist),
        method="iqr",
        details={"q1": float(q1), "q3": float(q3), "iqr": iqr, "k": float(k), "lo": lo, "hi": hi},
    )


def flatline_score(values: list[float], eps: float = 1e-6, min_run: int = 30) -> float:
    """Return a [0..1] score for abnormal flatlining.

    We detect the longest run of consecutive values whose absolute step <= eps.
    Score = clamp01((run_len - min_run + 1) / len(values)) if run_len >= min_run else 0.
    """
    if len(values) < max(2, int(min_run)):
        return 0.0

    eps = float(abs(eps))
    best = 1
    run = 1

    for i in range(1, len(values)):
        if abs(values[i] - values[i - 1]) <= eps:
            run += 1
        else:
            if run > best:
                best = run
            run = 1

    if run > best:
        best = run

    if best < int(min_run):
        return 0.0

    raw = float((best - int(min_run) + 1) / float(max(1, len(values))))
    return clamp01(raw)


def spike_score(values: list[float], k: float = 6.0) -> float:
    """Return a [0..1] score for abrupt spikes/step changes.

    We compute robust scale of first differences via MAD, then count diffs exceeding k*sigma.
    If the robust scale collapses (MAD=0) but diffs contain non-zero jumps, we treat that as a spike.
    """
    if len(values) < 6:
        return 0.0

    diffs = [float(values[i] - values[i - 1]) for i in range(1, len(values))]
    med = _median(diffs)
    mad = _mad(diffs, med)

    # Common "one spike in otherwise constant series" pattern -> MAD==0, but it's still a spike.
    if mad <= 1e-12:
        has_jump = any(abs(d - med) > 1e-12 for d in diffs)
        return 1.0 if has_jump else 0.0

    sigma = 1.4826 * mad
    thr = float(abs(k)) * sigma
    flagged = [d for d in diffs if abs(d - med) >= thr]
    return clamp01(float(len(flagged) / len(diffs)))


def drift_score(
    *,
    samples: list[tuple[datetime, float]],
    expected_span: float,
    min_points: int = 20,
) -> float:
    """Return a [0..1] score for slow drift (trend) across the window.

    Uses a lightweight linear regression slope vs time and normalizes by expected_span.
    expected_span should be >0: typical range for the variable in the current window.
    """
    if len(samples) < int(min_points):
        return 0.0

    t0 = samples[0][0]
    if t0.tzinfo is None:
        t0 = t0.replace(tzinfo=UTC)

    xs: list[float] = []
    ys: list[float] = []
    for t, v in samples:
        if t.tzinfo is None:
            t = t.replace(tzinfo=UTC)
        xs.append(float((t - t0).total_seconds()))
        ys.append(float(v))

    # Compute slope (least squares) with numerically stable formula.
    n = float(len(xs))
    mx = float(sum(xs) / n)
    my = float(sum(ys) / n)

    sxx = float(sum((x - mx) ** 2 for x in xs))
    if sxx <= 1e-12:
        return 0.0

    sxy = float(sum((xs[i] - mx) * (ys[i] - my) for i in range(len(xs))))
    slope = float(sxy / sxx)  # units: value per second

    # Normalize drift across the window to [0..1].
    span = float(abs(expected_span))
    if span <= 1e-12:
        span = float(max(1e-9, abs(my), 1.0))

    window_s = float(max(xs) - min(xs))
    drift_abs = abs(slope) * window_s
    return clamp01(float(drift_abs / span))


def expected_span_from_values(values: list[float]) -> float:
    """Estimate a typical range for normalization.

    Uses p95 - p05 to avoid single outliers inflating the span.
    """
    if len(values) < 8:
        if not values:
            return 1.0
        return float(max(values) - min(values)) or 1.0

    xs = sorted(values)
    n = len(xs)
    p05 = xs[int(0.05 * (n - 1))]
    p95 = xs[int(0.95 * (n - 1))]
    span = float(p95 - p05)
    if span <= 1e-12:
        span = float(max(xs) - min(xs))
    return span if span > 1e-12 else 1.0


def normalize_ratio(raw: float, ref: float) -> float:
    """Map a non-negative quantity to [0..1) via raw/(raw+ref)."""
    raw = max(0.0, float(raw))
    ref = max(1e-12, float(ref))
    return clamp01(float(raw / (raw + ref)))


def pearson_corr(x: list[float], y: list[float]) -> float | None:
    """Return Pearson correlation in [-1..1], or None if not computable."""
    n = min(len(x), len(y))
    if n < 6:
        return None

    xx = x[-n:]
    yy = y[-n:]

    mx = sum(xx) / n
    my = sum(yy) / n
    vx = sum((v - mx) ** 2 for v in xx)
    vy = sum((v - my) ** 2 for v in yy)
    if vx <= 1e-12 or vy <= 1e-12:
        return None

    cov = sum((xx[i] - mx) * (yy[i] - my) for i in range(n))
    return float(cov / sqrt(vx * vy))
