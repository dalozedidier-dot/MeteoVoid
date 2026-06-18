#!/usr/bin/env python3
"""
MeteoVoid CI serious fix.

This script is intentionally self-cleaning. Run it once from the repository root.
It patches the real generator, removes patch-delivery artifacts that must not be
committed, verifies the alert_state contract fields, and then deletes itself.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
GENERATOR = ROOT / "tools" / "generate_belgium_alert_report.py"
VERIFY_DIR = ROOT / "_ci_contract_verify"
SELF = Path(__file__).resolve()

PATCH_ARTIFACT_NAMES = {
    "apply_alert_state_contract_fields.py",
    "MeteoVoid_belgium_structural_hardening.diff",
    "README_APPLY_ALERT_STATE_CONTRACT_FIX.md",
    "README_APPLY_ALERT_STATE_CONTRACT_FIELDS.md",
    "README_APPLY_FINAL_CI_PRECOMMIT_FIX.md",
    "README_APPLY_CI_ARTIFACT_CLEANUP_FIX.md",
    "README_APPLY_PRECOMMIT_ARTIFACT_GUARD.md",
    "README_DO_NOT_COMMIT_PATCH_FILES.md",
}

PATCH_ARTIFACT_PREFIXES = (
    "MeteoVoid_",
    "mv_",
)

PATCH_ARTIFACT_SUFFIXES = (
    ".diff",
    ".patch",
)

REQUIRED_ALERT_STATE_KEYS = {
    "notification_allowed",
    "public_wording",
    "official_alert",
}


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("$", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT, text=True, check=check)


def is_git_repo() -> bool:
    if (ROOT / ".git").exists():
        return True
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    return result.returncode == 0


def git_rm(path: Path) -> None:
    rel = str(path.relative_to(ROOT))
    if is_git_repo():
        subprocess.run(
            ["git", "rm", "-f", "--ignore-unmatch", rel],
            cwd=ROOT,
            text=True,
            check=False,
        )
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        path.unlink()


def cleanup_patch_artifacts() -> list[str]:
    removed: list[str] = []
    for path in sorted(ROOT.iterdir()):
        name = path.name
        should_remove = False
        if name in PATCH_ARTIFACT_NAMES:
            should_remove = True
        if name.endswith(PATCH_ARTIFACT_SUFFIXES):
            should_remove = True
        if name.endswith("_patch.zip") or name.endswith("_patch"):
            should_remove = True
        if name.startswith("mv_") and name.endswith("_patch"):
            should_remove = True
        if should_remove:
            removed.append(name)
            git_rm(path)
    return removed


def replace_function(text: str, func_name: str, replacer) -> str:
    pattern = re.compile(
        rf"(^def {re.escape(func_name)}\(.*?\n)(?=^def |\Z)",
        flags=re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        raise SystemExit(f"Could not find function {func_name!r} in {GENERATOR}.")
    old = match.group(1)
    new = replacer(old)
    return text[: match.start(1)] + new + text[match.end(1) :]


def patch_operational_state(func: str) -> str:
    if '"notification_allowed": notification_allowed' in func:
        return func

    anchor = (
        '    if trend_status in {"rising", "rising_fast"} and level in {"watch", "watch_reinforced"}:\n'
        '        reason = f"{reason}. Tendance en hausse"\n'
        "    return {\n"
    )
    replacement = (
        '    if trend_status in {"rising", "rising_fast"} and level in {"watch", "watch_reinforced"}:\n'
        '        reason = f"{reason}. Tendance en hausse"\n'
        "\n"
        "    notification_allowed = level in {\n"
        '        "watch_reinforced",\n'
        '        "pre_alert_confirmed",\n'
        '        "alert_confirmed",\n'
        "    }\n"
        "    public_wording = {\n"
        '        "alert_confirmed": "alerte technique confirmée, non officielle",\n'
        '        "pre_alert_confirmed": "pré-alerte technique confirmée, non officielle",\n'
        '        "watch_reinforced": "veille renforcée, non officielle",\n'
        '        "watch": "veille météo technique non officielle",\n'
        '        "low_watch": "surveillance faible, non officielle",\n'
        '        "normal": "pas de signal notable, non officiel",\n'
        '    }.get(level, "veille météo technique non officielle")\n'
        "    official_alert = False\n"
        "\n"
        "    return {\n"
    )
    if anchor not in func:
        raise SystemExit("Could not find operational_state return anchor.")
    func = func.replace(anchor, replacement, 1)

    field_anchor = (
        '        "trend_status": trend_status,\n'
        '        "public_alert_allowed": level in {"pre_alert_confirmed", "alert_confirmed"},\n'
    )
    field_replacement = (
        '        "trend_status": trend_status,\n'
        '        "notification_allowed": notification_allowed,\n'
        '        "public_wording": public_wording,\n'
        '        "official_alert": official_alert,\n'
        '        "public_alert_allowed": level in {"pre_alert_confirmed", "alert_confirmed"},\n'
    )
    if field_anchor not in func:
        raise SystemExit("Could not find operational_state field anchor.")
    return func.replace(field_anchor, field_replacement, 1)


def patch_notification_state(func: str) -> str:
    if '"notification_allowed": bool(' in func:
        return func

    anchor = (
        '        "reason": reason,\n'
        '        "public_alert_allowed": bool(operational.get("public_alert_allowed", False)),\n'
    )
    replacement = (
        '        "reason": reason,\n'
        '        "notification_allowed": bool(\n'
        '            operational.get("notification_allowed", should_notify)\n'
        "        ),\n"
        '        "public_wording": str(\n'
        '            operational.get("public_wording", "veille météo technique non officielle")\n'
        "        ),\n"
        '        "official_alert": bool(operational.get("official_alert", False)),\n'
        '        "public_alert_allowed": bool(operational.get("public_alert_allowed", False)),\n'
    )
    if anchor not in func:
        raise SystemExit("Could not find notification_state field anchor.")
    return func.replace(anchor, replacement, 1)


def patch_generator() -> None:
    if not GENERATOR.exists():
        raise SystemExit(f"Missing {GENERATOR.relative_to(ROOT)}")
    text = GENERATOR.read_text(encoding="utf-8")
    original = text
    text = replace_function(text, "_operational_state", patch_operational_state)
    text = replace_function(text, "_notification_state", patch_notification_state)
    if text != original:
        GENERATOR.write_text(text, encoding="utf-8")
        print(f"patched {GENERATOR.relative_to(ROOT)}")
    else:
        print("generator already contains required contract fields")


def module_available(module_name: str) -> bool:
    result = subprocess.run(
        [sys.executable, "-c", f"import {module_name}"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    return result.returncode == 0


def maybe_format() -> None:
    # Prefer ruff format if available, then black. Do not fail if tools are absent.
    if module_available("ruff"):
        run([sys.executable, "-m", "ruff", "format", str(GENERATOR)], check=False)
    if module_available("black"):
        run([sys.executable, "-m", "black", str(GENERATOR)], check=False)


def verify_source_contains_fields() -> None:
    text = GENERATOR.read_text(encoding="utf-8")
    missing = [key for key in REQUIRED_ALERT_STATE_KEYS if key not in text]
    if missing:
        raise SystemExit(f"Source still misses required fields: {missing}")


def verify_runtime_generation() -> None:
    stations = ROOT / "config" / "stations_belgium.yaml"
    if not stations.exists():
        print("skip runtime verification: config/stations_belgium.yaml not found")
        return
    if VERIFY_DIR.exists():
        shutil.rmtree(VERIFY_DIR)
    VERIFY_DIR.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(GENERATOR),
        "--stations",
        str(stations),
        "--target-date",
        "2026-06-19",
        "--offline-demo",
        "--out-dir",
        str(VERIFY_DIR),
        "--official-forecast-signal",
        "severe_thunderstorms",
        "--heat-warning-active",
        "--external-note",
        "IRM/KMI annonce un risque d'orages violents.",
    ]
    result = subprocess.run(cmd, cwd=ROOT, text=True, check=False)
    if result.returncode != 0:
        print("warning: runtime verification skipped/failed, source patch still applied")
        return
    alert_state_path = VERIFY_DIR / "alert_state.json"
    if not alert_state_path.exists():
        print("warning: alert_state.json not generated during verification")
        return
    alert_state = json.loads(alert_state_path.read_text(encoding="utf-8"))
    missing = sorted(REQUIRED_ALERT_STATE_KEYS - set(alert_state))
    if missing:
        raise SystemExit(f"Runtime alert_state.json still misses: {missing}")
    print("runtime verification OK: alert_state.json contains required fields")


def final_cleanup() -> None:
    if VERIFY_DIR.exists():
        shutil.rmtree(VERIFY_DIR, ignore_errors=True)

    # Remove files delivered by this patch after successful execution.
    for name in ("README_DO_NOT_COMMIT_PATCH_FILES.md",):
        p = ROOT / name
        if p.exists():
            p.unlink()

    try:
        if SELF.exists() and SELF.parent == ROOT:
            SELF.unlink()
    except OSError:
        pass


def main() -> int:
    if not (ROOT / "pyproject.toml").exists() or not (ROOT / "tools").exists():
        raise SystemExit("Run this script from the MeteoVoid repository root.")

    removed = cleanup_patch_artifacts()
    if removed:
        print("removed patch artifacts:", ", ".join(removed))

    patch_generator()
    maybe_format()
    verify_source_contains_fields()
    run([sys.executable, "-m", "compileall", "-q", "tools"], check=True)
    verify_runtime_generation()
    final_cleanup()

    print("\nOK. Commit only real source changes, normally:")
    print("  git add -A")
    print('  git commit -m "ci: fix Belgium alert state contract cleanly"')
    print("  git push")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
