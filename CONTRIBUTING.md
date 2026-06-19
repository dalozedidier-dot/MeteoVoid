# Contribuer à MeteoVoid

MeteoVoid est un prototype météo non officiel. Les contributions doivent garder une séparation claire entre observation réelle, prévision modèle, affichage visuel et interprétation MeteoVoid.

## Workflow recommandé

1. Forker le dépôt.
2. Créer une branche courte : `feat/...`, `fix/...`, `docs/...`.
3. Installer l’environnement dev :

```bash
python -m pip install -U pip
python -m pip install -e ".[dev,live,viz]"
pre-commit install
```

4. Lancer les contrôles avant commit :

```bash
make clean
python -m ruff check .
python -m ruff format --check .
python -m black --check .
python -m mypy --config-file=pyproject.toml src
pytest -q
```

5. Garder des commits petits et auditables.

## Conventions de code

- Formatage : `ruff format` + `black`.
- Lint : `ruff check`.
- Typage : `mypy` sur `src`.
- Tests : `pytest` avec couverture minimale conservée.
- Pas de fichiers générés dans le repo : `__pycache__`, `.pytest_cache`, `_ci_out`, `_site`, caches radar, etc.

## Règles météo

- Ne pas présenter une prévision comme une observation.
- Ne pas transformer RainViewer en preuve radar machine.
- Ne pas inventer CAPE, CIN, cisaillement, foudre ou satellite si le champ est absent.
- Les alertes publiques doivent rester prudentes et non officielles.
- Les sources officielles IRM/KMI/MeteoAlarm gardent priorité dans la communication publique.

## Pipeline live

Le schéma Redis Streams est documenté dans `docs/LIVE_STREAM_SCHEMA.md`.

Avant de modifier le live worker :

```bash
pytest tests/test_stream.py tests/test_stream_processing.py -q
```

Pour tester en local :

```bash
docker compose --profile demo up --build
```

## Interface Storm-scope

Les pages publiques sont dans `stormscope/web/`. Toute nouvelle page doit :

- charger `assets/app.css`, `assets/app.js`, `assets/site-api-adapter.js` et `assets/alert-watch-panels.js` ;
- fonctionner avec `api/watch.json` quand il est présent ;
- garder un fallback honnête si l’API est absente ;
- rester accessible au clavier.
