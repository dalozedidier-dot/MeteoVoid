#!/usr/bin/env bash
set -euo pipefail

# Ce repo est fourni sous forme de squelette complet.
# Ce script sert uniquement à vérifier la structure après extraction du zip.

REPO_NAME="${REPO_NAME:-MeteoVoid}"

if [[ ! -f "pyproject.toml" ]]; then
  echo "pyproject.toml introuvable. Exécutez ce script depuis la racine du projet."
  exit 1
fi

mkdir -p src/meteovoid tests examples docs benchmarks notebooks .github/workflows scripts
chmod +x scripts/*.sh || true

echo "Structure OK."
