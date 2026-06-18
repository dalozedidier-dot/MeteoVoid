# MeteoVoid fix v1 — Bulletin zones à surveiller

Fichiers complets à remplacer :

- `tools/build_belgium_public_site.py`
- `tests/test_build_public_site.py`
- `src/meteovoid/db.py`

Correction principale :

- Le bulletin affichait des dictionnaires Python bruts dans `Zones à surveiller`, par exemple `{'Key': 'Alert', 'Label': 'Critique', ...}`.
- La cause était `_meta()` qui recevait parfois une sévérité déjà normalisée sous forme de dictionnaire et la retraitait comme une simple chaîne.
- `_meta()` accepte maintenant à la fois les clés simples (`alert`, `high`, `watch_reinforced`) et les objets déjà normalisés (`{"key":"alert","label":"Critique","class":"danger","rank":5}`).

Correction secondaire :

- `src/meteovoid/db.py` vérifie maintenant `DATABASE_URL` avant d'importer `psycopg2`, ce qui garde le comportement attendu quand aucune base n'est configurée.

Validation locale effectuée :

```bash
PYTHONPATH=src python -m compileall -q src tools tests
PYTHONPATH=src:. python -m pytest -q -o addopts='' \
  tests/test_build_public_site.py \
  tests/test_belgium_public_site.py \
  tests/test_belgium_extended_outputs.py \
  tests/test_db.py::test_connect_no_url
```

Résultat : `15 passed` + site offline demo reconstruit sans dictionnaire brut dans `Zones à surveiller`.

Note : le test complet n'a pas été lancé avec succès dans le sandbox car les dépendances optionnelles de CI (`hypothesis`, `redis`, `psycopg2`, `ruff`) ne sont pas installées ici. Le workflow GitHub installe normalement `.[dev,live,viz]`.
