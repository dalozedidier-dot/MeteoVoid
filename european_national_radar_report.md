# MeteoVoid · Radars nationaux Europe

Extension radar pour Espagne, France, Suisse et Pays-Bas.

- Généré : `2026-06-17T22:36:22+00:00`
- Statut : `interfaces_ready_no_machine_data`
- Live probe : `False`

## Pays suivis

- **France** (`france`) · priorité Belgique : `high` · machine radar : `False`
  - Météo-France API / Données publiques Radar · `endpoint_not_configured` · preuve `api_required`
  - EUMETNET OPERA ORD · `covered_by_opera_ord_connector` · preuve `opera_ord_fallback`
- **Pays-Bas** (`netherlands`) · priorité Belgique : `high` · machine radar : `False`
  - KNMI Data Platform · `requires_api_key` · preuve `open_data_api`
  - EUMETNET OPERA ORD · `covered_by_opera_ord_connector` · preuve `opera_ord_fallback`
- **Espagne** (`spain`) · priorité Belgique : `medium` · machine radar : `False`
  - AEMET OpenData · `requires_api_key` · preuve `api_required`
  - EUMETNET OPERA ORD · `covered_by_opera_ord_connector` · preuve `opera_ord_fallback`
- **Suisse** (`switzerland`) · priorité Belgique : `medium` · machine radar : `False`
  - MeteoSwiss Open Data · `configured_not_probed` · preuve `stac_open_data`
  - EUMETNET OPERA ORD · `covered_by_opera_ord_connector` · preuve `opera_ord_fallback`

## Règle de prudence

Une interface nationale configurée ne devient pas une confirmation radar machine tant qu’un fichier radar n’est pas téléchargé ou fourni localement, lu et transformé en métriques.

OPERA ORD reste la couche paneuropéenne unifiée ; les sources nationales servent à enrichir ou vérifier par pays lorsque les accès sont disponibles.
