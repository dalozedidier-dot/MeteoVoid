# MeteoVoid — Correctif page Europe dédiée

Ce patch corrige le problème signalé : les radars Europe n'étaient pas intégrés dans une vraie page autonome. Ils étaient seulement visibles comme section/iframe dans la page Belgique.

## Ajouts principaux

- Création d'une page publique dédiée `europe.html`.
- Création de l'endpoint `api/europe.json`.
- Ajout d'un lien direct `Europe` dans la navigation principale de `index.html`.
- Modèle Europe séparé de la Belgique : Espagne, France, Suisse, Pays-Bas.
- Tableau détaillé par pays : rôle amont, corridor, priorité Belgique, statut radar, fichiers lisibles, sources.
- Carte Europe intégrée : `reports/latest/european_national_radar_map.html`.
- Bloc de lecture rapide : RainViewer, OPERA ORD, radars nationaux, upstream watch.
- Liens directs : rapport Europe, CSV sources, API radar, API Europe, radar stack, carte amont.
- Fallback robuste : si l'ancien run n'a que les métriques et pas le statut complet, la page Europe est quand même générée.

## Fichiers modifiés

- `tools/build_belgium_public_site.py`
- `tests/test_build_public_site.py`

## Contrôles effectués

```bash
python -m py_compile tools/build_belgium_public_site.py tests/test_build_public_site.py
python -m pytest -q --no-cov tests/test_build_public_site.py
python -m pytest -q --no-cov tests/test_build_public_site.py tests/test_european_national_radar.py tests/test_radar_stack.py tests/test_upstream_watch.py tests/test_opera_ord.py
PYTHONPATH=src python tools/build_belgium_public_site.py --report-dir /mnt/data/meteo_eu_national_cifix_out --site-dir /mnt/data/meteo_europe_page_site
```

Résultat :

- 7 tests UI passés.
- 36 tests ciblés passés.
- `europe.html` généré.
- `api/europe.json` généré.
- `index.html` contient le lien vers `europe.html`.

## Note

`ruff`, `black` et `mypy` ne sont pas installés dans le sandbox utilisé ici. Le patch compile et les tests ciblés passent.
