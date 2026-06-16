# MeteoVoid Belgique — page publique GitHub Pages

Cette page publie une interface en **trois niveaux de lecture** à partir du dernier run
MeteoVoid Belgique. Elle ne remplace pas les alertes officielles de l’IRM/KMI : c’est une
vitrine technique et un tableau de bord expérimental.

La phrase directrice : *MeteoVoid ne montre pas seulement la météo, il cherche à détecter le
moment où une atmosphère instable bascule.*

## Trois niveaux

1. **Vue simple** — que faut-il retenir ? Niveau opérationnel, score MeteoVoid, confiance du
   run, fenêtre critique, zone principale et une phrase de synthèse automatique. Lecture en
   10 secondes.
2. **Vue opérationnelle** — pourquoi le risque monte ? Le tableau *Convective Transition* est
   une jauge de bascule en sept blocs (charge convective, déclencheur, organisation,
   couvercle, observation émergente, propagation amont, *void collapse signal*). Chaque bloc
   porte un score, une couleur, une phrase et les variables responsables. En dessous : une
   timeline horaire (courbe + récit automatique) et une explication automatique de l’alerte.
3. **Vue expert** — données, scores et graphes. Stations et zones, observation émergente
   (radar, foudre, satellite, GNSS, pression participative), validation scientifique, santé
   des sources, puis les cartes et graphes existants regroupés par usage et derrière des
   onglets, ainsi que les exports.

La logique est volontairement *« une couche à la fois »* : la complexité brute reste
accessible mais n’est plus imposée à l’entrée.

## API statique JSON

La page lit des fichiers JSON propres plutôt que d’être une grande page figée. Ils sont
publiés sous `api/` et réutilisables par d’autres clients :

```text
api/latest.json      niveau, score, confiance, fenêtre, zone, synthèse, explication
api/stations.json    risque par station et par province
api/timeline.json    timeline horaire + récit automatique
api/transition.json  les sept blocs de transition convective
api/sources.json     santé des sources et observation émergente
api/validation.json  métriques de validation scientifique
api/index.json       manifeste des points d’entrée
```

Servie sur GitHub Pages, la page récupère ces fichiers en direct. Ouverte en local
(`file://`), elle retombe sur un view-model embarqué pour rester fonctionnelle hors ligne.

## Workflow

Le workflow dédié est `.github/workflows/belgium_pages.yml`. Il génère les artefacts dans
`_ci_out/belgium_alert`, construit le site statique dans `_site` (page + `api/` + copie des
artefacts dans `reports/latest/`), puis le déploie via GitHub Pages.

```bash
python tools/build_belgium_public_site.py \
  --report-dir _ci_out/belgium_alert \
  --site-dir _site
```

## URL en ligne

Après le premier déploiement, l’URL apparaît dans le résumé du workflow GitHub Actions,
étape `Deploy to GitHub Pages`, généralement sous la forme :

```text
https://<utilisateur>.github.io/<repo>/
```

## Données et prudence

Le niveau opérationnel tient compte de la confirmation externe : un signal modèle élevé mais
non confirmé reste en « veille renforcée » plutôt qu’en alerte. Les cartes radar et fonds de
carte dépendent de services externes chargés côté navigateur. Les couches d’humidité, de
point de rosée et de formation orageuse sont des interpolations légères, à lire comme des
aides visuelles et non comme des champs officiels.

## GitHub Pages

Le workflow active GitHub Pages via `actions/configure-pages` avec `enablement: true`, puis
publie le dossier `_site`. En cas d’échec, vérifier dans `Settings > Pages` que la source est
bien **GitHub Actions**.
