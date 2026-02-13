# MeteoVoid v0.3.0

## Ce qui change

### Détection et scoring (composite)
Le score live est maintenant composite, normalisé dans [0..1], basé sur plusieurs signaux légers :

- gaps et fraction de temps manquante
- volatilité (échelle robuste)
- outliers (robust z-score + IQR + règles métier hard_min / hard_max)
- flatline (plateaux)
- spikes (sauts brusques)
- drift (dérive lente)
- spatial (cohérence multi-stations, si plusieurs stations actives)
- multivar (cohérence multi-variables via corrélation simple, optionnel)

Le rapport /latest contient maintenant :
- `signals` : chaque signal dans [0..1]
- `contributions` : contribution pondérée au score final
- `score_meta` : poids et méta (span, méthodes d’outlier, etc.)

### API
Nouveaux endpoints :
- `/metrics` : métriques au format Prometheus
- `/history?station_id=...&variable=...&limit=...` : lecture récente depuis le stream de rapports (filtrage côté API)

### Entrées
Le scan offline accepte maintenant :
- CSV
- Parquet (si pyarrow/fastparquet installé)
- JSON / JSON Lines

### Docker Compose
Le `docker-compose.yml` est aligné avec l’ENTRYPOINT du container (commande = sous-commande meteovoid).

## Configuration

Dans `config/meteovoid_config_example.json` :
- `window_s` : fenêtre glissante par défaut ou par variable
- `score_weights` : pondérations des signaux
- `expected_range` : plage attendue (min/max) pour normalisation
- `hard_min` / `hard_max` : règles métier
- `flatline_min_run`, `flatline_eps`, `spike_k`, `outlier_z_thresh`, `outlier_iqr_k`, `drift_min_points`
- `multivar_peers` et `multivar_min_abs_corr`

## Notes

- Le score reste dans [0..1] pour rester compatible avec la validation CI.
- Les nouveaux signaux restent légers et sans dépendances ML par défaut.
