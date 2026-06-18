# MeteoVoid CI errors fix

Correctif basé sur les logs GitHub Actions `74828430788`, `74828436668` et `74828546414` et sur le dépôt uploadé `MeteoVoid-main (12).zip`.

## Corrections principales

- Suppression d’un résidu de merge dans `tools/build_belgium_public_site.py` : `claude/happy-ramanujan-xse58t`.
- Suppression d’un fragment `=======` resté dans le template JavaScript de la page pays.
- Ajout de l’import `sys` manquant dans `tools/build_belgium_public_site.py`.
- Ajout de `_write_country_pages(...)` pour générer les pages pays Europe et les API associées :
  - `spain.html`, `france.html`, `switzerland.html`, `netherlands.html`, `germany.html`, `denmark.html`
  - `api/country_spain.json`, `api/country_france.json`, etc.
- Publication du modèle Europe enrichi dans `api/europe.json`, avec les liens de pages pays et le registre radar maître.
- Suppression du double appel à `_write_europe_page(...)` qui écrasait le modèle Europe enrichi.
- Mise à jour du test `tests/test_belgium_weather_layers.py` pour tenir compte du moteur convectif natif : `proxy_plus_native_convective_fields`, `native_convective_parameters.json`, `native_convective_grid.csv`, `belgium_native_convective_map.html`.
- Formatage Ruff/Black des fichiers que la CI aurait ensuite signalés après correction de l’erreur de syntaxe.
- Suppression d’un import inutilisé `os` dans `fix_meteovoid_ci_contract_cleanup.py`.

## Fichiers modifiés

- `tools/build_belgium_public_site.py`
- `tests/test_belgium_weather_layers.py`
- `fix_meteovoid_ci_contract_cleanup.py`
- `apply_alert_state_contract_fields.py`
- `tools/belgium_convective_transition.py`
- `tools/belgium_early_warning.py`
- `tools/belgium_information_graph.py`
- `tools/belgium_system_watchdog.py`
- `tools/belgium_upstream_graph.py`
- `tools/belgium_validation_metrics.py`
- `tools/belgium_weather_layers.py`
- `src/meteovoid/belgium/upstream_watch.py`

## Contrôles effectués

```bash
python -m ruff check .
python -m ruff format --check .
python -m black --check --diff --workers 1 .
PYTHONPATH=src python -m pytest -q --no-cov tests/test_build_public_site.py tests/test_europe_country.py tests/test_native_convective_fields.py tests/test_european_national_radar.py tests/test_radar_stack.py tests/test_upstream_watch.py tests/test_opera_ord.py
PYTHONPATH=src python -m pytest -q --no-cov
PYTHONPATH=src python tools/generate_belgium_alert_report.py --offline-demo --out-dir /mnt/data/mv_errors_fix_out --no-history --target-date 2026-06-19 --official-forecast-signal severe_thunderstorms --heat-warning-active
PYTHONPATH=src python tools/build_belgium_public_site.py --report-dir /mnt/data/mv_errors_fix_out --site-dir /mnt/data/mv_errors_fix_site
```

## Résultat

- Ruff OK.
- Ruff format OK.
- Black OK.
- 51 tests ciblés OK.
- Full `pytest -q --no-cov` OK.
- Génération Belgique OK.
- Génération site public OK.
- `europe.html` généré.
- Pages pays Europe générées et liées.
- `api/europe.json` généré avec le modèle enrichi.
