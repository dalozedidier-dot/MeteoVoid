# MeteoVoid build-pages fix

Correctif ciblé pour les logs `logs_74829749170.zip`.

## Cause dans les logs

Le workflow GitHub Pages échouait pendant l'étape :

```bash
python tools/build_belgium_public_site.py --report-dir _ci_out/belgium_alert --site-dir _site
```

Erreur visible :

```text
File "tools/build_belgium_public_site.py", line 2203
    country_links = _write_country_pages(site_dir)
IndentationError: unexpected indent
```

## Corrections appliquées

- Suppression du fragment parasite `claude/happy-ramanujan-xse58t`.
- Suppression du fragment de merge `=======` resté dans le template de page pays.
- Ajout de l'import `sys` manquant avant l'injection de `src/` dans `sys.path`.
- Ajout de `_write_country_pages(site_dir)` pour générer les pages pays Europe et leurs API JSON.
- Correction de `build_index()` pour :
  - générer `index.html`,
  - publier `api/radar_sources.json`,
  - générer les pages pays,
  - enrichir `api/europe.json` avec `country_pages` et `master_sources`,
  - générer `europe.html`,
  - générer `methodology.html`.
- Formatage Ruff/Black de deux scripts racine qui bloquaient `ruff check .` / `ruff format --check .`.

## Fichiers modifiés

```text
tools/build_belgium_public_site.py
apply_alert_state_contract_fields.py
fix_meteovoid_ci_contract_cleanup.py
```

## Contrôles effectués

```bash
python -m ruff check .
python -m ruff format --check .
python -m black --check --diff --workers 1 .
PYTHONPATH=src:. python -m pytest -q --no-cov tests/test_build_public_site.py tests/test_european_national_radar.py tests/test_radar_stack.py tests/test_upstream_watch.py tests/test_opera_ord.py tests/test_native_convective_fields.py
PYTHONPATH=src python tools/generate_belgium_alert_report.py --offline-demo --out-dir /mnt/data/mv_748297_fix_out --no-history --target-date 2026-06-19 --official-forecast-signal severe_thunderstorms --heat-warning-active
PYTHONPATH=src:. python tools/build_belgium_public_site.py --report-dir /mnt/data/mv_748297_fix_out --site-dir /mnt/data/mv_748297_fix_site
PYTHONPATH=src:. python tools/validate_belgium_contracts.py /mnt/data/mv_748297_fix_out
PYTHONPATH=src:. python tools/validate_belgium_public_latest.py /mnt/data/mv_748297_fix_out/belgium_public_latest.json
```

## Résultat

```text
Ruff OK
Ruff format OK
Black OK
42 tests ciblés passés
Génération Belgique OK
Génération site public OK
europe.html OK
pages pays OK
api/europe.json enrichi OK
contrats Belgique OK
belgium_public_latest OK
```
