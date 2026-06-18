# MeteoVoid native convective engine patch

## Objectif

Corriger la limite où MeteoVoid utilisait surtout une heatmap proxy dérivée des stations Open-Meteo, sans champs convectifs modèle natifs.

## Ajouts principaux

- Demande des champs Open-Meteo horaires : `cape`, `lifted_index`, `convective_inhibition`, `freezing_level_height`, `boundary_layer_height`.
- Intégration dans le moteur `native_convective_indices_from_hourly`.
- Extension du contrat natif avec `lightning_potential_index`, `freezing_level_height_m`, `boundary_layer_height_m`.
- Correction des alias SRH avec variantes `m2s2` et `m2_s2`.
- Nouvelle carte HTML dédiée : `belgium_native_convective_map.html`.
- Nouvelle grille : `native_convective_grid.csv`.
- Nouveau JSON : `native_convective_parameters.json`.
- Ajout du frame expert “Convectif natif” dans le site public.
- Ajout de tests ciblés.

## Fichiers modifiés

```text
tools/generate_belgium_alert_report.py
tools/belgium_score_layers.py
tools/belgium_weather_layers.py
tools/build_belgium_public_site.py
```

## Fichiers ajoutés

```text
tests/test_native_convective_fields.py
docs/CONVECTIVE_NATIVE_ENGINE.md
```

## Limites conservées volontairement

- Le Lightning Potential Index est un potentiel modèle, pas une observation foudre.
- Les champs cisaillement/SRH sont consommables si fournis par un connecteur, mais ils ne sont pas demandés par défaut à Open-Meteo dans ce patch.
- La validation historique reste dépendante d'un registre réel d'événements vérifiés. Aucun événement n'a été inventé.
- OPERA ORD et les radars nationaux restent dépendants des clés/fichiers réels configurés.

## Contrôles effectués

```bash
python -m compileall -q src tools tests
python -m pytest -q --no-cov tests/test_native_convective_fields.py
python -m pytest -q --no-cov tests/test_build_public_site.py tests/test_native_convective_fields.py tests/test_european_national_radar.py tests/test_radar_stack.py tests/test_upstream_watch.py tests/test_opera_ord.py
PYTHONPATH=src python tools/generate_belgium_alert_report.py --offline-demo --out-dir /mnt/data/test_native_out --no-history --target-date 2026-06-19 --official-forecast-signal severe_thunderstorms --heat-warning-active
PYTHONPATH=src python tools/build_belgium_public_site.py --report-dir /mnt/data/test_native_out --site-dir /mnt/data/test_native_site
```

## Résultat

```text
3 tests natifs passés
39 tests ciblés passés
génération Belgique OK
site public OK
artefacts natifs générés
```
