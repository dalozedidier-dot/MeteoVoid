# MeteoVoid Patch A – multi-variables, seuils configurables, imputation, alertes, mini-dashboard

## 1) /latest devient utilisable sans query params
- `/latest` sans paramètres retourne le report le plus récent (toutes stations/variables).
- `/latest?station_id=...` retourne un bundle station:
  - `variables`: mapping variable -> report
  - `global`: score/state global (moyenne pondérée) + thresholds utilisés
- `/latest?station_id=...&variable=...` retourne le report variable (comme avant).

## 2) Config JSON optionnelle (sans nouvelle dépendance)
Env var:
- `METEOVOID_CONFIG_PATH=/path/to/config.json`

Tu peux définir:
- thresholds par station/variable: stable_threshold, unstable_threshold, watch_threshold, alert_threshold
- max_gap_s par variable
- imputation: impute_mode (none|ffill|mean), use_imputed_for_score, max_imputed_frac, max_impute_points
- weight par variable pour le global station.

## 3) Imputation basique + flags
Quand il y a des gaps au-dessus du seuil:
- insertion de points (ffill ou mean)
- stats: imputed_points, imputed_frac, score_raw/score_imputed
- flags: imputed, imputation_high

## 4) Alertes webhook (optionnelles)
Env var:
- `METEOVOID_ALERT_WEBHOOK_URL=https://...`
- `METEOVOID_ALERT_MIN_SEVERITY=high` (par défaut)
- `METEOVOID_ALERT_ALWAYS_ON_FLAG=alert` (par défaut)

## 5) Dashboard minimal
- `/dashboard` liste les stations/variables et donne des liens directs vers `/latest`.

## Fichiers patchés
- `src/meteovoid/api.py`
- `src/meteovoid/live.py`
- `src/meteovoid/stream.py`
- `src/meteovoid/config.py` (nouveau)
- `src/meteovoid/alerts.py` (nouveau)
- tests additionnels sous `tests/`
- exemple config: `config/meteovoid_config_example.json`
