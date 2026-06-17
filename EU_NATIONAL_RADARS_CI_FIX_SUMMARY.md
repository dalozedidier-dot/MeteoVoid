# MeteoVoid — EU National Radars CI fix

Correctif ciblé après les logs `logs_74684184921.zip`.

## Cause du blocage

La CI échouait dans `Lint (pre-commit)` :

- `black 24.10.0` voulait reformater 4 fichiers ;
- `mypy` remontait 11 erreurs de narrowing dans `src/meteovoid/belgium/european_national_radar.py` ;
- `end-of-file-fixer` ajoutait une fin de ligne à `european_national_radar_map.html`.

## Fichiers corrigés

- `src/meteovoid/belgium/european_national_radar.py`
- `src/meteovoid/belgium/radar_stack.py`
- `tools/build_belgium_public_site.py`
- `tools/generate_belgium_alert_report.py`
- `european_national_radar_map.html`

## Corrections appliquées

- Typage explicite de `runtime`, `countries_cfg`, `sources_raw` et `outputs` pour satisfaire `mypy`.
- Reformattage des expressions longues selon le style attendu par Black.
- Ajout de la ligne finale manquante au fichier HTML généré committé.

## Contrôles effectués dans le sandbox

```bash
python -m compileall -q src tools tests
python -m pytest -q --no-cov tests/test_european_national_radar.py tests/test_radar_stack.py tests/test_build_public_site.py tests/test_upstream_watch.py tests/test_opera_ord.py
PYTHONPATH=src python tools/generate_belgium_alert_report.py --offline-demo --out-dir /mnt/data/meteo_eu_national_cifix_out --no-history --target-date 2026-06-19 --official-forecast-signal severe_thunderstorms --heat-warning-active
PYTHONPATH=src python tools/build_belgium_public_site.py --report-dir /mnt/data/meteo_eu_national_cifix_out --site-dir /mnt/data/meteo_eu_national_cifix_site
PYTHONPATH=src python tools/validate_belgium_contracts.py /mnt/data/meteo_eu_national_cifix_out
PYTHONPATH=src python tools/validate_belgium_public_latest.py /mnt/data/meteo_eu_national_cifix_out/belgium_public_latest.json
```

Résultat : 34 tests ciblés passent, génération Belgique OK, site public OK, contrats OK.

Note : `ruff`, `black` et `mypy` ne sont pas installés dans ce sandbox ; le correctif reprend précisément les reformattages et les erreurs signalés par les logs GitHub Actions.
