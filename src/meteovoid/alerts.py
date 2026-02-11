from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Mapping


def _severity_rank(sev: str) -> int:
    order = {"low": 0, "medium": 1, "high": 2}
    return order.get(sev, 0)


def maybe_send_alert(report: Mapping[str, Any]) -> bool:
    """Send an alert via webhook when severity is high or flag 'alert' appears.

    Controlled by env vars:
    - METEOVOID_ALERT_WEBHOOK_URL: if empty -> no-op
    - METEOVOID_ALERT_MIN_SEVERITY: default 'high'
    - METEOVOID_ALERT_ALWAYS_ON_FLAG: default 'alert'
    """
    url = os.getenv("METEOVOID_ALERT_WEBHOOK_URL", "").strip()
    if not url:
        return False

    meteo = report.get("meteo", {})
    if not isinstance(meteo, dict):
        return False

    flags = meteo.get("flags", [])
    if not isinstance(flags, list):
        flags = []

    severity = str(meteo.get("severity", "low"))
    min_sev = os.getenv("METEOVOID_ALERT_MIN_SEVERITY", "high").strip() or "high"
    flag_name = os.getenv("METEOVOID_ALERT_ALWAYS_ON_FLAG", "alert").strip() or "alert"

    should_by_sev = _severity_rank(severity) >= _severity_rank(min_sev)
    should_by_flag = flag_name in [str(x) for x in flags]

    if not (should_by_sev or should_by_flag):
        return False

    payload = json.dumps(dict(report), separators=(",", ":"), sort_keys=True).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "MeteoVoid/alerts"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
            _ = resp.read()
        return True
    except Exception:
        # Fail-silent: alerts must never crash the worker
        return False
