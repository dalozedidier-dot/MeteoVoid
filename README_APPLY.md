# MeteoVoid workflows fix v2

## Live Smoke
Correction de l’erreur YAML introduite par un heredoc Python non indenté dans `run: |`.
Cette version ne contient aucun heredoc. Elle supporte aussi votre API `GET /latest` qui exige `station_id` et `variable`:
- tentative `/latest` sans paramètres
- si 422, découverte d’un couple (station_id, variable) via `/stations`
- appel `/latest?station_id=...&variable=...`
- validation via `tools/validate_latest_report.py`

## Release
Correction des échecs en `workflow_dispatch`:
- `github-release` et `publish-pypi` ne s’exécutent que sur tags `v*`
- en dispatch manuel, seul `build` tourne (artefacts dist)
- `publish-pypi` est `continue-on-error` pour ne pas bloquer la release GitHub si PyPI est mal configuré

## Application
1) Dézipper à la racine du repo, conserver les chemins.
2) Commit + push.
3) Relancer Live Smoke, vérifier l’artefact `live_smoke_report`.
4) Pour une vraie release: bump version, tag `vX.Y.Z`, push du tag.
