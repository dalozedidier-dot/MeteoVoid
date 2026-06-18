# MeteoVoid TEST FORMAT FIX

## Cause détectée dans les logs

Le run `74868738342` bloque uniquement dans `pre-commit`.

- `ruff-format` veut reformater `tests/test_belgium_weather_layers.py`
- `black 24.10.0` veut reformater le même fichier
- `mypy (src only)` passe

Aucune logique météo, radar, Europe ou site public n'est en cause.

## Fichier corrigé

- `tests/test_belgium_weather_layers.py`

## Nature de la correction

Reformatage Black/Ruff du test ajouté pour le moteur convectif natif :

- `json.loads(...)` sur une ligne, conformément à Black avec `line-length = 100`
- assertion `native_convective_contract` sur une ligne
- aucun changement de logique de test

## Contrôles effectués

```bash
python -m py_compile tests/test_belgium_weather_layers.py
PYTHONPATH=src:. python -m pytest -q --no-cov tests/test_belgium_weather_layers.py tests/test_native_convective_fields.py tests/test_build_public_site.py tests/test_european_national_radar.py tests/test_radar_stack.py tests/test_upstream_watch.py tests/test_opera_ord.py
PYTHONPATH=src python tools/generate_belgium_alert_report.py --offline-demo --out-dir /mnt/data/mv_748687_fix_out --no-history --target-date 2026-06-19 --official-forecast-signal severe_thunderstorms --heat-warning-active
PYTHONPATH=src:. python tools/build_belgium_public_site.py --report-dir /mnt/data/mv_748687_fix_out --site-dir /mnt/data/mv_748687_fix_site
PYTHONPATH=src python tools/validate_belgium_contracts.py /mnt/data/mv_748687_fix_out
PYTHONPATH=src python tools/validate_belgium_public_latest.py /mnt/data/mv_748687_fix_out/belgium_public_latest.json
```

## Résultat

- 43 tests ciblés passés
- génération Belgique OK
- génération site public OK
- contrats Belgique OK
- `belgium_public_latest.json` OK
