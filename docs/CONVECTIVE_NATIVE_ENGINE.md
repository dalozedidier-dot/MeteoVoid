# MeteoVoid · moteur convectif natif

Ce module sépare explicitement deux niveaux de lecture.

1. Le proxy station : chaleur, humidité, précipitations, rafales, pression et codes météo.
2. Les champs convectifs natifs : CAPE, CIN, Lifted Index, freezing level, hauteur de couche limite, et champs additionnels fournis par connecteurs.

## Champs demandés à Open-Meteo

MeteoVoid demande maintenant, en plus des variables horaires classiques :

```text
cape
lifted_index
convective_inhibition
freezing_level_height
boundary_layer_height
```

Ces champs sont des champs modèle. Ils ne constituent pas une preuve radar, ni une observation foudre.

## Champs consommables si un autre connecteur les fournit

Le moteur sait aussi consommer :

```text
k_index_c
total_totals_index
precipitable_water_mm
lightning_potential_index
shear_0_6km_ms
shear_0_3km_ms
srh_0_1km_m2_s2
srh_0_3km_m2_s2
lcl_m
lfc_m
theta_e_850k
lapse_rate_700_500_c_km
```

Ces champs ne sont pas inventés. Ils sont intégrés seulement s'ils sont présents dans le payload d'entrée.

## Nouveaux artefacts

```text
convective_parameters.json
native_convective_parameters.json
native_convective_grid.csv
belgium_native_convective_map.html
```

## Statuts attendus

```text
proxy_only
proxy_plus_native_convective_fields
```

`proxy_only` signifie que la heatmap MeteoVoid reste un proxy dérivé des stations.

`proxy_plus_native_convective_fields` signifie que MeteoVoid a reçu au moins un champ convectif modèle natif et l'a intégré au score convectif.

## Limite importante

Le Lightning Potential Index est un potentiel modèle. Ce n'est pas une observation foudre. Une vraie confirmation foudre exige un flux de détection externe explicite.
