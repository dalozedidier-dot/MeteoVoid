# MeteoVoid Europe page

This page is a dedicated Europe layer built with the same public dashboard logic as the Belgium page.

It does not replace national meteorological services. It links national radar interfaces, OPERA ORD, RainViewer, Open-Meteo fallback layers and upstream corridors toward Belgium.

## Countries covered

- Spain: AEMET OpenData national and regional radar interfaces, OPERA ORD fallback, RainViewer display.
- France: Météo-France radar API path, AERIS radar network reference, public radar display, OPERA ORD fallback, RainViewer display.
- Switzerland: MeteoSwiss precipitation radar STAC products, hail radar products reference, short-term nowcasting on request, OPERA ORD fallback, RainViewer display.
- Netherlands: KNMI radar reflectivity composites, radar/gauge precipitation products, KNMI 2 h radar nowcast, WMS reference, OPERA ORD fallback, RainViewer display.

## Evidence rule

A source moves through this chain:

```text
source -> access -> file -> decode -> metrics -> corridor -> Belgium reading
```

RainViewer is display-only. OPERA ORD and national radar files can become machine evidence only when a file is downloaded or provided locally, decoded and converted into metrics.

## Generated public artifacts

```text
europe.html
api/europe.json
api/radar.json
reports/latest/european_national_radar_map.html
reports/latest/european_national_radar_report.md
reports/latest/european_national_radar_sources.csv
reports/latest/european_national_radar_status.json
reports/latest/european_national_radar_metrics.json
```

## Design contract

The Europe page now uses the same public dashboard design language as the Belgium page: command bar, theme toggle, tabs, hero block, KPI cards, operational chain, cards, source registry, exports and expert JSON view.
