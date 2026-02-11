# MeteoVoid patch fix v1 (Live Smoke 422 + Release fallback)

## 1) Live Smoke 422
Votre API FastAPI `GET /latest` exige `station_id` et `variable` (Query(...)).
Le workflow appelait `/latest` sans paramètres -> 422 Unprocessable Entity -> pas de latest.json.

Le nouveau workflow:
- tente `/latest` sans paramètres (compat)
- si 422, appelle `/stations` pour découvrir un couple (station_id, variable)
- appelle ensuite `/latest?station_id=...&variable=...`
- valide le JSON via `tools/validate_latest_report.py`
- sauvegarde `latest.json` dans l’artefact.

## 2) Release PyPI
Votre log montre `invalid-publisher` (Trusted Publisher non configuré).
Ce patch ajoute un fallback:
- si `PYPI_API_TOKEN` est défini dans les secrets, publication via token
- sinon, tentative OIDC Trusted Publisher (à configurer côté PyPI)

## Contenu
- .github/workflows/live_smoke.yml
- .github/workflows/release.yml

## Application
1) Dézipper à la racine du repo (en conservant les chemins).
2) Commit + push.
3) Relancer Live Smoke (vous devez retrouver `latest.json` dans l’artefact).
4) Pour PyPI: soit configurer Trusted Publisher, soit ajouter `PYPI_API_TOKEN` dans Secrets.
