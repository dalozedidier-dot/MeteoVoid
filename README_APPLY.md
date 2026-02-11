# MeteoVoid hotfix v2

Corrige 2 problèmes:
1) Workflow Live Smoke invalide (YAML): bloc python non indenté dans `run: |`.
2) Pre-commit ruff en échec sur tools/validate_latest_report.py (UP038).

Contenu:
- .github/workflows/live_smoke.yml
- tools/validate_latest_report.py

Application:
1) Dézipper à la racine du repo (en conservant les chemins).
2) Commit + push.
3) Vérifier que le workflow Live Smoke réapparaît et passe.
