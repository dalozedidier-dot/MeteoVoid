# MeteoVoid · Storm-scope — site multi-pages

Site statique, thème orage, **éclairs animés**. Toutes les pages partagent
`assets/app.css`, `assets/regions.js`, `assets/app.js`.

Pages : index.html (Belgique), europe.html, france/germany/netherlands/spain/
switzerland/italy/austria/denmark/uk.html, methodology.html.

## Aperçu (un serveur est nécessaire pour les chemins relatifs + le fetch)
    cd site && python -m http.server 8080   # http://localhost:8080/

Données live : indices Open-Meteo (CAPE/CIN/LI), radar RainViewer (affichage).
Sur le site réel, brancher sur api/*.json (voir le paquet Claude Code).
Discipline : surface & composantes = anticipation, pas confirmation radar.
