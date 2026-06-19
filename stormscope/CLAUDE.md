# CLAUDE.md — MeteoVoid · interface « Storm-scope »

Manuel d'exécution pour Claude Code. Lis ce fichier en entier avant d'agir, puis
suis `docs/INTEGRATION.md` pas à pas. Travaille **dans le dépôt MeteoVoid réel**
(celui qui contient `tools/build_belgium_public_site.py`), pas seulement dans ce
paquet — ce paquet est la nouvelle interface à intégrer.

## Contexte

MeteoVoid est un prototype non officiel de veille de **bascule convective** pour
la Belgique (cadre ORI-C de Didier Daloze, ori-c.be). Le site statique est généré
par `tools/build_belgium_public_site.py` et publié sur GitHub Pages. Il expose une
API statique sous `api/*.json` (scores calculés côté serveur) et plusieurs pages
(`index.html` Belgique, `europe.html`, pages pays, `methodology.html`).

« Storm-scope » est une nouvelle interface, plus moderne, assumant le thème orage :
fond ciel d'orage avec **éclairs animés**, et une application **multi-pages**
(Veille · Carte · Heures · Chaleur · Réseau · Europe · Expert · Méthode). Son
élément signature est une **coupe atmosphérique** : l'énergie convective s'empile
sous le couvercle d'inhibition, et perce → éclair.

Fichier de référence prêt à l'emploi : `web/index.html` (autonome, fonctionne
déjà via Open-Meteo en repli). Adaptateur API : `web/assets/site-api-adapter.js`.

## Contraintes NON négociables

1. **no_machine_radar_data** : ne jamais fabriquer de confirmation radar/foudre.
   La « surface de bascule » et les composantes sont des **anticipations / proxys
   modèle** ; radar, satellite et foudre sont des couches d'**affichage**. Toute
   étiquette d'UI doit le dire. Une bascule affichée n'est pas une cellule
   confirmée tant que le radar ne l'a pas vue.
2. **Données serveur d'abord** : quand un run est publié, l'interface lit
   `api/*.json` (scores calibrés côté serveur). Open-Meteo n'est qu'un **repli**.
3. **Statut** : « prototype non officiel · ne remplace pas l'IRM/KMI ». Conserver
   le `disclaimer` fourni par `api/latest.json`.
4. **Aucune mention d'édition/version** nulle part (ex. « v1 », « Première
   édition ») tant que ce n'est pas officiellement publié.
5. **Attribution** : conserver MeteoVoid / ORI-C / Didier Daloze / ori-c.be.
6. **Langue** : tout en français.
7. **Esthétique** : instrument de précision, dynamisme issu des données et non de
   la décoration ; pas d'excès ornemental. (La seule audace assumée est l'orage de
   fond + la coupe atmosphérique ; garder le reste sobre.)
8. **Qualité plancher** : responsive jusqu'au mobile, focus clavier visible,
   `prefers-reduced-motion` respecté (déjà le cas dans `web/index.html`).

## Faits sur le dépôt (vérifiés)

- Build : `pip install -e . --break-system-packages` puis appeler
  `build_index(report_dir, site_dir)` depuis `tools/build_belgium_public_site.py`.
  Le build est **robuste à un `report_dir` vide** (utile pour tester l'UI).
- Sorties générées : `index.html`, `europe.html`, `france/germany/netherlands/`
  `spain/switzerland/denmark.html`, `methodology.html`, et `api/*.json`.
- Endpoints utiles : `api/latest.json`, `api/timeline.json`, `api/stations.json`,
  `api/heat.json`, `api/europe.json`, `api/convective_live.json`. Contrats détaillés
  dans `web/assets/site-api-adapter.js` (confirmer les champs `(?)` sur un run réel).
- Tests : `python -m pytest tests/ -p no:cacheprovider -o addopts=""`
  (le `addopts` du `pyproject.toml` impose une couverture ; le neutraliser pour des
  runs ciblés). Ne pas casser les tests existants.

## Objectif

Faire de « Storm-scope » l'interface publique de MeteoVoid, branchée sur l'API du
site, déployée sur GitHub Pages, sans rien fabriquer et sans casser le pipeline.

## Plan (ordre conseillé — détails dans docs/INTEGRATION.md)

1. **Aperçu** : ouvrir `web/index.html` localement, vérifier les 8 pages, l'orage
   de fond, la carte Belgique et la page Europe (repli Open-Meteo).
2. **Brancher l'API du site** : activer l'adaptateur (`USE_SITE_API = true`),
   pointer la base sur `./api/`, garder Open-Meteo en repli. Confirmer les champs
   `(?)` contre un run réel et corriger le mapping si besoin.
3. **Intégrer au build** : faire générer/installer Storm-scope par
   `build_belgium_public_site.py` (Option A recommandée dans INTEGRATION.md :
   nouvel écrivain de page + copie des assets `web/assets`, `web/config`).
4. **Vérifier** : `build_index` produit la nouvelle page + assets ; les tests
   passent ; aucune étiquette ne fabrique de confirmation radar.
5. **Déployer** : publier le `site_dir` sur la branche/voie GitHub Pages du dépôt.

## Critères d'acceptation

- Les 8 pages s'affichent et naviguent (routes `#veille … #methode`).
- Avec un run publié, Veille/Heures/Réseau/Chaleur/Expert reflètent `api/*.json` ;
  sans run, repli Open-Meteo fonctionnel.
- Carte et Europe : surface de bascule + détecteurs + radar RainViewer + curseur
  temps ; Europe avec sélecteur de pays.
- Orage de fond animé, désactivé en `prefers-reduced-motion`.
- Étiquettes honnêtes (anticipation ≠ confirmation) ; disclaimer présent.
- `pytest` vert ; build reproductible ; déployable sur GitHub Pages.

## À NE PAS faire

- Ne pas inventer de données radar/foudre ni de scores.
- Ne pas ajouter de clés API ni de dépendances payantes (tout doit rester
  libre/sans clé : Open-Meteo, RainViewer, Leaflet, polices Google).
- Ne pas introduire de mention de version/édition.
- Ne pas remplacer la logique de scoring serveur par le proxy Open-Meteo sur le
  site publié (le proxy reste le repli).
