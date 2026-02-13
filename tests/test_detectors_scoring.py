from __future__ import annotations

from datetime import UTC, datetime, timedelta

from meteovoid.detectors import (
    drift_score,
    flatline_score,
    iqr_outliers,
    pearson_corr,
    robust_zscore_outliers,
    spike_score,
)
from meteovoid.scoring import compute_composite_score


def test_outlier_detectors_flag_extremes() -> None:
    values = [0.0] * 50 + [100.0]
    rz = robust_zscore_outliers(values, z_thresh=3.5)
    iq = iqr_outliers(values, k=1.5)
    assert rz.frac > 0.0 or iq.frac > 0.0
    assert rz.max_score >= 0.0
    assert iq.max_score >= 0.0


def test_flatline_and_spike_scores() -> None:
    flat_vals = [1.0] * 120
    assert flatline_score(flat_vals, eps=1e-9, min_run=30) > 0.0
    assert spike_score(flat_vals) == 0.0

    spike_vals = [0.0] * 10 + [10.0] + [0.0] * 10
    assert spike_score(spike_vals, k=3.0) > 0.0


def test_drift_score_detects_trend() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    samples = [(t0 + timedelta(seconds=i), float(i) * 0.1) for i in range(120)]
    # drift across 120s is ~12 units; expected span 12 -> score close to 1
    d = drift_score(samples=samples, expected_span=12.0, min_points=20)
    assert d > 0.5


def test_pearson_corr() -> None:
    x = list(range(50))
    y = [v * 2 for v in x]
    c = pearson_corr([float(v) for v in x], [float(v) for v in y])
    assert c is not None
    assert c > 0.99


def test_composite_score_is_normalized_and_explainable() -> None:
    t0 = datetime(2026, 2, 1, tzinfo=UTC)
    samples = [(t0 + timedelta(seconds=i * 10), float(i % 2)) for i in range(80)]
    values = [v for _t, v in samples]

    comp = compute_composite_score(
        samples=samples,
        values=values,
        window_s=800,
        missing_time_frac=0.0,
        overrides={"score_weights": {"volatility": 1.0, "gap": 0.0}},
    )
    assert 0.0 <= comp.score <= 1.0
    assert "volatility" in comp.signals
    assert "volatility" in comp.contributions
    assert comp.contributions["volatility"] >= 0.0

    # Spatial + multivar paths
    comp2 = compute_composite_score(
        samples=samples,
        values=values,
        window_s=800,
        missing_time_frac=0.0,
        overrides={"spatial_tol": 0.1, "multivar_min_abs_corr": 0.8},
        peer_median=0.0,
        peer_tol=0.1,
        multivar_peers={"temperature_c": [float(i % 2) for i in range(80)]},
    )
    assert 0.0 <= comp2.score <= 1.0
