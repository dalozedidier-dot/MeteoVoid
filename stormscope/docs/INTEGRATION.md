# INTEGRATION.md — brancher Storm-scope et déployer

Procédure concrète. Suppose le dépôt MeteoVoid réel (avec
`tools/build_belgium_public_site.py`) + ce paquet copié à la racine sous
`stormscope/` (ou n'importe où ; adapter les chemins).

---

## 0. Aperçu local (sans rien intégrer)

```bash
cd stormscope/web
python -m http.server 8080      # puis ouvrir http://localhost:8080/
```

Vérifier : les 8 pages, l'orage de fond, la carte Belgique (surface + radar), la
page Europe (sélecteur de pays). En l'absence d'`api/`, l'app utilise Open-Meteo.

---

## 1. Brancher l'API du site (données serveur d'abord)

Dans `web/index.html`, le bloc `<script>` final contient la fonction `loadBE()`
(moteur Open-Meteo) et `boot()` (`loadBE().catch(...)`). Pour préférer l'API :

1. Inclure l'adaptateur avant `app` logic :
   `<script src="assets/site-api-adapter.js"></script>` (avant le `<script>` inline,
   ou extraire le script inline vers `assets/app.js` — voir étape 3).
2. Ajouter un drapeau et un chargeur unifié :

```js
const USE_SITE_API = true;
async function boot(){
  let model = null;
  if (USE_SITE_API && window.MeteoVoidSiteApi) {
    model = await window.MeteoVoidSiteApi.loadModelFromSiteApi('./api/');
  }
  if (model) { applyModel(model); }     // chemin API
  else { await loadBE(); }              // repli Open-Meteo (existant)
}
```

3. Écrire `applyModel(model)` qui alimente les pages depuis le MODEL normalisé
   (`model.now`, `model.hours`, `model.stations`, `model.heatHours`). Réutiliser
   les rendus existants (`renderVeille`, `renderHours`, `renderNet`,
   `renderChaleur`, `renderExpert`) en les faisant lire le MODEL plutôt que `BE`.
   Le plus simple : introduire une variable `BE`-compatible dérivée du MODEL, ou
   refactorer les rendus pour accepter le MODEL.

4. **Confirmer les contrats** marqués `(?)` dans `assets/site-api-adapter.js`
   contre un run réel : générer un site avec un `report_dir` peuplé, ouvrir
   `api/timeline.json`, `api/stations.json`, `api/heat.json`, et ajuster le mapping
   (noms de champs `score/class/level`, `lat/lon`, `humidex`).

La carte et l'Europe peuvent garder Open-Meteo (couche d'affichage anticipative)
même quand le reste lit l'API : c'est cohérent avec no_machine_radar_data.

---

## 2. Confirmer les contrats d'API sur un run réel

```bash
pip install -e . --break-system-packages
python - <<'PY'
from pathlib import Path
import importlib.util
spec = importlib.util.spec_from_file_location("site","tools/build_belgium_public_site.py")
site = importlib.util.module_from_spec(spec); spec.loader.exec_module(site)
# report_dir = un répertoire de run réel si disponible, sinon vide pour tester l'UI
site.build_index(Path("RUN_DIR_OU_VIDE"), Path("site"))
PY
ls site/api/*.json
```

Inspecter `site/api/latest.json|timeline.json|stations.json|heat.json` et aligner
l'adaptateur. (À report-dir vide les valeurs sont `null/[]` → l'app bascule en
repli Open-Meteo : c'est voulu.)

---

## 3. Intégrer au build — Option A (recommandée, faible risque)

Servir Storm-scope comme page, et copier ses assets dans la sortie du site.

1. Optionnel mais propre : extraire de `web/index.html` le `<style>` vers
   `web/assets/app.css` et le `<script>` inline vers `web/assets/app.js`, puis dans
   `index.html` référencer `assets/app.css`, `assets/regions.js` (constantes
   `BE_PROV/REGIONS/RADAR_SITES/BE_STATIONS`), `assets/site-api-adapter.js`,
   `assets/app.js`. (Tant que ce n'est pas fait, le monolithe autonome convient.)

2. Dans `tools/build_belgium_public_site.py`, ajouter un écrivain :

```python
import shutil
def _write_stormscope(site_dir: Path, pkg_web: Path) -> None:
    # copie l'app + assets dans la sortie publiée
    (site_dir).mkdir(parents=True, exist_ok=True)
    shutil.copy(pkg_web / "index.html", site_dir / "index.html")      # nouvelle home
    for sub in ("assets", "config"):
        src = pkg_web / sub
        if src.exists():
            shutil.copytree(src, site_dir / sub, dirs_exist_ok=True)
```

   et l'appeler dans `build_index(...)` **après** l'écriture de `api/*.json`, en
   passant le chemin `web/` du paquet. Conserver l'ancienne home sous
   `classic.html` si tu veux un repli (`shutil.move`/écrire avant la copie).

3. L'app lit `./api/…` (mêmes répertoires) — aucune URL absolue, donc compatible
   sous-chemin GitHub Pages (`user.github.io/repo/`).

### Option B (plus invasive)
Réécrire les gabarits internes (`EUROPE_MAX_TEMPLATE`, gabarit de `build_index`)
au langage Storm-scope. Plus long, plus risqué ; ne le faire qu'après validation
de l'Option A.

---

## 4. Tests

```bash
python -m pytest tests/ -p no:cacheprovider -o addopts="" -q
```

Doit rester vert. Si l'écrivain ajoute des fichiers, ajouter au besoin un test
vérifiant la présence de `index.html` + `assets/` dans la sortie.

---

## 5. Déploiement GitHub Pages

Selon la configuration du dépôt :

- **Pages depuis `/docs` ou une branche `gh-pages`** : générer dans ce dossier,
  committer, pousser.
  ```bash
  python -c "..."          # build_index(report_dir, Path('docs'))  ou  Path('site')
  git add -A && git commit -m "Storm-scope: nouvelle interface publique" && git push
  ```
- **GitHub Actions** : si un workflow build/publie déjà le site, y intégrer l'appel
  `_write_stormscope`. Ne pas committer de secrets ; tout est sans clé.

Vérifier en ligne : 8 pages, orage de fond, carte + Europe, données du run,
étiquettes honnêtes, disclaimer présent.

---

## Rappels

- Ne pas fabriquer de radar/foudre ; surface & composantes = anticipation.
- Open-Meteo / RainViewer / Leaflet / polices Google : libres, sans clé.
- Aucune mention de version/édition ; conserver l'attribution ORI-C / ori-c.be.
