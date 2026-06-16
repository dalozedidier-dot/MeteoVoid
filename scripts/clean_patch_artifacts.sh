#!/usr/bin/env bash
set -euo pipefail

# Remove patch-delivery artifacts that should never be tracked by the repo.
# This is intentionally strict because pre-commit scans tracked files.

tracked_artifacts=$(git ls-files '*.diff' '*.patch' '*_patch.zip' 'PATCH_NOTES_*.md' 'README_APPLY_*.md' 2>/dev/null || true)
if [ -n "$tracked_artifacts" ]; then
  echo "$tracked_artifacts" | xargs -r git rm -f --
fi

find . -path ./.git -prune -o \
  \( -name '*.diff' -o -name '*.patch' -o -name '*_patch.zip' \) \
  -type f -print -delete

find . -path ./.git -prune -o \
  \( -name 'mv_*_patch' -o -name 'patch_package' \) \
  -type d -print -exec rm -rf {} + 2>/dev/null || true

echo "Patch artifacts cleaned. Run: git status"
