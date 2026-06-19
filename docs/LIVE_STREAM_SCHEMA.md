# Schéma Redis Streams MeteoVoid

MeteoVoid utilise deux streams principaux :

- `meteovoid:observations` : observations entrantes.
- `meteovoid:reports` : rapports calculés par le moteur live.
- `meteovoid:observations:dlq` par défaut : dead letter queue des messages impossibles à traiter.

## Observation entrante

Champs requis :

| Champ | Type | Exemple | Rôle |
|---|---:|---|---|
| `station_id` | string | `BE_UCCLE` | identifiant stable de station |
| `variable` | string | `temperature_2m` | grandeur mesurée |
| `value` | number/string | `27.4` | valeur numérique |
| `ts` | epoch seconds ou ISO | `1781881200` | timestamp observation |

Champs optionnels :

| Champ | Type | Rôle |
|---|---:|---|
| `retry_count` / `attempts` | integer | nombre de tentatives amont avant DLQ |
| `source` | string | fournisseur ou pipeline d’origine |
| `quality` | string | annotation fournisseur |

## Rapport sortant

Le worker publie dans `meteovoid:reports` :

| Champ | Type | Rôle |
|---|---:|---|
| `station_id` | string | station concernée |
| `variable` | string | variable concernée |
| `payload` | JSON string | rapport complet MeteoVoid |

Le `payload` contient notamment :

- `score`, `state`, `signals`, `contributions` ;
- `signals.flatline` pour les plateaux/capteurs bloqués ;
- `signals.spatial` pour les incohérences inter-stations ;
- `stats.spatial_context` avec `peer_count`, `peer_median`, `peer_mean`, `peer_std`, `peer_z` quand assez de pairs existent ;
- `meteo.flags` et `meteo.interpretation` pour l’explication humaine.

## Dead letter queue

Un message invalide ou une exception de traitement est publié dans `METEOVOID_DLQ_STREAM`, ou par défaut `<in_stream>:dlq`.

Champs DLQ :

| Champ | Type | Rôle |
|---|---:|---|
| `source_stream` | string | stream d’origine |
| `source_id` | string | ID Redis du message source |
| `reason` | string | `invalid_payload` ou `processing_exception` |
| `payload` | JSON string | message source, erreur, retry_count, max_retries |

Variable utile :

```bash
METEOVOID_DLQ_STREAM=meteovoid:observations:dlq
METEOVOID_MAX_RETRIES=3
```
