# MeteoVoid · Patch OPERA ORD complet

Patch à appliquer sur le dépôt `MeteoVoid-main-radar-stack-complete`.

## Objectif

Implanter OPERA ORD comme vraie voie radar machine, sans confondre affichage RainViewer et donnée radar exploitable.

## Fichiers ajoutés

```text
src/meteovoid/belgium/opera_ord.py
tools/fetch_opera_ord.py
docs/OPERA_ORD.md
tests/test_opera_ord.py
.github/workflows/opera_ord_live_smoke.yml
```

## Fichiers modifiés

```text
config/opera_ord.yaml
src/meteovoid/belgium/radar_stack.py
src/meteovoid/belgium/upstream_watch.py
tools/generate_radar_stack.py
tools/generate_belgium_alert_report.py
tools/build_belgium_public_site.py
docs/RADAR_STACK.md
README.md
tests/test_radar_stack.py
```

## Nouvelles sorties

```text
opera_ord_status.json
opera_ord_inventory.json
opera_ord_files_manifest.json
opera_radar_metrics.json
radar_stack.json
api/radar.json
```

## Ce qui est réellement implanté

- Client OPERA ORD / MeteoGate.
- Découverte des produits composites OPERA.
- Construction des requêtes `collections/observations/locations/{location_id}`.
- Extraction des liens de données.
- Téléchargement optionnel en cache local.
- Manifest fichiers avec taille et SHA256.
- Analyse GeoTIFF via `rasterio` si disponible.
- Analyse ODIM HDF5 via `wradlib` si disponible.
- Fallback numérique `.npy`, `.csv`, `.json` pour tests et expériences locales.
- Génération de `opera_radar_metrics.json`.
- Intégration dans `radar_stack.json`.
- Injection du score OPERA dans `upstream_watch.json` lorsque `opera_radar_metrics.json` existe.
- Workflow manuel GitHub Actions `OPERA ORD Live Smoke`.

## Commandes

Offline :

```bash
python tools/fetch_opera_ord.py --out-dir _out/opera
```

Live sans téléchargement :

```bash
python tools/fetch_opera_ord.py \
  --enable \
  --config config/opera_ord.yaml \
  --out-dir _out/opera \
  --datetime "2026-06-17T00:00Z/2026-06-17T01:00Z"
```

Live avec téléchargement :

```bash
python tools/fetch_opera_ord.py \
  --enable \
  --download \
  --config config/opera_ord.yaml \
  --out-dir _out/opera \
  --datetime "2026-06-17T00:00Z/2026-06-17T01:00Z" \
  --max-download-files 4
```

Rapport Belgique avec OPERA ORD :

```bash
python tools/generate_belgium_alert_report.py \
  --out-dir _out/belgium \
  --enable-opera-ord \
  --enable-opera-download \
  --opera-datetime "2026-06-17T00:00Z/2026-06-17T01:00Z"
```

## Contrôles effectués dans le sandbox

```bash
python -m compileall -q src tools tests
python -m pytest -q --no-cov tests/test_opera_ord.py tests/test_radar_stack.py tests/test_upstream_watch.py
PYTHONPATH=src python tools/generate_belgium_alert_report.py --offline-demo --out-dir /mnt/data/meteo_opera_test_out --no-history --target-date 2026-06-19 --official-forecast-signal severe_thunderstorms --heat-warning-active
PYTHONPATH=src python tools/validate_belgium_contracts.py /mnt/data/meteo_opera_test_out
PYTHONPATH=src python tools/validate_belgium_public_latest.py /mnt/data/meteo_opera_test_out/belgium_public_latest.json
PYTHONPATH=src python tools/build_belgium_public_site.py --report-dir /mnt/data/meteo_opera_test_out --site-dir /mnt/data/meteo_opera_site
PYTHONPATH=src python tools/fetch_opera_ord.py --out-dir /mnt/data/meteo_opera_tool_out
```

Résultats : tests ciblés OK, génération offline OK, contrats Belgique OK, site public OK, outil OPERA offline OK.

Je n’ai pas pu lancer `ruff`, `black` ou `mypy` dans ce sandbox car ces paquets ne sont pas installés ici. Le patch contient cependant des fichiers compilés avec `py_compile`/`compileall` et des tests ciblés passés.

## Règle d’honnêteté conservée

RainViewer seul = affichage visuel.
OPERA metadata seule = pas de confirmation machine.
OPERA fichiers téléchargés/lisibles = début de preuve radar machine.
Aucune donnée radar fine absente n’est simulée.
