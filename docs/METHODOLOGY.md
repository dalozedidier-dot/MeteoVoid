# Méthodologie MeteoVoid Belgique

MeteoVoid Belgique est un prototype technique expérimental de veille météo. Il ne remplace pas les avertissements de l’IRM/KMI, MeteoAlarm, les autorités locales, le radar ou le nowcast foudre.

## Niveaux de signal

Le système distingue trois niveaux :

1. Signal interne : score calculé à partir des stations et des variables disponibles.
2. Confirmation externe : signaux officiels, radar, foudre, MeteoAlarm ou ESTOFEX lorsqu’ils sont renseignés.
3. Niveau opérationnel : formulation prudente fondée sur la convergence entre modèle interne et confirmation externe.

## Séparation chaleur et risque convectif

Le score global est complété par deux couches :

- `heat_stress_score` : lourdeur thermique, chaleur, humidité, point de rosée.
- `convective_risk_score` : potentiel convectif, précipitations, rafales, codes météo, chute de pression et, si disponibles, champs convectifs natifs.

Cette séparation évite de transformer automatiquement une atmosphère chaude et humide en alerte orageuse.

## Indices convectifs natifs

Le contrat `native_convective_fields_optional_v1` prépare l’intégration de CAPE, CIN, Lifted Index, K-index, Total Totals, eau précipitable, cisaillement, SRH, LCL, LFC, theta-e et lapse rate.

Si ces champs ne sont pas fournis par le connecteur météo, MeteoVoid reste en mode proxy explicite.

## Contrat public

Le fichier canonique est `belgium_public_latest.json` avec le contrat `belgium_public_latest_v1`. L’ancien fichier `meteovoid_api_latest.json` reste généré comme alias de compatibilité.

## Validation historique

`config/belgium_verified_storm_events.csv` sert de base d’événements vérifiés pour le replay. L’objectif est de documenter les vrais positifs, faux positifs, faux négatifs et délais de détection.

## Couche radar européenne et nowcasting

MeteoVoid distingue désormais quatre niveaux qui ne doivent pas être confondus.

1. **RainViewer** sert à afficher rapidement une carte radar publique dans le navigateur. Cette carte aide à lire le contexte, mais elle ne devient pas automatiquement une confirmation machine.
2. **OPERA ORD / MeteoGate** est le connecteur prévu pour les vraies données radar européennes lorsque l’accès est activé et conforme aux licences. Si le connecteur n’est pas configuré ou échoue, le rapport l’indique.
3. **wradlib** peut analyser des fichiers radar locaux fournis à MeteoVoid. Cette étape est optionnelle et dépend des formats disponibles.
4. **pySTEPS** peut calculer un mouvement/nowcasting à partir d’une séquence réelle de trames radar. Il n’est jamais lancé sans données suffisantes.

La règle est stricte : si aucune donnée radar fine, licite et exploitable n’est disponible, MeteoVoid écrit explicitement `no_machine_radar_data`. Le système peut afficher une carte visuelle, mais il ne la transforme pas en preuve radar ni en alerte officielle.
