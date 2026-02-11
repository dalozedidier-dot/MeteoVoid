# MeteoVoid workflows fix v3

Pourquoi ça cassait:
- Votre log CI montre `check-yaml` en échec: `.github/workflows/live_smoke.yml` ligne 91/92.
- Cause: un caractère CR (\r) ou une coupure de ligne non indentée s’est glissé dans le fichier, ce qui fait sortir YAML du bloc `run: |`.

Ce patch:
- Remet un `live_smoke.yml` YAML valide (aucune ligne "cassée", aucune séquence \r injectée).
- Gère aussi le 422 sur `/latest` (API exige `station_id` + `variable`) via découverte `/stations`.
- Rend `release.yml` inoffensif en `workflow_dispatch` (publish + github-release ne tournent que sur tag v*).

Application:
1) Dézipper à la racine du repo (en gardant les chemins).
2) Commit + push.
3) CI doit repasser (check-yaml).
4) Live Smoke doit repasser et produire `latest.json`.
5) Release: en manuel -> build seulement. En tag vX.Y.Z -> build + publish + github release.
