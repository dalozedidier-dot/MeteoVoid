# MeteoVoid Belgique · nettoyage et extension publique/expert

Ce patch ajoute une séparation plus nette entre trois couches :

1. **grand public** : bulletin météo classique à 5 jours, zones belges, texte sobre ;
2. **opérationnel** : signal MeteoVoid, fenêtres sensibles, sources, radar et confirmation ;
3. **expert** : cartes, champs convectifs, exports, validation et historique.

## Nouvelles commandes

```bash
make clean
make test-fast
make belgium-geodata-offline
make belgium-5days-offline
make belgium-site-demo
```

En CI live, les workflows appellent :

```bash
python tools/prepare_belgium_geodata.py --out-dir _ci_out/belgium_alert
python tools/generate_belgium_5day_bulletin.py --out-dir _ci_out/belgium_alert --days 5
python tools/update_belgium_validation_history.py --out-dir _ci_out/belgium_alert
```

## Cartes Belgique

Le repo garde un fallback local pour ne jamais casser la page. Le nouveau statut
`official_geodata_status.json` indique explicitement si la couche utilisée vient
d’un téléchargement ou du fallback local. La source de référence à viser reste
geo.be / INSPIRE / CadGIS ; le fallback documenté utilise des données WGS84 issues
de projets open-data belges dérivés de Statbel.

## Bulletin 5 jours

Sorties :

- `weather_5days.json`
- `weather_5days.md`
- `api/weather_5days.json` sur la page statique

Le bulletin reste non officiel. Il ne remplace pas l’IRM/KMI.

## Validation historique

Sorties :

- `validation_history.json`
- `forecast_history.csv`

La logique est append-only : on stocke ce que MeteoVoid prévoyait, puis on compare
plus tard avec `config/belgium_verified_storm_events.csv`. Cela évite de valider
un modèle avec ses propres hypothèses.
