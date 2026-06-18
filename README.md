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

### Pages de suivi par pays

Chaque pays suivi (Espagne, France, Suisse, Pays-Bas) dispose maintenant d’une page dédiée, au même niveau que la page Belgique : `spain.html`, `france.html`, `switzerland.html`, `netherlands.html`. Elles sont générées par `tools/build_belgium_public_site.py` et reliées depuis la page Europe.

Chaque page expose :

- la **détection MeteoVoid par station** via le même moteur générique (`meteovoid.scoring.compute_composite_score`) que la Belgique : volatilité, à-coups et dérive des rafales, complétés de proxys convectif et thermique ;
- le **réseau radar national réel** (positions physiques des radars AEMET, Météo-France, MeteoSwiss, KNMI) affiché sur une carte Leaflet interactive, avec la couche **RainViewer** animée en direct ;
- un statut de source **honnête** : un flux radar national n’est promu en preuve machine que si sa clé est configurée et qu’une trame est lisible.

Le registre des stations et des sites radar est dans `config/european_country_radar_sites.yaml`.

Mode hors-ligne déterministe (par défaut, reproductible pour la CI et GitHub Pages) :

```bash
python tools/build_belgium_public_site.py --report-dir _out/belgium --site-dir _site
```

Mode données réelles (Open-Meteo pour les observations, clés nationales pour le radar) :

```bash
export METEOVOID_ENABLE_LIVE_COUNTRY=1
export AEMET_API_KEY=...        # Espagne (radar national)
export METEOFRANCE_API_KEY=...  # France (radar national)
export KNMI_API_KEY=...         # Pays-Bas (radar national)
python tools/build_belgium_public_site.py --report-dir _out/belgium --site-dir _site
```

Sans clé, la carte affiche quand même les sites radar réels et RainViewer, et signale `interface_ready_awaiting_national_key`.

### Registre maître des sources radar européennes

`config/european_radar_master_sources.yaml` est la référence unique des fournisseurs radar (8 sources), exposée de façon **sanitisée** dans `api/radar_sources.json` et sur l’onglet Sources de la page Europe. Pour chaque source : authentification, quota documenté, formats, niveau de preuve, attribution et **priorité opérationnelle**.

Ordre de priorité : **MeteoGate OPERA ORD** (pivot Europe) → **KNMI** (Pays-Bas) → **Météo-France** → **AEMET** (Espagne) → **MeteoSwiss** → **DWD** (Allemagne) → **RainViewer** (visuel) → **DMI** (Danemark).

Contrat de sécurité : les clés (`AEMET_API_KEY`, `METEOFRANCE_API_KEY`, `KNMI_API_KEY`, `METEOGATE_API_KEY`) restent dans les **secrets GitHub Actions** ou un `.env` local. Le site public ne reçoit **jamais** une valeur de clé, seulement des booléens `configured`/`enabled` et des statuts. Voir `.env.example` pour le schéma complet (clés, interrupteurs `*_ENABLED`, garde-fous de quota/cache/attribution).

### Champs convectifs natifs, validation et preuve machine

MeteoVoid sépare et **étiquette honnêtement** trois niveaux de rigueur, par pays :

- **Couche convective** : en mode live, le moteur lit les champs **natifs** Open‑Meteo (CAPE, CIN, Lifted Index, et cisaillement dérivé des vents par niveau de pression) ; hors‑ligne, il reste un **proxy** explicitement étiqueté (`convective_basis: proxy`). La couche n’est jamais présentée comme une carte modèle si elle est un proxy.
- **Validation historique** : tant qu’aucun événement vérifié n’est fourni (`config/<pays>_verified_storm_events.csv`), le statut reste `needs_verified_events` et Brier/POD/FAR/CSI restent **non calculés** (`null`), jamais inventés.
- **Preuve radar machine** : `0` métrique tant qu’aucun fichier radar lisible n’est fourni. En configurant une clé/OPERA ORD et un fichier via `METEOVOID_RADAR_FILE_<PAYS>` (ODIM HDF5 / GeoTIFF), MeteoVoid calcule des métriques et **promeut** la source en preuve machine. RainViewer reste une couche visuelle, jamais une preuve.
