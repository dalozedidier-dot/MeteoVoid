#!/usr/bin/env bash
set -euo pipefail

python - <<'PY'
from pathlib import Path

path = Path("tools/generate_belgium_alert_report.py")
if not path.exists():
    raise SystemExit("Missing tools/generate_belgium_alert_report.py. Run this script from the repository root.")

text = path.read_text(encoding="utf-8")
original = text

# 1) Ensure _operational_state computes the new contract-safe fields.
needle = '''    if trend_status in {"rising", "rising_fast"} and level in {"watch", "watch_reinforced"}:
        reason = f"{reason}. Tendance en hausse"
    return {
'''
replacement = '''    if trend_status in {"rising", "rising_fast"} and level in {"watch", "watch_reinforced"}:
        reason = f"{reason}. Tendance en hausse"

    notification_allowed = level in {"pre_alert_confirmed", "alert_confirmed"}
    public_wording = {
        "normal": "surveillance normale, non officielle",
        "low_watch": "veille faible, non officielle",
        "watch": "veille, non officielle",
        "watch_reinforced": "veille renforcée, non officielle",
        "pre_alert_confirmed": "pré-alerte technique confirmée, non officielle",
        "alert_confirmed": "alerte technique confirmée, non officielle",
    }.get(level, "veille technique, non officielle")

    return {
'''
if "notification_allowed = level in" not in text and needle in text:
    text = text.replace(needle, replacement, 1)

old = '''        "trend_status": trend_status,
        "public_alert_allowed": level in {"pre_alert_confirmed", "alert_confirmed"},
        "public_alert_caution": "Ne jamais publier comme alerte officielle. Comparer avec IRM/KMI, MeteoAlarm, radar et foudre.",
'''
new = '''        "trend_status": trend_status,
        "notification_allowed": notification_allowed,
        "public_wording": public_wording,
        "official_alert": False,
        "public_alert_allowed": notification_allowed,
        "public_alert_deprecated": "Use notification_allowed/public_wording/official_alert instead.",
        "public_alert_caution": "Ne jamais publier comme alerte officielle. Comparer avec IRM/KMI, MeteoAlarm, radar et foudre.",
'''
if old in text:
    text = text.replace(old, new, 1)

# 2) Ensure _notification_state also respects the same contract.
needle = '''    if trend in {"rising", "rising_fast"} and level in {"watch", "watch_reinforced"}:
        should_notify = True
        reason += ", tendance en hausse"
    return {
'''
replacement = '''    if trend in {"rising", "rising_fast"} and level in {"watch", "watch_reinforced"}:
        should_notify = True
        reason += ", tendance en hausse"
    notification_allowed = bool(
        operational.get("notification_allowed", operational.get("public_alert_allowed", False))
    )
    return {
'''
if "operational.get(\"notification_allowed\", operational.get(\"public_alert_allowed\", False))" not in text and needle in text:
    text = text.replace(needle, replacement, 1)

old = '''        "reason": reason,
        "public_alert_allowed": bool(operational.get("public_alert_allowed", False)),
        "message_title": "MeteoVoid Belgique - veille météo",
'''
new = '''        "reason": reason,
        "notification_allowed": notification_allowed,
        "public_wording": operational.get("public_wording", "veille technique, non officielle"),
        "official_alert": bool(operational.get("official_alert", False)),
        "public_alert_allowed": notification_allowed,
        "message_title": "MeteoVoid Belgique - veille météo",
'''
if old in text:
    text = text.replace(old, new, 1)

# 3) Fail loudly if the critical contract keys are still not emitted.
required_fragments = [
    '"notification_allowed": notification_allowed',
    '"public_wording": public_wording',
    '"official_alert": False',
    '"public_wording": operational.get("public_wording", "veille technique, non officielle")',
]
missing = [frag for frag in required_fragments if frag not in text]
if missing:
    raise SystemExit("Patch did not find/insert all required fragments: " + repr(missing))

if text != original:
    path.write_text(text, encoding="utf-8")
    print("Updated tools/generate_belgium_alert_report.py")
else:
    print("No changes needed: alert_state contract fields already present")
PY

python -m compileall tools/generate_belgium_alert_report.py
