# Changelog

## Belgium public dashboard and GitHub Pages

- Added `tools/build_belgium_public_site.py` to build a cleaner public static dashboard from MeteoVoid Belgium outputs.
- Added `.github/workflows/belgium_pages.yml` to publish the latest Belgium dashboard through GitHub Pages.
- Improved advanced weather-layer maps: lower visual opacity, smaller interpolation markers, clearer default layers and safer RainViewer zoom behavior.
- Added documentation in `docs/BELGIUM_PUBLIC_PAGE.md`.
- Added public site regression test.


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
## MeteoVoid Convective Transition Engine

- Added an experimental convective transition diagnostic layer for Belgium.
- New outputs: `convective_transition_report.json`, `convective_transition_by_station.csv`, `convective_transition_report.md`, `convective_transition_dashboard.html`.
- Added six systemic indices: convective load, trigger readiness, storm organization potential, lid fragility, latent risk gap, and void collapse signal.
- Added `config/convective_transition_engine.yaml` to document weights, thresholds and future native inputs.
- Added tests for the transition engine and integrated the outputs in the Belgium report workflow.

## Belgium graph hardening update

- Removed duplicated dead renderer definitions from `tools/generate_belgium_alert_report.py`.
- Lightened `risk_by_station.geojson` by moving hourly details exclusively to `risk_timeseries.json`.
- Added upstream graph outputs: `upstream_graph_summary.json`, `upstream_graph_edges.csv`, `upstream_graph.html`.
- Added `Graphe amont` to the public GitHub Pages dashboard.
- Made Redis-related imports lazier so base imports are less dependent on the `live` extra.
- Added `docs/BELGIUM_GRAPH_AND_HARDENING.md`.
