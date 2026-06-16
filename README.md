# MeteoVoid

MeteoVoid est un outil Python expérimental de veille météo systémique. Il ne cherche pas seulement à afficher une prévision : il suit les signaux faibles, les trous de données, les anomalies amont, la cohérence spatiale et les indices de bascule convective.

Le projet reste non officiel. Il ne remplace pas l’IRM/KMI, MeteoAlarm, les radars, la foudre ou les consignes des autorités. Sa valeur est d’expliquer pourquoi un risque technique monte, quelles variables y contribuent, et quel niveau de confirmation externe existe réellement.

## Axes principaux

- détection d’anomalies dans des séries météo ;
- pipeline live avec Redis Streams et API HTTP ;
- veille Belgique avec stations, cartes, API statique et rapport Markdown ;
- scoring composite : chaleur, humidité, point de rosée, précipitations, pression, rafales, cohérence spatiale ;
- export d’artefacts auditables : JSON, CSV, GeoJSON, HTML, CAP XML et manifest de hashes ;
- séparation prudente entre signal interne, pré-alerte technique et confirmation externe.

## Installation

```bash
python -m pip install -U pip
pip install -e ".[dev]"
```

## CLI rapide

Un exemple de CSV est fourni dans `examples/sample_timeseries.csv`.

```bash
meteovoid scan examples/sample_timeseries.csv --time-col timestamp --value-col value --out report.json
cat report.json
```

## Pipeline live

MeteoVoid peut tourner en flux continu : observations dans Redis Streams, moteur live, rapports calculés, API HTTP.

```bash
docker compose up --build
```

Publier un flux synthétique :

```bash
docker compose run --rm meteovoid-live meteovoid simulate --sleep 0.01
```

Interroger le dernier rapport :

```bash
curl "http://localhost:8000/latest?station_id=DEMO_BE_0001&variable=wind_gust_ms"
```

Voir `docs/LIVE_PIPELINE.md`.

## Veille Belgique

Le workflow Belgique génère un dossier d’artefacts complet : rapport JSON, rapport Markdown, cartes HTML, fichiers CSV, API statique, état d’alerte technique, état des sources et manifest.

Exemple en mode démonstration hors ligne :

```bash
python tools/generate_belgium_alert_report.py --offline-demo --out-dir _out/belgium
python tools/build_belgium_public_site.py --report-dir _out/belgium --site-dir _site
```

Le vocabulaire public est volontairement prudent : MeteoVoid parle de veille, de pré-alerte technique ou de signal technique confirmé. Le mot « alerte » doit rester lié aux sources officielles ou à une confirmation externe forte clairement affichée.

## Développement

```bash
pre-commit install
pytest
ruff check src tests tools
mypy src
```

## Licence

MIT, voir `LICENSE`.
