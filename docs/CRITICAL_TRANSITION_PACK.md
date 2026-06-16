# MeteoVoid Critical Transition Pack

Ce pack ajoute une couche ORI-C appliquée à MeteoVoid Belgique. Le but n'est pas de produire une alerte officielle, mais de mesurer des signatures de bascule : signaux précoces, graphes d'information, validation, auto-surveillance et sorties interopérables.

## Sorties ajoutées

- `early_warning_signals.json` : autocorrélation lag-1, variance, skewness, flickering et score de ralentissement critique.
- `early_warning_by_station.csv` : signaux précoces par station.
- `early_warning_dashboard.html` : lecture visuelle des signaux de transition.
- `information_graph_summary.json` : graphe directionnel appris par corrélation retardée et proxy d'entropie de transfert.
- `information_graph_edges.csv` : arêtes informationnelles entre stations.
- `information_graph.html` : tableau de lecture du graphe informationnel.
- `validation_metrics.json` : POD, FAR, CSI, Brier et squelette coût-perte.
- `validation_dashboard.html` : restitution de validation.
- `self_watchdog.json` : auto-surveillance du run.
- `observation_gap_status.json` : état de préparation satellite, GNSS, pression participative, radar et foudre.
- `belgium_alert_cap.xml` : sortie CAP de test, non officielle.
- `meteovoid_api_latest.json` : API statique JSON pour GitHub Pages.

## Lecture

MeteoVoid ne cherche pas seulement une intensité d'orage. Il mesure si les couches du système deviennent cohérentes vers une transition : charge, déclenchement, organisation, observation et propagation amont.

Les connecteurs satellite EUMETSAT, GNSS/E-GVAP, pression participative et foudre communautaire sont volontairement exposés comme états de préparation. Ils ne cassent pas la CI quand les accès ne sont pas configurés.

Voir aussi `docs/METHODOLOGY.md` pour le contrat public, les limites et la séparation chaleur / risque convectif.
