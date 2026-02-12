# Bulletin MeteoVoid Live

Le workflow **Live Smoke** produit un artefact `live_smoke_report/` qui contient :

- `latest.json` : snapshot d'un report enrichi
- `bulletin.json` : bulletin structuré agrégé (toutes stations et variables)
- `bulletin.md` : bulletin lisible (Markdown)
- `history.jsonl` et `history.csv` : historique court extrait du stream Redis `meteovoid:reports` (best effort)
- `ps.txt`, `compose.log` : diagnostics Docker

## Idée

Le `latest.json` est une preuve technique. Le bulletin est la couche "humain" :

- Agrégation multi-variables par station
- Sévérité globale, confiance, recommandations
- Trend (delta score) si l'historique est disponible

## Génération

Le script `tools/generate_bulletin.py` appelle :

- `GET /stations`
- `GET /latest?station_id=...&variable=...`

Puis tente de lire l'historique depuis Redis via :

- `XRANGE meteovoid:reports - +` dans le service `redis`

Le workflow ajoute automatiquement `bulletin.md` et `bulletin.json` dans l'artefact.
