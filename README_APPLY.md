MeteoVoid patch (v2) – Fix CI + Live Smoke contract

Contenu
- src/meteovoid/api.py
  - Fix mypy/ruff/black formatting issues
  - Supprime le .format() sur la page /dashboard (problème d’accolades CSS)
  - Corrige isinstance(..., bytes | bytearray) -> tuple (bytes, bytearray)
  - Rend _ts_ingest() compatible mypy (None-safe)

- src/meteovoid/stream.py
  - Restaure stats.dt_median_s (requis par tools/validate_latest_report.py)
  - Conserve dt_ref_s pour l’imputation interne

- tests/test_alerts.py
  - Supprime import inutilisé (os)

- tests/test_api_latest_any.py
  - Formatage (black/ruff-format) + lignes longues

- .github/workflows/live_smoke.yml
  - Workflow Live Smoke stable (Docker Compose), tel que validé

- .github/workflows/release.yml
  - skip-existing: true (évite échec lors d’un rerun sur une version déjà publiée)

- tools/validate_latest_report.py
- docs/LATEST_REPORT_CONTRACT.md

Application
1) Dézipper ce ZIP à la racine du repo (en conservant les chemins)
2) Commit + push
3) Relancer Actions: CI + Live Smoke
