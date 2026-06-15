# MeteoVoid Belgium Alert Watch

Ce module génère une veille météo Belgique à partir des prévisions horaires Open-Meteo, puis produit un rapport JSON, Markdown, CSV, GeoJSON, une carte interactive Leaflet et un tableau de bord HTML.

Le système ne remplace pas l’IRM/KMI. Il sert à détecter un signal modèle, à suivre sa tendance, à conserver l’historique des runs, puis à comparer ce signal avec des confirmations externes.

## Fichiers principaux

- `config/stations_belgium.yaml` : grille Belgique et approches frontalières.
- `tools/generate_belgium_alert_report.py` : récupération, scoring, rapport, cartes, historique, manifeste.
- `.github/workflows/belgium_alert_watch.yml` : workflow planifié et manuel.

## Sorties générées

Le workflow écrit dans `_ci_out/belgium_alert/` :

- `belgium_alert_report.json` : rapport complet machine.
- `belgium_alert_report.md` : résumé humain.
- `risk_by_station.csv` : stations, scores et composantes.
- `risk_by_station.geojson` : données SIG.
- `belgium_alert_map.html` : carte Leaflet principale.
- `belgium_alert_map.svg` : fallback hors ligne.
- `belgium_alert_dashboard.html` : tableau de bord professionnel.
- `source_status.json` : état des sources et erreurs par station.
- `alert_state.json` : niveau opérationnel calculé.
- `history.csv` : historique append-only local ou restauré depuis cache GitHub Actions.
- `manifest.json` : tailles et hashes SHA-256 des fichiers générés.

## Niveaux internes

MeteoVoid distingue désormais trois couches :

1. `aggregate.severity` : sévérité issue du modèle météo.
2. `external_confirmation.score` : confirmation externe renseignée ou future intégration.
3. `operational_state.level` : niveau final prudent pour la veille.

Niveaux opérationnels possibles :

- `normal` : pas de signal notable.
- `low_watch` : signal faible.
- `watch` : signal à surveiller.
- `watch_reinforced` : signal modèle élevé sans confirmation suffisante.
- `pre_alert_confirmed` : signal modèle élevé et confirmation externe partielle.
- `alert_confirmed` : signal modèle très élevé et confirmation externe partielle ou forte.

Même en `alert_confirmed`, le rapport reste non officiel. Le texte public doit renvoyer vers l’IRM/KMI, MeteoAlarm, le radar et la foudre.

## Confirmation externe manuelle

Le workflow manuel permet de renseigner des confirmations externes sans coder de connecteur immédiat :

- `irm_warning_level` : `none`, `yellow`, `orange`, `red`
- `official_forecast_signal` : `none`, `heat`, `instability`, `thunderstorms`, `severe_thunderstorms`
- `heat_warning_active` : `true` ou `false`
- `metealarm_level` : `none`, `yellow`, `orange`, `red`
- `estofex_level` : `none`, `level1`, `level2`, `level3`
- `radar_confirmation` : `none`, `weak`, `moderate`, `strong`
- `lightning_confirmation` : `none`, `nearby`, `confirmed`
- `external_note` : note libre

Correction importante : un bulletin texte de l’IRM/KMI peut confirmer un risque sans qu’un avertissement couleur soit encore publié. Le champ `official_forecast_signal` sert précisément à éviter que `external_confirmation_score` reste à zéro dans ce cas. Si ce champ reste à `none`, MeteoVoid tente aussi d’inférer un signal officiel depuis `external_note`, uniquement quand la note mentionne explicitement IRM/KMI/meteo.be ou une prévision officielle.

Exemple :

```bash
python tools/generate_belgium_alert_report.py \
  --stations config/stations_belgium.yaml \
  --target-date 2026-06-19 \
  --out-dir _ci_out/belgium_alert \
  --history-dir .meteovoid_history/belgium_alert \
  --irm-warning-level yellow \
  --official-forecast-signal severe_thunderstorms \
  --heat-warning-active \
  --metealarm-level yellow \
  --estofex-level level1 \
  --radar-confirmation weak \
  --lightning-confirmation nearby \
  --external-note "Bulletins consultés manuellement avant run"
```

## Historique et tendance

Chaque run ajoute une ligne à :

```text
.meteovoid_history/belgium_alert/belgium_alert_history.csv
```

Le fichier est recopié dans l’artefact sous le nom `history.csv`.

En GitHub Actions, le workflow restaure et sauvegarde `.meteovoid_history` via `actions/cache`. Cela permet de comparer le score actuel au run précédent et de produire un état de tendance :

- `no_history`
- `stable`
- `rising`
- `rising_fast`
- `falling`
- `falling_fast`

## Carte

`belgium_alert_map.html` utilise Leaflet et OpenStreetMap. Les marqueurs sont regroupés automatiquement lorsque les points sont proches. Les labels ne sont plus affichés en permanence, ce qui évite les superpositions. Les détails apparaissent au clic.

`belgium_alert_map.svg` reste disponible en fallback hors ligne. Il utilise une silhouette belge plus détaillée, décale légèrement les points proches et trace une ligne vers la position réelle.

## Webhook

Le webhook générique utilise `METEOVOID_ALERT_WEBHOOK_URL`. Il envoie :

- score modèle
- confirmation externe
- niveau opérationnel
- tendance
- stations principales

Pour éviter les alertes excessives, le workflow peut être lancé avec `min_severity`. Si le niveau opérationnel passe en `pre_alert_confirmed` ou `alert_confirmed`, la notification est traitée comme une alerte interne.

## Limites

- Open-Meteo reste une source de prévision modèle.
- Le système ne fait pas encore de scraping ou ingestion automatique IRM/KMI, MeteoAlarm, ESTOFEX, radar ou foudre.
- Les confirmations externes sont actuellement manuelles ou préparées pour de futurs connecteurs.
- La convection peut évoluer très vite. Un run à J-3 n’a pas la même valeur qu’un run à H-3.
