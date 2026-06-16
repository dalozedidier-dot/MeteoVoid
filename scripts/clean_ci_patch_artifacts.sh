#!/usr/bin/env bash
set -euo pipefail

# Remove temporary patch-delivery files accidentally committed at repo root.
# These files are not MeteoVoid source code and should not be checked by CI.
patterns=(
  "apply_*.py"
  "fix_meteovoid_*.py"
  "fix_*_patch*.py"
  "MeteoVoid_*.diff"
  "*.patch"
  "README_APPLY*.md"
  "PATCH_NOTES*.md"
  "PATCH_NOTES*.txt"
)

for pattern in "${patterns[@]}"; do
  while IFS= read -r -d '' file; do
    if git ls-files --error-unmatch "$file" >/dev/null 2>&1; then
      git rm -f "$file"
    else
      rm -f "$file"
    fi
  done < <(find . -maxdepth 1 -type f -name "$pattern" -print0)
done

# Remove common unpacked patch folders from the working tree if present.
find . -maxdepth 1 -type d \( -name '*_patch' -o -name 'patch_*' \) -print0 | while IFS= read -r -d '' dir; do
  rm -rf "$dir"
done

echo "Patch delivery artifacts cleaned. Run: git status"
