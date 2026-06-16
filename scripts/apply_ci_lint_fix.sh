#!/usr/bin/env bash
set -euo pipefail

# Remove patch artefacts that were accidentally included in the repository and
# are checked by pre-commit hooks.
rm -f MeteoVoid_belgium_structural_hardening.diff
rm -f MeteoVoid_belgium_structural_hardening_patch.diff

python -m compileall tools/validate_belgium_contracts.py tools/generate_belgium_alert_report.py

if command -v ruff >/dev/null 2>&1; then
  ruff check tools/validate_belgium_contracts.py tools/generate_belgium_alert_report.py
fi

if command -v black >/dev/null 2>&1; then
  black --check tools/validate_belgium_contracts.py tools/generate_belgium_alert_report.py
fi

if command -v pre-commit >/dev/null 2>&1; then
  pre-commit run --all-files
fi
