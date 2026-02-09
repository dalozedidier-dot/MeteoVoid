#!/usr/bin/env bash
set -euo pipefail

REPO_NAME="${REPO_NAME:-MeteoVoid}"
VERSION_TAG="${VERSION_TAG:-v0.1.0}"

command -v gh >/dev/null 2>&1 || { echo "GitHub CLI (gh) non installé"; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "Pas authentifié. Exécutez: gh auth login"; exit 1; }

if [[ ! -d ".git" ]]; then
  echo "Ce script doit être exécuté depuis la racine du projet (dossier git)"
  exit 1
fi

# Commit initial
git add .
git commit -m "chore: initial project skeleton" || true

# Labels (idempotent)
gh label create "type: bug" --color ff0000 --description "Quelque chose ne fonctionne pas" || true
gh label create "type: feature" --color 0e8a16 --description "Nouvelle fonctionnalité" || true
gh label create "type: void" --color 6f42c1 --description "Anomalie de type silence/void" || true
gh label create "priority: high" --color b60205 --description "Priorité haute" || true
gh label create "status: triage" --color d4c5f9 --description "A trier" || true

# Tag et push
git tag -a "$VERSION_TAG" -m "Initial structured skeleton" || true
git push -u origin main
git push --tags

echo "Push terminé."
