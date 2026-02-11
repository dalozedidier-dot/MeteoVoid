# MeteoVoid Live Smoke YAML fix v1

But:
- Corriger l’erreur de syntaxe YAML (ligne ~72) causée par un bloc Python non indenté dans `run: |`.

Contenu:
- .github/workflows/live_smoke.yml (corrigé)

Application:
1) Dézipper à la racine du repo (en conservant les chemins).
2) Commit + push.
3) Relancer le workflow Live Smoke.
