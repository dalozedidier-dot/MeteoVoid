Patch Live Smoke report (v1)

But
- L'artefact live_smoke_report ne contenait pas latest.json ni bulletin.* (seulement compose.log/ps.txt).

Ce patch force:
- Sauvegarde de http://localhost:8000/latest vers _ci_out/live_smoke/latest.json
- Génération d'un bulletin dans _ci_out/live_smoke/ via tools/generate_bulletin.py:
  - bulletin.json
  - bulletin.md
  - history.jsonl
  - history.csv
- Upload de tout _ci_out/live_smoke/

Fichiers modifiés
- .github/workflows/live_smoke.yml
