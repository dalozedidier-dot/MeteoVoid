#!/usr/bin/env bash
set -euo pipefail

if [[ ! -d ".git" ]]; then
  echo "Ce script doit être exécuté depuis la racine du projet (dossier git)"
  exit 1
fi

git add .github/ Dockerfile || true
git commit -m "ci: add workflows (CI, Docker, Release) + dependabot" || true
git push

echo "Workflows poussés."
