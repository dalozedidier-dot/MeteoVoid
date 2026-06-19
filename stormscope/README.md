# MeteoVoid · Storm-scope

Nouvelle interface publique pour MeteoVoid — moderne, thème orage, **multi-pages**,
avec **éclairs animés** en arrière-plan. Prototype non officiel (cadre ORI-C,
ori-c.be). Ne remplace pas l'IRM/KMI.

## Contenu

```
meteovoid-stormscope/
├─ CLAUDE.md                       Manuel d'exécution pour Claude Code (à lire d'abord)
├─ docs/
│  └─ INTEGRATION.md               Câblage API + intégration au build + déploiement Pages
└─ web/
   ├─ index.html                   L'application (autonome, fonctionne déjà)
   ├─ assets/
   │  └─ site-api-adapter.js       Adaptateur vers api/*.json (données serveur d'abord)
   └─ config/
      └─ belgium_provinces_simplified.geojson
```

## Aperçu rapide

```bash
cd web && python -m http.server 8080
# http://localhost:8080/
```

Sans `api/` publié, l'app lit Open-Meteo (repli). Branchée sur le site
(`api/*.json` peuplé), elle utilise les scores calculés côté serveur.

## Pages

Veille · Carte · Heures · Chaleur · Réseau · Europe · Expert · Méthode.

## Sources (libres, sans clé)

- Indices convectifs & chaleur : Open-Meteo (CC BY 4.0) — repli.
- Scores publiés : API du site `api/*.json`.
- Radar / satellite : RainViewer (couche d'affichage).
- Cartographie : Leaflet + CARTO dark.

## Discipline

Surface de bascule et composantes = **anticipation / proxy modèle**, jamais une
confirmation radar. Radar, satellite, foudre = affichage. Voir `CLAUDE.md`.
