from __future__ import annotations

from meteovoid.detectors import iqr_outliers, robust_zscore_outliers, spike_score


def test_outliers_when_scale_is_zero() -> None:
    # Mostly constant series: MAD and IQR are 0, but the final point is a true extreme.
    values = [0.0] * 50 + [100.0]
    rz = robust_zscore_outliers(values, z_thresh=3.5)
    iq = iqr_outliers(values, k=1.5)
    assert rz.frac > 0.0
    assert iq.frac > 0.0


def test_spike_when_diff_scale_is_zero() -> None:
    # Diffs have MAD=0 because most diffs are 0, but there is a clear step change.
    spike_vals = [0.0] * 10 + [10.0] + [0.0] * 10
    assert spike_score(spike_vals, k=3.0) > 0.0
