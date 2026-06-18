# MeteoVoid Europe Max Page Patch

Objectif : remplacer la page Europe minimale par une vraie page Europe structurée au même niveau de lecture que la page Belgique.

## Fichiers modifiés

- `tools/build_belgium_public_site.py`
- `tests/test_build_public_site.py`

## Ce que le patch ajoute côté Europe

- Page `europe.html` beaucoup plus complète.
- API `api/europe.json` enrichie avec le contrat `meteovoid_europe_page_full_v2`.
- Vue simple Europe.
- Vue opérationnelle Europe.
- Vue carte Europe.
- Vue par pays.
- Vue corridors amont.
- Vue sources radar.
- Vue expert avec exports.
- Chaîne opérationnelle explicite : RainViewer, OPERA ORD, radars nationaux, métriques, corridors.
- Table pays : Espagne, France, Suisse, Pays-Bas.
- Table sources : AEMET, Météo-France, MeteoSwiss, KNMI, OPERA ORD fallback.
- Blocage clair des sources : clé API manquante, endpoint non configuré, donnée machine absente.
- Radar layers : RainViewer, OPERA ORD, radars nationaux.
- Corridors amont depuis `upstream_watch.json`.
- Liens vers carte nationale, RainViewer, OPERA, upstream, API radar, API Europe.

## Règle de rigueur

La page ne transforme pas une carte affichée en preuve radar. Une source radar devient preuve machine uniquement si un fichier radar est lisible et transformé en métriques.

## Contrôles effectués

```bash
python -m py_compile tools/build_belgium_public_site.py tests/test_build_public_site.py
pytest -q --no-cov tests/test_build_public_site.py
pytest -q --no-cov tests/test_build_public_site.py tests/test_european_national_radar.py tests/test_radar_stack.py tests/test_upstream_watch.py tests/test_opera_ord.py
PYTHONPATH=src python tools/build_belgium_public_site.py --report-dir /mnt/data/meteo_eu_national_cifix_out --site-dir /mnt/data/meteo_europe_max_site
```

Résultat :

- 7 tests UI passés.
- 36 tests ciblés passés.
- `europe.html` généré.
- `api/europe.json` généré.
- La page contient les vues : Vue simple, Opérationnel, Carte Europe, Pays, Corridors, Sources, Expert.
