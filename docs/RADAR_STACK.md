# MeteoVoid · European Radar Stack

Cette couche ajoute quatre niveaux distincts :

1. **RainViewer** : affichage radar immédiat dans `rainviewer_radar_map.html`. C’est une couche visuelle utile pour situer les précipitations, mais elle n’est pas utilisée comme preuve radar machine.
2. **OPERA ORD / MeteoGate** : connecteur européen pour données radar ouvertes quand l’accès est activé et licite. La configuration est dans `config/opera_ord.yaml`.
3. **wradlib** : traitement local de fichiers radar quand la dépendance optionnelle est installée et que des fichiers radar exploitables sont fournis.
4. **pySTEPS** : estimation de mouvement/nowcasting seulement si une séquence réelle de trames radar est disponible.

## Commandes

```bash
python tools/generate_belgium_alert_report.py --offline-demo --out-dir _out/belgium
```

Active le fetch live RainViewer côté Python, uniquement pour produire un statut JSON :

```bash
python tools/generate_belgium_alert_report.py --out-dir _out/belgium --enable-rainviewer-live
```

Active OPERA ORD :

```bash
python tools/generate_belgium_alert_report.py --out-dir _out/belgium --enable-opera-ord
```

Analyse des fichiers radar locaux :

```bash
python tools/generate_belgium_alert_report.py \
  --out-dir _out/belgium \
  --radar-frame path/to/frame_1.npy \
  --radar-frame path/to/frame_2.npy \
  --radar-frame path/to/frame_3.npy \
  --enable-pysteps-nowcast
```

## Dépendances optionnelles

```bash
pip install -e ".[dev,live,viz,radar]"
```

Les dépendances radar sont volontairement optionnelles. Le projet doit continuer à passer en CI sans installer wradlib/pySTEPS.

## Règle de sincérité

Si aucun endpoint OPERA/licencié ou aucun fichier radar local n’est disponible, MeteoVoid écrit explicitement : `no_machine_radar_data`. Il ne convertit pas une carte visuelle en confirmation radar.

## Extension OPERA ORD complète

La couche radar utilise maintenant `src/meteovoid/belgium/opera_ord.py` pour séparer clairement l’affichage et la donnée machine.

Nouveaux fichiers de sortie :

```text
opera_ord_inventory.json
opera_ord_files_manifest.json
opera_radar_metrics.json
```

`radar_stack.json` passe à un contrat enrichi `meteovoid_european_radar_stack_v2`. La confirmation radar machine n’est vraie que si des fichiers radar locaux ou OPERA sont réellement lisibles. RainViewer reste `display_only`.

Voir aussi : `docs/OPERA_ORD.md`.
