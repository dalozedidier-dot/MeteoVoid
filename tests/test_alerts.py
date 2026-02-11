from __future__ import annotations

import os
from typing import Any

import meteovoid.alerts as alerts


class _Resp:
    def __enter__(self):  # noqa: ANN001
        return self

    def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
        return False

    def read(self) -> bytes:
        return b"ok"


def test_maybe_send_alert_noop_without_url(monkeypatch) -> None:
    monkeypatch.delenv("METEOVOID_ALERT_WEBHOOK_URL", raising=False)
    assert alerts.maybe_send_alert({"meteo": {"severity": "high", "flags": ["alert"]}}) is False


def test_maybe_send_alert_posts_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv("METEOVOID_ALERT_WEBHOOK_URL", "http://example.invalid/webhook")
    monkeypatch.setenv("METEOVOID_ALERT_MIN_SEVERITY", "high")

    calls: list[dict[str, Any]] = []

    def fake_urlopen(req, timeout=0):  # noqa: ANN001
        calls.append({"url": req.full_url, "data": req.data, "timeout": timeout})
        return _Resp()

    monkeypatch.setattr(alerts.urllib.request, "urlopen", fake_urlopen)

    ok = alerts.maybe_send_alert({"meteo": {"severity": "high", "flags": []}, "score": 0.9})
    assert ok is True
    assert calls and calls[0]["url"].endswith("/webhook")
