# Belgium Alert Watch, grosse mise à jour

Cette mise à jour transforme le module Belgique en veille plus robuste :

- ajout d’un état opérationnel séparé du score modèle
- ajout d’un score de confirmation externe renseignable manuellement
- ajout des champs IRM/KMI, MeteoAlarm, ESTOFEX, radar et foudre
- ajout de `source_status.json`
- ajout de `alert_state.json`
- ajout de `history.csv` append-only
- ajout de snapshots de runs dans le répertoire d’historique local
- ajout de `manifest.json` avec hashes SHA-256
- enrichissement du CSV avec les composantes du score
- enrichissement du Markdown avec tendance, confirmation externe et limites
- workflow GitHub Actions avec cache d’historique
- workflow manuel avec champs de confirmation externe
- carte Leaflet conservée comme carte principale
- SVG conservé en fallback hors ligne

Validation locale effectuée :

```bash
python -m py_compile tools/generate_belgium_alert_report.py
python -m compileall -q tools src
python -m ruff check tools/generate_belgium_alert_report.py
python -m black --check tools/generate_belgium_alert_report.py
PYTHONPATH=src python -m pytest -q tests/test_stations_config.py tests/test_config.py --no-cov
```

Test génération :

```bash
python tools/generate_belgium_alert_report.py \
  --stations config/stations_belgium.yaml \
  --out-dir /tmp/mv_big_final \
  --target-date 2026-06-19 \
  --offline-demo \
  --irm-warning-level orange \
  --metealarm-level yellow \
  --estofex-level level1 \
  --radar-confirmation weak \
  --lightning-confirmation nearby
```
