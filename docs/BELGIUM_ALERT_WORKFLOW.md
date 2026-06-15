# MeteoVoid Belgium Alert Watch

Ce workflow ajoute une couche de veille météo orientée Belgique au-dessus de MeteoVoid.

Il ne remplace pas les avertissements officiels. Il produit un rapport interne de surveillance qui doit être comparé avec l’IRM/KMI, MeteoAlarm, ESTOFEX, le radar et la foudre avant toute communication publique.

## Fichiers

- `config/stations_belgium.yaml` : grille belge et frontalière.
- `tools/generate_belgium_alert_report.py` : récupération des prévisions et scoring de risque.
- `.github/workflows/belgium_alert_watch.yml` : workflow GitHub Actions planifié.

## Sorties

Le workflow écrit ces fichiers dans `_ci_out/belgium_alert/` :

- `belgium_alert_report.json`
- `belgium_alert_report.md`
- `risk_by_station.csv`

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
