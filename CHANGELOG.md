# Changelog

## 0.1.0

- Initial project skeleton.

## Belgium Alert extended system update

- Add hourly station risk timelines.
- Add `risk_timeseries.json` and `risk_timeline.csv`.
- Add province/zone summaries in JSON and CSV.
- Add Leaflet heatmap output.
- Add notification state output with cooldown and dedupe key.
- Add replay metrics scaffold for future historical validation.
- Extend Markdown and manifest outputs.
- Add tests for extended Belgium alert outputs.

## Belgium alert extended operational layer

- Added fail-safe auto external connectors for IRM/KMI warning/forecast pages, MeteoAlarm Belgium Atom feed and ESTOFEX text bulletin.
- Added configurable nowcast endpoints for radar and lightning confirmations.
- Added calibration profile support through `config/belgium_scoring_calibration.yaml` and `calibration_report.json`.
- Added simplified Belgium province GeoJSON layer and `belgium_province_map.html`.
- Added replay validation outputs and `tools/replay_belgium_alert_history.py`.
- Extended GitHub Actions workflow with auto-external inputs, optional radar/lightning secrets, calibration, province map and replay configuration.

## Belgium weather layers pack

- Added advanced weather layer outputs for Belgium.
- Added RainViewer radar overlay page.
- Added humidity, dew point and storm formation maps.
- Added interpolated `weather_layers_grid.csv`.
- Added `convective_parameters.json`.
- Added optional Windy comparison page that does not expose API keys by default.
- Added targeted weather layer tests.
