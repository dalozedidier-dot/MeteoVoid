# MeteoVoid · Radars nationaux Europe

Extension radar pour Espagne, France, Suisse et Pays-Bas.

- Généré : `2026-06-18T17:30:51+00:00`
- Statut : `interfaces_ready_no_machine_data`
- Live probe : `False`

## Pays suivis

- **France** (`france`) · priorité Belgique : `high` · machine radar : `False`
  - Météo-France API / Données publiques Radar · `endpoint_not_configured` · preuve `api_required`
  - AERIS / Réseau radar Météo-France · `endpoint_not_configured` · preuve `catalogue_or_account_required`
  - Météo-France · `endpoint_not_configured` · preuve `display_only`
  - EUMETNET OPERA ORD · `covered_by_opera_ord_connector` · preuve `opera_ord_fallback`
  - RainViewer · `endpoint_not_configured` · preuve `display_only`
- **Pays-Bas** (`netherlands`) · priorité Belgique : `high` · machine radar : `False`
  - KNMI Data Platform · `requires_api_key` · preuve `open_data_api`
  - KNMI Data Platform · `requires_api_key` · preuve `open_data_api`
  - KNMI Data Platform · `requires_api_key` · preuve `open_data_api`
  - KNMI WMS API · `endpoint_not_configured` · preuve `wms_open_data`
  - EUMETNET OPERA ORD · `covered_by_opera_ord_connector` · preuve `opera_ord_fallback`
  - RainViewer · `endpoint_not_configured` · preuve `display_only`
- **Espagne** (`spain`) · priorité Belgique : `medium` · machine radar : `False`
  - AEMET OpenData · `requires_api_key` · preuve `api_required`
  - AEMET OpenData · `requires_api_key` · preuve `api_required`
  - EUMETNET OPERA ORD · `covered_by_opera_ord_connector` · preuve `opera_ord_fallback`
  - RainViewer · `endpoint_not_configured` · preuve `display_only`
- **Suisse** (`switzerland`) · priorité Belgique : `medium` · machine radar : `False`
  - MeteoSwiss Open Data · `configured_not_probed` · preuve `stac_open_data`
  - MeteoSwiss Open Data · `endpoint_not_configured` · preuve `stac_open_data`
  - MeteoSwiss Open Data · `endpoint_not_configured` · preuve `data_on_request`
  - EUMETNET OPERA ORD · `covered_by_opera_ord_connector` · preuve `opera_ord_fallback`
  - RainViewer · `endpoint_not_configured` · preuve `display_only`

## Règle de prudence

Une interface nationale configurée ne devient pas une confirmation radar machine tant qu’un fichier radar n’est pas téléchargé ou fourni localement, lu et transformé en métriques.

OPERA ORD reste la couche paneuropéenne unifiée ; les sources nationales servent à enrichir ou vérifier par pays lorsque les accès sont disponibles.
