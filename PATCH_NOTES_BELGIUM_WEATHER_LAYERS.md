# MeteoVoid Belgium Weather Layers Pack

This update installs advanced Belgium map layers into the existing alert workflow.

## Added

- `tools/belgium_weather_layers.py`
- `config/belgium_map_layers.yaml`
- `tests/test_belgium_weather_layers.py`

## New generated outputs

- `belgium_weather_layers.html`
- `belgium_radar_map.html`
- `belgium_humidity_map.html`
- `belgium_dewpoint_map.html`
- `belgium_storm_formation_map.html`
- `belgium_windy_compare.html`
- `weather_layers_grid.csv`
- `convective_parameters.json`

## Notes

- RainViewer radar tiles are loaded client-side in the HTML map.
- Humidity, dew point and storm formation layers are derived from the MeteoVoid station forecasts.
- The storm formation layer is an operational derived index, not an official convective model field.
- Windy is optional and uses a browser-side manual API key entry to avoid exposing secrets in GitHub artifacts.
