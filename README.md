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
