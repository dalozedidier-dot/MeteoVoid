from __future__ import annotations

from datetime import UTC, datetime, timedelta

from meteovoid.live import LiveConfig, RollingWindow, analyze_window


def test_analyze_window_transitions() -> None:
    cfg = LiveConfig(window_s=60, stable_threshold=0.05, unstable_threshold=0.20)
    win = RollingWindow(window_s=cfg.window_s)
    now = datetime(2026, 1, 1, tzinfo=UTC)

    # Stable region: constant-ish values
    for i in range(80):
        win.push(now + timedelta(seconds=i), 1.0)
    r1 = analyze_window(win.values(now + timedelta(seconds=80)), cfg)
    assert r1["state"] == "stable"

    # Transition region: small variance
    for i in range(80, 140):
        win.push(now + timedelta(seconds=i), 1.0 + (i % 3) * 0.02)
    r2 = analyze_window(win.values(now + timedelta(seconds=140)), cfg)
    assert r2["state"] in {"stable", "transition"}

    # Unstable: large variance
    for i in range(140, 220):
        win.push(now + timedelta(seconds=i), 0.0 if i % 2 == 0 else 1.0)
    r3 = analyze_window(win.values(now + timedelta(seconds=220)), cfg)
    assert r3["state"] == "unstable"
