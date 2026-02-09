# MeteoVoid

MeteoVoid est un squelette de projet Python pour détecter des zones de silence et des anomalies amont dans des séries météo.
L'idée est de produire des rapports simples, auditables, puis d'ouvrir la porte à des graphes et à des signaux plus complexes.

## Installation

```bash
python -m pip install -U pip
pip install -e ".[dev]"
```

## Exemple rapide

Un exemple de CSV est fourni dans `examples/sample_timeseries.csv`.

```bash
meteovoid scan examples/sample_timeseries.csv --time-col timestamp --value-col value --out report.json
cat report.json
```

## Développement

```bash
pre-commit install
pytest -q
```

## Scripts GitHub

Le dossier `scripts/` contient des scripts optionnels pour créer un dépôt GitHub via `gh` et pousser un commit initial.

1. `scripts/create_remote_repo.sh`
2. `scripts/add_git_commit_tag.sh`

## Licence

MIT, voir `LICENSE`.


## Release (GitHub + PyPI)

### GitHub Release
- Sur un tag `v*` : la release est créée automatiquement.
- En manuel (Actions > Release) : indique le tag dans l'input `tag`.

### PyPI
Deux options :

1) API token (simple)
- Ajoute un secret GitHub `PYPI_API_TOKEN` (token PyPI)
- Le workflow publie automatiquement sur tag.

2) Trusted Publishing (OIDC)
- Configure un Trusted Publisher sur PyPI pour ce repo + environnement `pypi`
- Ajoute une variable de repo `PYPI_TRUSTED_PUBLISHING=true` (pour activer la publication sur tags)
