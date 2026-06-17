# MeteoVoid · OPERA ORD / MeteoGate

Cette couche implante une chaîne OPERA ORD complète et prudente pour MeteoVoid.

Objectif : passer d’un simple affichage radar à une voie radar machine exploitable quand les données européennes OPERA sont réellement disponibles.

Chaîne prévue :

```text
MeteoGate ORD API
→ découverte des produits
→ inventaire JSON
→ liens de données
→ téléchargement optionnel
→ cache local hashé
→ lecture GeoTIFF / ODIM HDF5 si dépendances disponibles
→ métriques radar
→ radar_stack.json
→ upstream_watch.json
→ site public api/radar.json
```

## Fichiers ajoutés

```text
src/meteovoid/belgium/opera_ord.py
tools/fetch_opera_ord.py
config/opera_ord.yaml
.github/workflows/opera_ord_live_smoke.yml
tests/test_opera_ord.py
```

## Sorties

```text
opera_ord_status.json
opera_ord_inventory.json
opera_ord_files_manifest.json
opera_radar_metrics.json
radar_stack.json
api/radar.json
```

## Règle de prudence

RainViewer reste une carte visuelle. OPERA ORD est la voie radar machine. MeteoVoid ne transforme pas des tuiles affichées dans un navigateur en preuve radar exploitable.

Les niveaux sont séparés :

```text
RainViewer seul = display_only
OPERA metadata seule = metadata_available_no_data_links
OPERA liens disponibles = data_links_available
OPERA fichiers téléchargés = opera_ord_files_downloaded
OPERA fichiers lisibles + métriques = opera_ord_metrics_available
```

## Utilisation hors ligne

```bash
python tools/fetch_opera_ord.py --out-dir _out/opera
```

Résultat attendu : statut `disabled`, sans erreur.

## Utilisation live sans téléchargement

```bash
python tools/fetch_opera_ord.py \
  --enable \
  --config config/opera_ord.yaml \
  --out-dir _out/opera \
  --datetime "2026-06-17T00:00Z/2026-06-17T01:00Z"
```

## Utilisation live avec téléchargement

```bash
python tools/fetch_opera_ord.py \
  --enable \
  --download \
  --config config/opera_ord.yaml \
  --out-dir _out/opera \
  --datetime "2026-06-17T00:00Z/2026-06-17T01:00Z" \
  --max-download-files 4
```

## Intégration avec le rapport Belgique

```bash
python tools/generate_belgium_alert_report.py \
  --out-dir _out/belgium \
  --enable-opera-ord \
  --enable-opera-download \
  --opera-datetime "2026-06-17T00:00Z/2026-06-17T01:00Z"
```

Le rapport génère d’abord la couche radar, puis injecte les métriques OPERA disponibles dans la veille amont européenne lorsque `opera_radar_metrics.json` existe.

## Dépendances optionnelles

Pour lire plus profondément les fichiers radar :

```bash
pip install -e ".[radar]"
```

`wradlib` sert à préparer la lecture ODIM HDF5. `pySTEPS` sert au nowcasting si plusieurs trames radar successives sont fournies.

Aucune de ces dépendances lourdes n’est obligatoire pour la CI standard.
