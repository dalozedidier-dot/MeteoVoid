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
pip install -e ".[dev,live,viz]"
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
docker compose run --rm meteovoid-simulate
```

Interroger le dernier rapport :

```bash
curl "http://localhost:8000/latest?station_id=DEMO_BE_0001&variable=wind_gust_ms"
```

Voir `docs/LIVE_PIPELINE.md`.

### Sécurité API optionnelle

Les endpoints de lecture restent ouverts pour les dashboards. Les endpoints d’écriture (`POST /thresholds`, `POST /alerts/{id}/ack`, `resolve`, `ignore`) sont protégés dès que `METEOVOID_API_TOKEN` est défini.

```bash
export METEOVOID_API_TOKEN="change-me"
curl -H "Authorization: Bearer $METEOVOID_API_TOKEN" http://localhost:8000/thresholds
```

## Veille Belgique

Le workflow Belgique génère un dossier d’artefacts complet : rapport JSON, rapport Markdown, cartes HTML, fichiers CSV, API statique, état d’alerte technique, état des sources et manifest.

Exemple en mode démonstration hors ligne :

```bash
python tools/generate_belgium_alert_report.py --offline-demo --out-dir _out/belgium
python tools/build_belgium_public_site.py --report-dir _out/belgium --site-dir _site
```

Le vocabulaire public est volontairement prudent : MeteoVoid parle de veille, de pré-alerte technique ou de signal technique confirmé. Le mot « alerte » doit rester lié aux sources officielles ou à une confirmation externe forte clairement affichée.

## Europe amont / Upstream Watch

MeteoVoid peut générer une couche amont européenne pour suivre les régions sources et les couloirs de propagation vers la Belgique. Cette couche ne simule pas de radar : les interfaces radar/foudre européennes restent optionnelles et ne sont utilisées que si un endpoint licite est configuré dans l’environnement.

Sorties principales :

```text
upstream_watch.json
upstream_watch_report.md
european_upstream_map.html
upstream_corridors.csv
european_radar_sources_status.json
```

Mode intégré, sans accès réseau :

```bash
python tools/generate_belgium_alert_report.py --offline-demo --out-dir _out/belgium
```

Mode intégré avec fallback Open-Meteo pour les flux et niveaux de pression :

```bash
python tools/generate_belgium_alert_report.py --out-dir _out/belgium --enable-upstream-openmeteo
```

Outil dédié :

```bash
python tools/generate_european_upstream_watch.py \
  --report-json _out/belgium/belgium_alert_report.json \
  --out-dir _out/belgium
```

Voir `docs/UPSTREAM_WATCH.md`.

## Méthodologie courte

MeteoVoid sépare trois niveaux de lecture :

1. le signal interne, calculé à partir des variables météo disponibles ;
2. la confirmation externe, radar, foudre, IRM/KMI, MeteoAlarm ou ESTOFEX quand ces sources sont renseignées ;
3. le niveau public, volontairement prudent et toujours non officiel.

Le modèle distingue désormais le stress thermique, le potentiel convectif et les indices convectifs natifs lorsqu’ils sont disponibles. Sans CAPE, CIN, cisaillement ou SRH, MeteoVoid signale explicitement que le diagnostic reste un proxy.

Voir `docs/METHODOLOGY.md` pour le détail.

## Développement

```bash
pre-commit install
pytest
ruff check src tests tools
mypy src
```

## Licence

MIT, voir `LICENSE`.

## OPERA ORD radar européen optionnel

MeteoVoid prépare une voie radar machine via OPERA ORD / MeteoGate, séparée de l’affichage RainViewer.

Mode offline, sans accès réseau :

```bash
python tools/fetch_opera_ord.py --out-dir _out/opera
```

Mode live, sans téléchargement :

```bash
python tools/fetch_opera_ord.py \
  --enable \
  --config config/opera_ord.yaml \
  --out-dir _out/opera \
  --datetime "2026-06-17T00:00Z/2026-06-17T01:00Z"
```

Mode live avec téléchargement des fichiers disponibles :

```bash
python tools/fetch_opera_ord.py \
  --enable \
  --download \
  --config config/opera_ord.yaml \
  --out-dir _out/opera \
  --datetime "2026-06-17T00:00Z/2026-06-17T01:00Z"
```

RainViewer reste une couche visuelle. OPERA ORD devient la voie radar machine lorsque les métadonnées, liens et fichiers radar sont réellement accessibles. Si les fichiers radar fins sont absents, MeteoVoid l’indique explicitement.

### Radars nationaux Europe

MeteoVoid peut maintenant suivre des interfaces radar nationales pour l’Espagne, la France, la Suisse et les Pays-Bas, en complément de RainViewer et OPERA ORD.

```bash
python tools/generate_european_national_radar.py --out-dir _out/belgium
python tools/generate_radar_stack.py --out-dir _out/belgium --country-radar-file france:/tmp/frame.npy
```

Voir `docs/EUROPEAN_NATIONAL_RADARS.md` pour la logique d’intégration, les clés API possibles et la règle de prudence : aucune source nationale n’est traitée comme preuve machine tant qu’un fichier radar n’est pas lisible et métriqué.
