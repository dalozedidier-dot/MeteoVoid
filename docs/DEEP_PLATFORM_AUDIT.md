# MeteoVoid deep platform audit

Cette note décrit les nouveaux contrats publics ajoutés à la plateforme.

## Objectif

MeteoVoid ne doit pas seulement afficher une météo. La plateforme doit montrer la cohérence ou l’incohérence entre les signaux disponibles.

## Contrats ajoutés

- `api/convergence_matrix.json` compare modèle, stations, grille, live smoke, radar machine, source officielle et santé des sources.
- `api/forecast_ledger.json` prépare la validation append-only par horizon H-24, H-12, H-6 et H-3.
- `api/operational_readiness.json` indique ce qui est prêt et ce qui reste candidat.
- `api/action_cards.json` produit une lecture publique et une lecture expert sans remplacer les bulletins officiels.
- `api/public_manifest.json` hash chaque endpoint JSON public après build.

## Règle de lecture

Un potentiel modèle ne devient pas un événement observé sans confirmation par une couche indépendante. Radar visuel, radar machine, foudre, stations et sources officielles doivent rester séparés.
