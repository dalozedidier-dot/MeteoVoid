# MeteoVoid TEST NATIVE MODE FIX

## Cause CI

Le nouveau run CI passe `pre-commit` puis échoue dans `pytest` sur :

```text
FAILED tests/test_belgium_weather_layers.py::test_weather_layers_outputs_are_written
AssertionError: assert 'proxy_plus_native_convective_fields' == 'derived_from_station_forecasts'
```

Le moteur convectif natif fonctionne : le test était resté aligné sur l'ancien contrat proxy seulement.

## Correctif

Fichier modifié :

```text
tests/test_belgium_weather_layers.py
```

Le test attend désormais le nouveau mode :

```text
proxy_plus_native_convective_fields
```

Il vérifie aussi les artefacts natifs :

```text
belgium_native_convective_map.html
native_convective_grid.csv
native_convective_parameters.json
```

Et les champs du contrat :

```text
native_convective_contract = native_convective_fields_optional_v1
cape_integrated = True
shear_integrated = False
srh_integrated = False
max_native_convective_score_grid != None
```

## Contrôles effectués

```bash
python -m py_compile tests/test_belgium_weather_layers.py
PYTHONPATH=src:. python -m pytest -q --no-cov tests/test_belgium_weather_layers.py tests/test_native_convective_fields.py tests/test_build_public_site.py tests/test_european_national_radar.py tests/test_radar_stack.py tests/test_upstream_watch.py tests/test_opera_ord.py
PYTHONPATH=src python tools/generate_belgium_alert_report.py --offline-demo --out-dir /mnt/data/mv_748666_fix_out --no-history --target-date 2026-06-19 --official-forecast-signal severe_thunderstorms --heat-warning-active
PYTHONPATH=src:. python tools/build_belgium_public_site.py --report-dir /mnt/data/mv_748666_fix_out --site-dir /mnt/data/mv_748666_fix_site
PYTHONPATH=src python tools/validate_belgium_contracts.py /mnt/data/mv_748666_fix_out
PYTHONPATH=src python tools/validate_belgium_public_latest.py /mnt/data/mv_748666_fix_out/belgium_public_latest.json
```

Résultat :

```text
43 tests ciblés passés
génération Belgique OK
site public OK
contrats Belgique OK
belgium_public_latest OK
```

Le full `pytest -q --no-cov` n'a pas été lancé jusqu'au bout dans le sandbox parce que la dépendance `hypothesis` n'y est pas installée. Dans GitHub Actions, elle est installée, et le log montre déjà que la couverture dépassait le seuil de 85 %. Le blocage restant était donc uniquement ce test obsolète.
