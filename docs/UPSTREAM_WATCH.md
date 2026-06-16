# MeteoVoid — European Upstream Watch

Cette couche élargit la veille Belgique vers les zones amont européennes : nord de la France, Manche, Champagne-Ardenne, Luxembourg, sud des Pays-Bas, Rhénanie/Eifel et flux plus lointains depuis le golfe de Gascogne ou le sud-ouest de la France.

Objectif : ne plus lire seulement ce qui arrive déjà sur la Belgique, mais suivre la chaîne :

```text
source -> transport -> accumulation -> déclenchement -> propagation -> confirmation
```

## Fichiers ajoutés

```text
config/upstream_regions.yaml
config/european_radar_sources.yaml
src/meteovoid/belgium/upstream_watch.py
tools/generate_european_upstream_watch.py
```

## Sorties produites

```text
upstream_watch.json
upstream_watch_report.md
european_upstream_map.html
upstream_corridors.csv
european_radar_sources_status.json
```

Ces fichiers sont aussi copiés dans le site public et exposés dans l’API statique via `api/upstream.json`.

## Score de corridor

Chaque corridor possède un score composé de plusieurs signaux :

- activité amont ;
- alimentation humide ;
- alignement du flux avec la trajectoire du corridor ;
- organisation dynamique ;
- activité déjà présente sur la zone cible ;
- confirmation radar/foudre si elle est configurée.

Le score reste volontairement prudent : une masse d’air chaude et humide ne devient pas une alerte par magie. Sans confirmation radar/foudre ou signal officiel, le rapport reste un diagnostic amont.

## Fallback Open-Meteo

La couche peut utiliser Open-Meteo pour les flux et indices lorsque `--enable-upstream-openmeteo` est activé dans `generate_belgium_alert_report.py`, ou `--enable-openmeteo` dans l’outil dédié.

Variables utilisées :

- surface : température, point de rosée, humidité, précipitations, rafales, weather code, CAPE ;
- niveaux de pression : vent, direction du vent, température, point de rosée, humidité relative et hauteur géopotentielle à 925, 850, 700, 500 et 300 hPa.

Les indices calculés à partir des niveaux de pression sont indiqués comme proxys. Ils ne remplacent pas un produit radar Doppler ou une analyse convective professionnelle.

## Interface radar européenne

`config/european_radar_sources.yaml` prépare les connecteurs radar/foudre, mais ne simule rien.

Si une variable d’environnement comme `METEOVOID_OPERA_RADAR_JSON_URL`, `METEOVOID_KMI_RADAR_JSON_URL`, `METEOVOID_FRANCE_RADAR_JSON_URL`, `METEOVOID_KNMI_RADAR_JSON_URL`, `METEOVOID_DWD_RADAR_JSON_URL` ou `METEOVOID_EU_LIGHTNING_JSON_URL` n’est pas configurée, le statut reste :

```text
interface_only_unconfigured
```

Ce comportement est volontaire : MeteoVoid ne doit jamais inventer une confirmation radar.

## Commandes

Mode intégré, sans réseau, basé sur le rapport Belgique :

```bash
python tools/generate_belgium_alert_report.py --offline-demo --out-dir _out/belgium --no-history
```

Mode intégré avec fallback Open-Meteo :

```bash
python tools/generate_belgium_alert_report.py \
  --out-dir _out/belgium \
  --enable-upstream-openmeteo
```

Outil dédié :

```bash
python tools/generate_european_upstream_watch.py \
  --report-json _out/belgium/belgium_alert_report.json \
  --out-dir _out/belgium
```

Avec Open-Meteo :

```bash
python tools/generate_european_upstream_watch.py \
  --report-json _out/belgium/belgium_alert_report.json \
  --out-dir _out/belgium \
  --enable-openmeteo
```

## Limites publiques

- MeteoVoid ne remplace pas l’IRM/KMI, MeteoAlarm, OPERA, les autorités ou les services nationaux.
- Les cartes radar fines ne sont utilisées que si une source licite et configurée les fournit.
- Les flux Open-Meteo améliorent la lecture amont, mais ne donnent pas la précision d’un réseau radar Doppler intégré comme aux États-Unis.
- La sortie doit être lue comme une veille expérimentale, pas comme une alerte officielle.
