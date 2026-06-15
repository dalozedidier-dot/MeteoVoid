# MeteoVoid Belgium Alert Watch

Ce workflow ajoute une couche de veille météo orientée Belgique au-dessus de MeteoVoid.

Il ne remplace pas les avertissements officiels. Il produit un rapport interne de surveillance qui doit être comparé avec l’IRM/KMI, MeteoAlarm, ESTOFEX, le radar et la foudre avant toute communication publique.

## Ce qui est récupéré en direct

En mode normal, le script interroge l’API Open-Meteo Forecast au moment de l’exécution.

Le rapport indique explicitement :

- `data_mode`: `live_forecast_api` lorsque les prévisions sont récupérées en ligne.
- `source_type`: `model_forecast` pour rappeler qu’il s’agit de prévisions modèle.
- `source_detail`: `Open-Meteo Forecast API`.
- `integrations`: état des sources externes non encore branchées.

En mode `--offline-demo`, aucune donnée réelle n’est récupérée. Le rapport affiche alors :

- `data_mode`: `offline_demo`.
- `source_type`: `synthetic_demo`.

## Fichiers

- `config/stations_belgium.yaml` : grille belge et frontalière.
- `tools/generate_belgium_alert_report.py` : récupération des prévisions, scoring de risque et génération des cartes.
- `.github/workflows/belgium_alert_watch.yml` : workflow GitHub Actions planifié.

## Sorties

Le workflow écrit ces fichiers dans `_ci_out/belgium_alert/` :

- `belgium_alert_report.json`
- `belgium_alert_report.md`
- `risk_by_station.csv`
- `risk_by_station.geojson`
- `belgium_alert_map.svg`
- `belgium_alert_map.html`

La carte SVG/HTML est volontairement statique et hors ligne. Elle ne dépend pas de tuiles externes. Les points sont placés selon la latitude et la longitude des stations. La couleur représente la sévérité, et la taille du cercle représente le score.

## Niveaux de sévérité

- `normal` : aucun signal fort dans les variables disponibles.
- `watch` : la configuration mérite une surveillance rapprochée.
- `medium` : comparer avec les avertissements officiels et l’évolution radar.
- `high` : préparer un message clair si les signaux officiels ou le nowcast confirment.
- `alert` : publier seulement après confirmation externe.

## Composantes du risque

Le score combine actuellement :

- chaleur
- humidité et point de rosée
- probabilité de précipitation ou précipitation horaire
- rafales de vent
- baisse de pression sur six heures
- code météo Open-Meteo

Le score reste volontairement prudent. Il sert à produire une veille, pas un avertissement officiel.

## Lancement manuel

```bash
python tools/generate_belgium_alert_report.py \
  --stations config/stations_belgium.yaml \
  --target-date next-friday \
  --out-dir _ci_out/belgium_alert
```

Pour vérifier localement sans accès réseau :

```bash
python tools/generate_belgium_alert_report.py \
  --stations config/stations_belgium.yaml \
  --target-date next-friday \
  --out-dir _ci_out/belgium_alert \
  --offline-demo
```

## Webhook

Créer un secret de dépôt nommé `METEOVOID_ALERT_WEBHOOK_URL` pour envoyer un payload JSON compact lorsque la sévérité atteint le minimum configuré.

Le workflow ne tombe pas en erreur si le webhook est absent.

## Prochaine couche à brancher

La structure JSON est déjà prête pour ajouter les sources externes suivantes :

- avertissements officiels IRM/KMI
- MeteoAlarm
- ESTOFEX
- radar pluie
- détection foudre

Quand une source sera réellement intégrée, le champ correspondant dans `integrations` devra passer à `true`, et le calcul du score pourra intégrer une composante externe distincte du modèle Open-Meteo.
