# Ingestion Europe (Open-Meteo)

Objectif
Récupérer des conditions météo "current" via Open-Meteo pour une liste de stations, puis publier des observations dans Redis Streams.

## 1) Config stations

Fichier: config/stations_europe.yaml

Champs requis par station:
- id: identifiant unique (ex: BE_UCCLE)
- lat, lon: coordonnées
- source: openmeteo
- variables: noms Open-Meteo (current)

Variables Open-Meteo utiles:
- wind_speed_10m
- wind_gusts_10m
- temperature_2m
- surface_pressure

## 2) Lancer en local

Avec docker compose:
- redis
- meteovoid-live
- meteovoid-api
- meteovoid-ingest-europe

Commande:
docker compose up -d redis meteovoid-live meteovoid-api meteovoid-ingest-europe

Pour un test one-shot:
docker compose run --rm meteovoid-ingest-europe python -m meteovoid.ingest_europe --config config/stations_europe.yaml --once

## 3) Streams

Par défaut, publication dans:
- meteovoid:observations

Option --per-stream:
- meteovoid:observations:<station_id>:<variable>

## 4) Scaling

Redis Streams ne supporte pas la lecture par pattern.
Pour scaler, il faut distribuer la lecture:
- plusieurs workers, chacun avec une liste explicite de streams
- ou garder un stream unique meteovoid:observations

Ce patch garde le stream unique par défaut (stable, simple).

## 5) Bulletin Europe

Le bulletin peut être agrégé à partir des /latest par station/variable.
Si ton API expose /stations, le script tools/generate_bulletin.py peut lister automatiquement les couples station/variable.
Sinon, il peut lire config/stations_europe.yaml en fallback (option --stations-config).
