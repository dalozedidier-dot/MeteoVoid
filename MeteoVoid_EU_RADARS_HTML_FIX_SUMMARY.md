# MeteoVoid — correctif affichage HTML des radars Europe

## Problème corrigé

La couche `european_national_radar_*` était bien générée côté artefacts et exposée dans `api/radar.json`, mais elle restait trop enterrée dans la vue expert et n'était pas visible comme section radar dédiée dans la page HTML publique.

## Correction appliquée

Fichiers modifiés :

- `tools/build_belgium_public_site.py`
- `tests/test_build_public_site.py`

Ajouts côté interface publique :

- nouvel onglet expert `Radars Europe` ;
- section visible `Radars Europe · Espagne, France, Suisse, Pays-Bas` ;
- cartes de statut : RainViewer, OPERA ORD, radars nationaux, pays avec données machine ;
- liens directs vers :
  - `reports/latest/european_national_radar_map.html` ;
  - `reports/latest/european_national_radar_report.md` ;
  - `reports/latest/european_national_radar_sources.csv` ;
  - `api/radar.json` ;
- tableau par pays : Espagne, France, Suisse, Pays-Bas ;
- iframe dédiée à la carte `european_national_radar_map.html`.

## Logique conservée

Le correctif ne prétend pas avoir une preuve radar si aucun fichier radar lisible n’est disponible. La page indique clairement :

- interface prête ;
- donnée machine absente si aucun fichier n’est lu ;
- RainViewer = affichage immédiat seulement ;
- OPERA ORD = données exploitables seulement si accès/licence configuré.

## Tests effectués

```bash
python -m py_compile tools/build_belgium_public_site.py tests/test_build_public_site.py
PYTHONPATH=. pytest -q --no-cov tests/test_build_public_site.py
PYTHONPATH=src python tools/build_belgium_public_site.py --report-dir /mnt/data/meteo_eu_national_cifix_out --site-dir /mnt/data/meteo_html_radars_fix_site
```

Résultat :

```text
6 tests UI passés
site généré OK
index.html contient Radars Europe + european_national_radar_map.html
api/radar.json contient european_national_radar
```
