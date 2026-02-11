# MeteoVoid update patch

Contenu:
- tools/validate_latest_report.py
- docs/LATEST_REPORT_CONTRACT.md
- .github/workflows/live_smoke.yml
- .github/workflows/release.yml

Application:
1) Dézipper à la racine du repo, en conservant les chemins.
2) Commit + push.
3) Lancer le workflow "Live Smoke (Docker Compose)" et vérifier l’artefact `live_smoke_report`.
4) Pour la release: bump version, tagger `vX.Y.Z`, pousser le tag.
