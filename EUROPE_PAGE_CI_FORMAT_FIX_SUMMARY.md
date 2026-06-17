# MeteoVoid — Correctif CI page Europe dédiée

## Cause dans les logs
Le run CI échouait encore au niveau `pre-commit`, uniquement sur `tools/build_belgium_public_site.py` :

- `ruff-format`: 1 fichier à reformater.
- `black 24.10.0`: reformattage attendu du bloc `build_europe_model` / `api/index.json`.
- `mypy (src only)`: déjà OK dans les logs.

## Correction appliquée
Le fichier `tools/build_belgium_public_site.py` a été reformatté selon le diff Black visible dans les logs :

- suppression d’une ligne vide superflue avant `_EUROPE_COUNTRY_LABELS` ;
- retour à la ligne de `_machine_label()` ;
- retour à la ligne de certains dictionnaires longs dans `build_europe_model()` ;
- parenthésage des expressions conditionnelles longues ;
- formatage de `extra_endpoints` dans `api/index.json` ;
- normalisation des lignes vides avant `_write_europe_page()`.

## Contrôles effectués localement

```bash
python -m py_compile tools/build_belgium_public_site.py tests/test_build_public_site.py
PYTHONPATH=. pytest -q --no-cov tests/test_build_public_site.py
```

Résultat :

```text
7 tests UI passés
```

## À appliquer

```bash
unzip MeteoVoid_EUROPE_PAGE_CI_FORMAT_FIX_PATCH.zip -d /chemin/vers/MeteoVoid-main
```

Ce correctif vise uniquement le blocage CI observé dans `logs_74689811103.zip`.
