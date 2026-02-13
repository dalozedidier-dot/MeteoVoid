from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import pstdev
from typing import Any

from .detectors import (
    clamp01,
    drift_score,
    expected_span_from_values,
    flatline_score,
    iqr_outliers,
    normalize_ratio,
    pearson_corr,
    robust_zscore_outliers,
    spike_score,
)


@dataclass(frozen=True)
class CompositeScore:
    score: float
    signals: dict[str, float]
    weights: dict[str, float]
    contributions: dict[str, float]
    meta: dict[str, Any]


def _weights_from_overrides(overrides: dict[str, Any]) -> dict[str, float]:
    # Default weights: sum is normalized away.
    weights: dict[str, float] = {
        "gap": 0.25,
        "volatility": 0.25,
        "outlier": 0.15,
        "flatline": 0.10,
        "spike": 0.10,
        "drift": 0.10,
        "spatial": 0.03,
        "multivar": 0.02,
    }
    w_any = overrides.get("score_weights")
    if isinstance(w_any, dict):
        for k, v in w_any.items():
            if isinstance(k, str) and k and isinstance(v, int | float):
                weights[k] = float(v)
    return weights


def compute_composite_score(
    *,
    samples: list[tuple[datetime, float]],
    values: list[float],
    window_s: int,
    missing_time_frac: float,
    overrides: dict[str, Any],
    peer_median: float | None = None,
    peer_tol: float | None = None,
    multivar_peers: dict[str, list[float]] | None = None,
) -> CompositeScore:
    """Compute a normalized composite stability/anomaly score in [0..1].

    This is intentionally lightweight and dependency-free.

    Signals (each in [0..1]):
      - gap: missing_time_frac
      - volatility: robust std normalized to expected span
      - outlier: max(robust-z outlier frac, IQR outlier frac, business-rule violations)
      - flatline: consecutive identical values
      - spike: abrupt first-difference jumps
      - drift: trend across the window
      - spatial: deviation from peer median
      - multivar: correlation breaking vs peers (if provided)
    """
    weights = _weights_from_overrides(overrides)

    # Normalization scale
    span = float(overrides.get("expected_span") or 0.0)
    if not (span > 0.0):
        # Optional expected range
        r_any = overrides.get("expected_range")
        if isinstance(r_any, dict):
            lo = r_any.get("min")
            hi = r_any.get("max")
            if (
                isinstance(lo, int | float)
                and isinstance(hi, int | float)
                and float(hi) > float(lo)
            ):
                span = float(hi) - float(lo)

    if not (span > 0.0):
        span = expected_span_from_values(values)

    # Volatility proxy: robust-z MAD sigma, then normalize via ratio.
    z = robust_zscore_outliers(values, z_thresh=float(overrides.get("outlier_z_thresh", 3.5)))
    # sigma estimate in details when available
    sigma = float(z.details.get("sigma", 0.0)) if isinstance(z.details, dict) else 0.0
    if sigma <= 0.0 and len(values) >= 2:
        # Fallback: use standard deviation. This keeps constant windows at sigma=0.
        sigma = float(pstdev(values))

    vol_ref = float(overrides.get("volatility_ref", max(1e-9, span * 0.10)))
    volatility = normalize_ratio(sigma, vol_ref)

    # Outliers
    iqr = iqr_outliers(values, k=float(overrides.get("outlier_iqr_k", 1.5)))
    outlier = float(max(z.frac, iqr.frac))

    # Business rules, if configured
    hard_min = overrides.get("hard_min")
    hard_max = overrides.get("hard_max")
    violations = 0
    if isinstance(hard_min, int | float):
        violations += sum(1 for v in values if v < float(hard_min))
    if isinstance(hard_max, int | float):
        violations += sum(1 for v in values if v > float(hard_max))
    if violations > 0 and values:
        outlier = clamp01(max(outlier, float(violations / len(values))))

    # Flatline
    flat = flatline_score(
        values,
        eps=float(overrides.get("flatline_eps", 1e-6)),
        min_run=int(overrides.get("flatline_min_run", 30)),
    )

    # Spikes
    spike = spike_score(values, k=float(overrides.get("spike_k", 6.0)))

    # Drift
    drift = drift_score(
        samples=samples, expected_span=span, min_points=int(overrides.get("drift_min_points", 20))
    )

    # Spatial
    spatial = 0.0
    if peer_median is not None:
        tol = (
            float(peer_tol)
            if peer_tol is not None
            else float(overrides.get("spatial_tol", 0.0) or 0.0)
        )
        if tol <= 1e-12:
            tol = float(max(1e-9, span * 0.25))
        mean = float(sum(values) / max(1, len(values))) if values else 0.0
        spatial = clamp01(abs(mean - float(peer_median)) / tol)

    # Multi-variable correlation
    multivar = 0.0
    if multivar_peers:
        min_abs = float(overrides.get("multivar_min_abs_corr", 0.25))
        worst = 0.0
        for _name, peer_vals in multivar_peers.items():
            c = pearson_corr(values, peer_vals)
            if c is None:
                continue
            dev = max(0.0, min_abs - abs(float(c)))
            worst = max(worst, float(dev / max(min_abs, 1e-9)))
        multivar = clamp01(worst)

    signals = {
        "gap": clamp01(float(missing_time_frac)),
        "volatility": float(volatility),
        "outlier": float(outlier),
        "flatline": float(flat),
        "spike": float(spike),
        "drift": float(drift),
        "spatial": float(spatial),
        "multivar": float(multivar),
    }

    # Weighted sum -> normalize.
    wsum = float(sum(max(0.0, float(w)) for w in weights.values()))
    if wsum <= 1e-12:
        wsum = 1.0
        weights = {"volatility": 1.0}

    score = 0.0
    contributions: dict[str, float] = {}
    for k, s in signals.items():
        w = max(0.0, float(weights.get(k, 0.0)))
        c = float(w * float(s))
        score += c
        contributions[k] = c

    score = clamp01(float(score / wsum))

    # Normalize contributions to sum to score (optional, helps explain).
    if score > 0.0:
        csum = float(sum(contributions.values()))
        if csum > 1e-12:
            for k in list(contributions.keys()):
                contributions[k] = float(score * (contributions[k] / csum))

    meta: dict[str, Any] = {
        "span": float(span),
        "window_s": int(window_s),
        "outlier_methods": {
            "robust_z": {"frac": float(z.frac), "max_z": float(z.max_score)},
            "iqr": {"frac": float(iqr.frac), "max_score": float(iqr.max_score)},
        },
        "volatility": {"sigma_est": float(sigma), "ref": float(vol_ref)},
    }
    return CompositeScore(
        score=float(score),
        signals=signals,
        weights={k: float(v) for k, v in weights.items()},
        contributions={k: float(v) for k, v in contributions.items()},
        meta=meta,
    )
