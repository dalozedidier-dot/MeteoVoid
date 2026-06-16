#!/usr/bin/env python3
"""Patch MeteoVoid Belgium alert_state contract fields.

Run from the repository root. This script modifies only:
  tools/generate_belgium_alert_report.py

It adds the contract fields required by src/meteovoid/belgium/contracts.py:
  - notification_allowed
  - public_wording
  - official_alert

It keeps public_alert_allowed for backward compatibility.
"""
from __future__ import annotations

from pathlib import Path

TARGET = Path("tools/generate_belgium_alert_report.py")

INSERT_ANCHOR = '''    if trend_status in {"rising", "rising_fast"} and level in {"watch", "watch_reinforced"}:
        reason = f"{reason}. Tendance en hausse"
    return {
'''

INSERT_REPLACEMENT = '''    if trend_status in {"rising", "rising_fast"} and level in {"watch", "watch_reinforced"}:
        reason = f"{reason}. Tendance en hausse"

    notification_allowed = level in {
        "watch_reinforced",
        "pre_alert_confirmed",
        "alert_confirmed",
    }
    public_wording_by_level = {
        "normal": "veille météo technique normale, non officielle",
        "low_watch": "surveillance météo technique faible, non officielle",
        "watch": "veille météo technique, non officielle",
        "watch_reinforced": "veille renforcée technique, non officielle",
        "pre_alert_confirmed": "pré-alerte technique confirmée, non officielle",
        "alert_confirmed": "alerte technique confirmée, non officielle",
    }
    public_wording = public_wording_by_level.get(
        level,
        "veille météo technique non officielle",
    )
    official_alert = False

    return {
'''

FIELD_ANCHOR = '''        "trend_status": trend_status,
        "public_alert_allowed": level in {"pre_alert_confirmed", "alert_confirmed"},
        "public_alert_caution": "Ne jamais publier comme alerte officielle. Comparer avec IRM/KMI, MeteoAlarm, radar et foudre.",
'''

FIELD_REPLACEMENT = '''        "trend_status": trend_status,
        "notification_allowed": notification_allowed,
        "public_wording": public_wording,
        "official_alert": official_alert,
        "public_alert_allowed": level in {"pre_alert_confirmed", "alert_confirmed"},
        "public_alert_caution": "Ne jamais publier comme alerte officielle. Comparer avec IRM/KMI, MeteoAlarm, radar et foudre.",
'''

NOTIFICATION_ANCHOR = '''        "reason": reason,
        "public_alert_allowed": bool(operational.get("public_alert_allowed", False)),
        "message_title": "MeteoVoid Belgique - veille météo",
'''

NOTIFICATION_REPLACEMENT = '''        "reason": reason,
        "notification_allowed": bool(operational.get("notification_allowed", should_notify)),
        "public_wording": str(
            operational.get("public_wording", "veille météo technique non officielle")
        ),
        "official_alert": bool(operational.get("official_alert", False)),
        "public_alert_allowed": bool(operational.get("public_alert_allowed", False)),
        "message_title": "MeteoVoid Belgique - veille météo",
'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count == 0:
        if label == "operational variables" and "notification_allowed = level in" in text:
            return text
        if label == "alert_state fields" and '"notification_allowed": notification_allowed' in text:
            return text
        if label == "notification_state fields" and '"notification_allowed": bool(operational.get("notification_allowed", should_notify))' in text:
            return text
        raise SystemExit(f"Could not find patch anchor for {label}.")
    if count > 1:
        raise SystemExit(f"Patch anchor for {label} appears {count} times; refusing ambiguous edit.")
    return text.replace(old, new, 1)


def main() -> int:
    if not TARGET.exists():
        raise SystemExit(f"Missing target file: {TARGET}")

    text = TARGET.read_text(encoding="utf-8")
    original = text
    text = replace_once(text, INSERT_ANCHOR, INSERT_REPLACEMENT, "operational variables")
    text = replace_once(text, FIELD_ANCHOR, FIELD_REPLACEMENT, "alert_state fields")
    text = replace_once(text, NOTIFICATION_ANCHOR, NOTIFICATION_REPLACEMENT, "notification_state fields")

    if text == original:
        print("No change needed; contract fields already appear to be present.")
    else:
        TARGET.write_text(text, encoding="utf-8")
        print(f"Patched {TARGET}")

    final = TARGET.read_text(encoding="utf-8")
    required = [
        '"notification_allowed": notification_allowed',
        '"public_wording": public_wording',
        '"official_alert": official_alert',
    ]
    missing = [item for item in required if item not in final]
    if missing:
        raise SystemExit(f"Patch verification failed, missing: {missing}")
    print("Patch verification OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
