# Bulletin MeteoVoid Live

Le workflow **Live Smoke** produit un artefact `live_smoke_report/` qui contient :

- `latest.json` : snapshot brut récupéré depuis `/latest`
- `latest_enriched.json` : snapshot enrichi pour lecture humaine
- `bulletin.json` : bulletin structuré
- `bulletin.md` : bulletin lisible en Markdown
- `history.jsonl` et `history.csv` : historique court extrait du stream `meteovoid:reports`
- `ps.txt`, `compose.log` : diagnostics Docker

## Idée

`latest.json` est une preuve technique. Le bulletin est la couche humaine :

- résumer le niveau de sévérité sans masquer les limites ;
- exposer les métriques principales (`score`, `state`, `station_id`, `variable`, `stats`, `meteo`) ;
- ajouter une lecture d’incohérence légère si la configuration le permet ;
- conserver un historique append-only pour comparer les runs.

## Génération actuelle en CI

Le workflow `.github/workflows/live_smoke.yml` utilise principalement :

```bash
python tools/postprocess_live_report.py \
  --latest _ci_out/live_smoke/latest.json \
  --out-dir _ci_out/live_smoke \
  --history-csv _ci_out/live_smoke/history.csv \
  --incoherence-config config/incoherence.json
```

Le script `tools/postprocess_live_report.py` produit ensuite :

- `latest_enriched.json`
- `bulletin.json`
- `bulletin.md`
- `history.csv`
- `history.jsonl`

`tools/generate_bulletin.py` reste disponible comme outil auxiliaire pour interroger une API déjà exposée (`/stations`, `/latest?...`), mais il n’est plus le chemin principal du workflow Live Smoke.

## Page publique Belgique

La page publique Belgique possède aussi un bulletin statique dans `api/latest.json` et dans le modèle de page généré par `tools/build_belgium_public_site.py`.

Dans ce bulletin, les zones sont séparées en deux familles :

- **Zones belges à surveiller** : provinces et régions belges réellement dans le domaine Belgique ;
- **Couloirs amont à surveiller** : zones d’approche depuis les pays voisins, par exemple `Approche France`, `Approche Pays-Bas`, `Approche Allemagne` ou `Approche Luxembourg`.

Cette séparation évite de mélanger une province belge avec une zone d’entrée extérieure. Les couloirs amont servent à lire ce qui arrive vers la Belgique ; ils ne doivent pas être présentés comme des provinces belges.

## Contrat d’affichage

Le bulletin ne doit jamais afficher de représentation Python brute, par exemple :

```text
{'key': 'alert', 'label': 'Critique', 'class': 'danger', 'rank': 5}
```

Les sévérités doivent toujours être rendues sous forme humaine :

```text
Critique
Élevé
Veille renforcée
```

Le test `test_bulletin_zones_are_clean_and_split_from_upstream` protège ce comportement.
