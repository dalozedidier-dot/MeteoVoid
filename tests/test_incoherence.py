from __future__ import annotations

from meteovoid.incoherence import IncoherenceConfig, compute_incoherence_from_latest


def test_incoherence_gap_only() -> None:
    cfg = IncoherenceConfig(
        variables={
            "__default__": {"weights": {"gap": 1.0, "range": 0.0, "stuck": 0.0}},
        },
        severity={"medium": 0.2, "high": 0.4},
    )
    latest = {"variable": "x", "stats": {"missing_time_frac": 0.3, "n_points": 250}}
    inco = compute_incoherence_from_latest(latest=latest, cfg=cfg)
    assert abs(float(inco["score"]) - 0.3) < 1e-9
    assert inco["severity"] == "medium"


def test_incoherence_range_exceed() -> None:
    cfg = IncoherenceConfig(
        variables={
            "wind_gust_ms": {
                "range": {"min": 0.0, "max": 10.0},
                "weights": {"gap": 0.0, "range": 1.0, "stuck": 0.0},
            }
        },
        severity={"medium": 0.2, "high": 0.4},
    )
    latest = {
        "variable": "wind_gust_ms",
        "stats": {"min": -5.0, "max": 15.0, "missing_time_frac": 0.0, "n_points": 250},
    }
    inco = compute_incoherence_from_latest(latest=latest, cfg=cfg)
    # Exceedance: below 0 by 5/10 = 0.5, above 10 by 5/10 = 0.5 -> 1.0 clamp
    assert abs(float(inco["components"]["range"]) - 1.0) < 1e-9
    assert inco["severity"] == "high"


def test_incoherence_stuck_range() -> None:
    cfg = IncoherenceConfig(
        variables={
            "temperature_c": {
                "stuck": {"eps_range": 1.0, "min_points": 30},
                "weights": {"gap": 0.0, "range": 0.0, "stuck": 1.0},
            }
        },
        severity={"medium": 0.2, "high": 0.4},
    )
    latest = {
        "variable": "temperature_c",
        "stats": {"min": 10.0, "max": 10.0, "missing_time_frac": 0.0, "n_points": 250},
    }
    inco = compute_incoherence_from_latest(latest=latest, cfg=cfg)
    assert abs(float(inco["components"]["stuck"]) - 1.0) < 1e-9
    assert inco["severity"] == "high"
