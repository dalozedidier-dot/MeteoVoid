# docs/LATEST_REPORT_CONTRACT.md

Ce document décrit le contrat attendu pour la réponse de l’API `GET /latest`.

## Champs racine

- `score` (number, 0..1) : score de variabilité ou instabilité sur la fenêtre.
- `state` (string) : `stable` | `transition` | `unstable`.
- `station_id` (string) : identifiant station.
- `variable` (string) : variable mesurée (ex: temperature_c, wind_ms, pressure_hpa).
- `stream_id` (string) : Redis Stream id du dernier point.
- `ts` (number) : timestamp du dernier point (epoch seconds).
- `ts_ingest` (number) : timestamp ingestion (epoch seconds).

## stats (object)

- `n_points` (int) : nombre de points dans la fenêtre.
- `min`, `max`, `mean`, `p95` (number) : statistiques fenêtre.
- `dt_median_s` (number) : médiane des deltas temporels.
- `gap_count` (int) : nombre de trous détectés (gap > seuil).
- `gap_max_s` (number) : plus grand trou.
- `gap_total_s` (number) : somme des trous.
- `missing_time_s` (number) : estimation du temps manquant.
- `missing_time_frac` (number, 0..1) : fraction de temps manquant sur la fenêtre.

## meteo (object)

- `interpretation` (string) : texte court exploitable humain.
- `flags` (list[string]) : drapeaux (ex: `watch`, `data_gap`, `noisy`, `flatline`).
- `severity` (string) : `low` | `medium` | `high`.
- D’autres champs peuvent exister, mais ceux ci dessus sont obligatoires.
