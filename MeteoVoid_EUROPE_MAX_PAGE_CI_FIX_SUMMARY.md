# MeteoVoid — Europe Max Page CI Fix

Correctif appliqué après analyse de `logs_74694857104.zip`.

## Cause CI

Le workflow bloquait uniquement sur `pre-commit` :

- `ruff-format` voulait reformater `tools/build_belgium_public_site.py`.
- `black 24.10.0` voulait reformater le même fichier.
- `mypy (src only)` passait déjà.

## Fichier modifié

- `tools/build_belgium_public_site.py`

## Correction

Le fichier a été formaté avec :

```bash
python -m ruff format tools/build_belgium_public_site.py
python -m black --workers 1 tools/build_belgium_public_site.py
```

## Contrôles effectués

```bash
python -m ruff check tools/build_belgium_public_site.py
python -m ruff format --check tools/build_belgium_public_site.py
python -m black --check --diff --workers 1 tools/build_belgium_public_site.py
PYTHONPATH=. pytest -q --no-cov tests/test_build_public_site.py
PYTHONPATH=. pytest -q --no-cov tests/test_build_public_site.py tests/test_european_national_radar.py tests/test_radar_stack.py tests/test_upstream_watch.py tests/test_opera_ord.py
PYTHONPATH=src python tools/build_belgium_public_site.py --report-dir /mnt/data/meteo_eu_national_cifix_out --site-dir /mnt/data/meteo_europe_max_cifix_site
```

Résultat :

- Ruff OK
- Ruff format OK
- Black OK
- 7 tests UI passés
- 36 tests ciblés passés
- `europe.html` généré
- `api/europe.json` généré
