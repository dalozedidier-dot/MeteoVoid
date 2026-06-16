#!/usr/bin/env bash
set -euo pipefail

# Run this from the repository root.
if [ ! -f "pyproject.toml" ]; then
  echo "error: run this script from the MeteoVoid repository root" >&2
  exit 1
fi

mkdir -p tools
cp "$(dirname "$0")/../tools/validate_belgium_contracts.py" tools/validate_belgium_contracts.py
chmod +x tools/validate_belgium_contracts.py

# Patch delivery files must not be committed. Remove the known culprit and any other root-level diff artifacts.
git rm -f MeteoVoid_belgium_structural_hardening.diff 2>/dev/null || true
find . -maxdepth 2 -type f -name '*.diff' -print -delete

# Optional local normalization when tools are installed.
python -m compileall tools/validate_belgium_contracts.py
if command -v ruff >/dev/null 2>&1; then
  ruff check tools/validate_belgium_contracts.py
  ruff format --check tools/validate_belgium_contracts.py
fi
if command -v black >/dev/null 2>&1; then
  black --check tools/validate_belgium_contracts.py
fi

if find . -maxdepth 2 -type f -name '*.diff' | grep -q .; then
  echo "error: .diff artifact still present" >&2
  find . -maxdepth 2 -type f -name '*.diff' >&2
  exit 1
fi

echo "CI artifact cleanup fix applied. Commit the modified validator and the deleted .diff artifact."
