# Déploiement, monitoring et staging

## Staging

Cible recommandée :

- `staging.ori-c.be` pour les pages générées par GitHub Actions ;
- `ori-c.be` pour la production ;
- publication staging après tests unitaires + build site ;
- publication production uniquement après validation manuelle ou tag.

## Tests end-to-end à ajouter

- ouverture `index.html`, `europe.html`, `bulletin.html`, `expert.html` ;
- vérification que Leaflet reçoit une taille non nulle ;
- vérification que `api/watch.json`, `api/latest.json`, `api/data_quality.json` sont lisibles ;
- vérification que les panneaux Belgium Alert Watch s’affichent.

## Monitoring Prometheus

L’endpoint `/metrics` expose déjà des métriques Prometheus. À surveiller :

- `meteovoid_latest_age_seconds` ;
- `meteovoid_latest_score` ;
- `meteovoid_stations_by_severity` ;
- `meteovoid_out_stream_len` ;
- `meteovoid_silent_stations` ;
- `meteovoid_open_alerts`.

## Grafana

Tableaux conseillés :

- santé du pipeline live ;
- latence des observations ;
- nombre d’alertes ouvertes ;
- longueur des streams Redis ;
- top stations par score ;
- taux de DLQ.
