from __future__ import annotations

from datetime import datetime, timezone

from meteovoid.live import LiveScoreConfig, RollingWindow, compute_live_report


def test_live_report_states_progress() -> None:
    cfg = LiveScoreConfig(window_s=600, expected_interval_s=60)

    win = RollingWindow(window_s=cfg.window_s)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    # Stable region
    for i in range(60):
        win.add((now.timestamp() - 600) + i * 10, 10.0 + (i % 3) * 0.1)
    rep = compute_live_report(now_ts=now, station_id="S", variable="v", window=win, cfg=cfg)
    assert rep.state in {"stable", "transition"}

    # Add volatile tail -> should move toward transition/unstable
    for i in range(30):
        win.add(now.timestamp() + i * 10, 10.0 + (i % 2) * 6.0)
    rep2 = compute_live_report(now_ts=now, station_id="S", variable="v", window=win, cfg=cfg)
    assert rep2.score >= rep.score
