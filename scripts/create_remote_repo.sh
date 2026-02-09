#!/usr/bin/env bash
set -euo pipefail

REPO_NAME="${REPO_NAME:-MeteoVoid}"
REPO_DESC="${REPO_DESC:-Graph-based upstream weather silence & anomaly detector – voids before the storm}"
REPO_VISIBILITY="${REPO_VISIBILITY:-public}" # public | private
LICENSE="${LICENSE:-MIT}"
TOPICS_DEFAULT=(
  meteorology
  anomaly-detection
  graph-theory
  chaos-theory
  systematic-observation
  null-trace
  upstream-guard
)
TOPICS="${TOPICS:-${TOPICS_DEFAULT[*]}}"

command -v gh >/dev/null 2>&1 || { echo "GitHub CLI (gh) non installé"; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "Pas authentifié. Exécutez: gh auth login"; exit 1; }

OWNER="$(gh api user --jq .login)"
FULL_NAME="$OWNER/$REPO_NAME"

if [[ ! -d ".git" ]]; then
  echo "Ce script doit être exécuté depuis la racine du projet (dossier git)"
  exit 1
fi

echo "Création du dépôt distant: $FULL_NAME ($REPO_VISIBILITY)"
set +e
gh repo create "$FULL_NAME" \
  --"$REPO_VISIBILITY" \
  --description "$REPO_DESC" \
  --license "$LICENSE" \
  --source . \
  --remote origin \
  --push
RC=$?
set -e

if [[ $RC -ne 0 ]]; then
  echo "Le dépôt existe peut être déjà. On continue."
fi

# Topics via API (plus stable que les flags)
IFS=' ' read -r -a TOPIC_ARR <<< "$TOPICS"
JSON_TOPICS="$(python - <<'PY'
import json, os
topics = os.environ["TOPICS"].split()
print(json.dumps({"names": topics}))
PY
)"
gh api -X PUT "repos/$FULL_NAME/topics" \
  -H "Accept: application/vnd.github+json" \
  --input <(echo "$JSON_TOPICS") >/dev/null

echo "OK: https://github.com/$FULL_NAME"
