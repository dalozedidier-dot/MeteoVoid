# MeteoVoid · Cartes modèles NWP

Cette couche ajoute une sélection de modèles opérationnels directement sur la carte Leaflet.

## Sources connectées

- `Best match` : Open-Meteo Forecast API
- `ECMWF IFS` : Open-Meteo ECMWF endpoint
- `DWD ICON` : Open-Meteo DWD ICON endpoint
- `Météo-France AROME/ARPEGE` : Open-Meteo Météo-France endpoint

Les valeurs ne sont pas simulées par MeteoVoid. Elles sont lues côté navigateur depuis les endpoints météo externes. Si un champ n’est pas disponible pour un modèle, une échéance ou une zone, l’interface affiche `champ indisponible`.

## Couches disponibles

- précipitation
- vent 10 m
- rafales
- température 2 m
- point de rosée
- pression MSL
- CAPE
- CIN
- PWAT / eau précipitable
- température 850 hPa
- température 700 hPa
- température 500 hPa
- cisaillement 0–6 km approximé par différence vectorielle entre le vent 10 m et le vent 500 hPa

## Limites assumées

La couche est une visualisation par points d’échantillonnage, pas une tuile modèle continue propriétaire de type Windy. Elle reste compatible avec GitHub Pages et ne nécessite pas de clé API. Les produits modèle sont des prévisions opérationnelles, distinctes des observations radar, foudre ou satellite.
