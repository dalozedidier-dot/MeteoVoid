# Registre d’événements vérifiés Belgique

`config/belgium_verified_storm_events.csv` est le registre canonique utilisé par le mode replay.

Objectif : comparer les sorties MeteoVoid avec des épisodes documentés afin de mesurer vrais positifs, faux positifs, faux négatifs et délai de détection.

Colonnes attendues :

- `event_id` : identifiant stable.
- `start_date` / `end_date` : fenêtre YYYY-MM-DD.
- `expected` : `event`, `alert`, `severe`, `positive` ou `none`.
- `phenomenon` : orage, grêle, rafales, inondation, chaleur, etc.
- `region` : Belgique, province, station ou zone.
- `verification_level` : officiel, radar, foudre, média vérifié, observation terrain.
- `official_source` : IRM/KMI, MeteoAlarm, commune, province, autre.
- `radar_confirmed` / `lightning_confirmed` : booléen textuel.
- `notes` : contexte libre.

Sans événements vérifiés, le replay reste installé mais non concluant.
