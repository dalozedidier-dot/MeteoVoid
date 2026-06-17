# MeteoVoid — correctif post-CI radars nationaux Europe

Ce patch corrige le dernier blocage `pre-commit` observé dans les logs `logs_74686935050.zip`.

## Causes corrigées

- `end-of-file-fixer` modifiait `european_national_radar_map.html` parce qu’il manquait un retour à la ligne final.
- `ruff-format` / `black 24.10.0` voulaient reformater un bloc dans `src/meteovoid/belgium/european_national_radar.py`.
- `mypy (src only)` passait déjà dans ces logs ; il n’y avait pas de correction de typage à refaire.

## Fichiers inclus

- `src/meteovoid/belgium/european_national_radar.py`
- `european_national_radar_map.html`

## Application

```bash
unzip MeteoVoid_EU_NATIONAL_RADARS_POST_CI_FIX_PATCH.zip -d /chemin/vers/MeteoVoid-main
```

Puis relancer la CI.
