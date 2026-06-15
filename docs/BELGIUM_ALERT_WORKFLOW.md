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

## Mise à jour étendue : lignes futures intégrées

La version étendue ajoute directement plusieurs briques qui étaient prévues dans la feuille de route.

### Séries horaires et fenêtre sensible

Le rapport conserve maintenant une série horaire compacte par station dans `stations[].hourly_risk`. Elle alimente :

- `risk_timeseries.json` : timeline agrégée par heure.
- `risk_timeline.csv` : version tabulaire exploitable.
- `timeline_summary` dans le rapport JSON : pic, score du pic, première et dernière heure `high`.

Cette couche permet de savoir si le risque est ponctuel, durable, en fin de journée ou concentré sur une fenêtre précise.

### Synthèse par province / zone

Les stations sont regroupées dans une synthèse territoriale :

- `province_summary.json`
- `province_summary.csv`
- `province_summary` dans `belgium_alert_report.json`

Le regroupement distingue les provinces belges et les zones d’approche frontalières. Ce n’est pas encore une carte administrative officielle, mais cela prépare le passage vers une vraie couche provinces GeoJSON.

### Heatmap

Une nouvelle sortie est générée :

- `belgium_alert_heatmap.html`

Elle utilise Leaflet et une couche de chaleur pour visualiser la concentration du risque. Elle ne remplace pas un radar météo ; elle représente uniquement la distribution spatiale du score MeteoVoid.

### Notification state

Une sortie anti-spam/notification est maintenant générée :

- `notification_state.json`

Elle contient :

- `should_notify`
- `cooldown_hours`
- `dedupe_key`
- `public_alert_allowed`
- `message_summary`

Cette sortie prépare une logique de notification plus propre : ne pas envoyer la même alerte plusieurs fois si le niveau, la fenêtre et la sévérité n’ont pas changé.

### Replay metrics

Une sortie de pré-validation est générée :

- `replay_metrics.json`

Elle contient des métriques simples : nombre de stations high, durée horaire high, pic horaire, densité du signal. Cette couche prépare un futur mode replay complet sur épisodes passés.

### Fichiers générés dans la version étendue

En plus des sorties précédentes, le dossier `_ci_out/belgium_alert/` contient maintenant :

- `risk_timeseries.json`
- `risk_timeline.csv`
- `province_summary.json`
- `province_summary.csv`
- `belgium_alert_heatmap.html`
- `notification_state.json`
- `replay_metrics.json`

## Prochaines extensions encore ouvertes

Ce qui reste volontairement préparé mais non branché automatiquement :

- connecteur IRM/KMI automatique robuste ;
- connecteur MeteoAlarm stable ;
- connecteur ESTOFEX avec parsing prudent ;
- couche radar/foudre temps réel ;
- vrai fond administratif belge GeoJSON provinces/communes ;
- validation replay sur épisodes historiques observés.

Le principe retenu reste conservateur : mieux vaut une intégration déclarative fiable qu’un scraping fragile qui casse la CI ou donne une fausse confirmation.

## Extension opérationnelle installée : palier multi-sources

La version étendue ajoute les six blocs du prochain palier directement dans MeteoVoid :

1. **IRM/KMI automatique** : option `--auto-external` avec récupération fail-safe de la page d'avertissements IRM/KMI et de la prévision texte. Les erreurs réseau ou changements HTML sont consignés dans `official_sources_status.json` sans casser le run.
2. **MeteoAlarm + ESTOFEX** : connecteurs fail-safe vers le flux Atom Belgique de MeteoAlarm et le bulletin texte ESTOFEX. Les niveaux détectés alimentent `external_confirmation.score`.
3. **Radar & foudre** : endpoints configurables `--radar-json-url` et `--lightning-json-url`, ou secrets GitHub `METEOVOID_RADAR_JSON_URL` et `METEOVOID_LIGHTNING_JSON_URL`. Les confirmations sont résumées dans `nowcast_status.json`.
4. **Carte provinces + heatmap** : génération de `belgium_province_map.html` à partir de `config/belgium_provinces_simplified.geojson`, en plus de `belgium_alert_heatmap.html` et de la carte stations Leaflet.
5. **Replay historique** : génération de `replay_validation.json` et ajout du script `tools/replay_belgium_alert_history.py` pour comparer l'historique MeteoVoid à un registre d'épisodes connus.
6. **Calibration du scoring** : configuration `config/belgium_scoring_calibration.yaml`, sortie `calibration_report.json`, seuils et pondérations modifiables sans toucher au code.

Commande complète type :

```bash
python tools/generate_belgium_alert_report.py \
  --stations config/stations_belgium.yaml \
  --target-date auto \
  --out-dir _ci_out/belgium_alert \
  --history-dir .meteovoid_history/belgium_alert \
  --auto-external \
  --external-sources-config config/external_sources_belgium.yaml \
  --calibration-config config/belgium_scoring_calibration.yaml \
  --province-geojson config/belgium_provinces_simplified.geojson \
  --replay-events config/belgium_replay_events.example.csv
```

Les connecteurs externes restent volontairement prudents : ils renforcent le score de confirmation quand les sources convergent, mais MeteoVoid continue d'indiquer que seul l'IRM/KMI et les autorités compétentes publient des avertissements officiels.
