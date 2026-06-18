# MeteoVoid EOF newline fix

Correctif ciblé pour le run GitHub Actions `logs_74860353237`.

## Cause

`pre-commit` échouait uniquement sur `end-of-file-fixer` :

```text
Fixing european_national_radar_map.html
No newline at end of file
```

## Correction

Ajout d'un retour à la ligne final dans :

```text
european_national_radar_map.html
```

Aucune logique météo, radar, Europe ou site public n'a été modifiée.

## Vérification locale

```bash
python -m py_compile tools/build_belgium_public_site.py
python - <<'PY'
from pathlib import Path
assert Path('european_national_radar_map.html').read_bytes().endswith(b'\\n')
PY
```
