# MeteoVoid · Radars nationaux Europe

Cette extension ajoute une couche de suivi radar pour quatre pays autour du périmètre Belgique : Espagne, France, Suisse et Pays-Bas.

Objectif : ne pas remplacer OPERA ORD, mais enrichir la veille amont lorsque des sources nationales sont disponibles, configurées et licites.

## Pays suivis

- Espagne : AEMET OpenData + fallback OPERA ORD.
- France : Météo-France / données publiques radar + fallback OPERA ORD.
- Suisse : MeteoSwiss Open Data / STAC radar precipitation products + fallback OPERA ORD.
- Pays-Bas : KNMI Data Platform / HDF5/WMS/Open Data API + fallback OPERA ORD.

## Règle stricte

Une source nationale peut avoir trois états différents :

1. `interface_ready` ou `configured_not_probed` : l’interface est prête, mais aucune donnée n’est encore lue.
2. `reachable` : le point d’accès répond, mais cela ne suffit pas encore à produire une preuve radar machine.
3. `metrics_available` : un fichier radar national ou local a été lu et transformé en métriques.

MeteoVoid ne considère pas une carte visuelle ou un endpoint joignable comme une confirmation radar machine. Il faut un fichier lisible, une métrique calculée et un statut explicite.

## Commandes

Génération offline honnête :

```bash
python tools/generate_european_national_radar.py --out-dir _out/belgium
```

Probe live des interfaces configurées :

```bash
python tools/generate_european_national_radar.py \
  --out-dir _out/belgium \
  --enable-live
```

Ajout de fichiers radar locaux par pays :

```bash
python tools/generate_european_national_radar.py \
  --out-dir _out/belgium \
  --country-radar-file france:/tmp/france_frame.npy \
  --country-radar-file netherlands:/tmp/knmi_frame.npy
```

Intégration dans le radar stack :

```bash
python tools/generate_radar_stack.py \
  --out-dir _out/belgium \
  --country-radar-file france:/tmp/france_frame.npy
```

Intégration dans le rapport Belgique :

```bash
python tools/generate_belgium_alert_report.py \
  --out-dir _out/belgium \
  --enable-national-radar-live
```

## Variables d’environnement possibles

- `AEMET_API_KEY`
- `METEOFRANCE_API_KEY`
- `KNMI_API_KEY`

La Suisse peut être exploitée via les produits Open Data / STAC quand le client STAC complet sera branché. Pour l’instant, MeteoVoid prépare l’interface, documente la source et accepte des fichiers locaux lisibles.

## Sorties

- `european_national_radar_status.json`
- `european_national_radar_metrics.json`
- `european_national_radar_sources.csv`
- `european_national_radar_map.html`
- `european_national_radar_report.md`

Ces fichiers sont aussi repris dans le site public, sous `api/radar.json` et dans la vue expert.
