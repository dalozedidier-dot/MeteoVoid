# Stratégie de fallback des sources météo

MeteoVoid sépare strictement trois niveaux :

1. **Observation réelle** : radar machine, station, foudre, satellite ou source officielle exploitable.
2. **Prévision modèle** : Open-Meteo / ECMWF / ICON / AROME / HARMONIE selon disponibilité.
3. **Affichage visuel** : tuiles radar ou cartes destinées à la lecture humaine, non utilisées comme preuve machine.

## Ordre de priorité Belgique

| Domaine | Priorité |
|---|---|
| Avertissements officiels | IRM/KMI, MeteoAlarm si disponibles |
| Radar machine | OPERA ORD ou source nationale lisible |
| Radar visuel | RainViewer, seulement comme overlay |
| Variables météo | stations réelles, puis Open-Meteo best match |
| Champs convectifs | champs natifs disponibles, sinon champ absent |
| Carte administrative | geo.be/CadGIS/Statbel, puis fallback simplifié documenté |

## Règles non négociables

- Un champ absent reste absent.
- Une couche RainViewer ne devient jamais une confirmation radar machine.
- OPERA ORD n’est considéré comme preuve que si un fichier radar est réellement lu et métriqué.
- Les bulletins publics mentionnent que MeteoVoid est non officiel.

## Cache radar

Les métadonnées radar peuvent être mises en cache pour éviter de frapper trop souvent les endpoints publics :

```bash
METEOVOID_RADAR_CACHE_DIR=.meteovoid_cache/radar
METEOVOID_RADAR_CACHE_TTL_SECONDS=300
```

Le TTL recommandé est de 5 minutes pour les métadonnées radar/nowcast.
