# Changelog

## Belgium public interface — visual refresh and interactive location map

- Visual redesign of the three views: a radial (270°) "void collapse" gauge in the
  banners, the seven convective-transition components rendered as progress-ring cards
  with icons, severity-tinted status banners, icon metric tiles, confidence meters, a
  smoothed timeline (gradient area, high-threshold line, timestamped markers) and a
  refreshed dark header. Sober palette: red reserved for real danger.
- New **Carte** tab with an interactive Leaflet map (CARTO Voyager basemap): one marker
  per MeteoVoid station, sized by score and coloured by severity, an optional RainViewer
  radar overlay (off by default) and a **location selector**. Choosing a place (or
  clicking a marker) recenters the map and opens a detail panel with that location's
  operational readout (score, drivers, hourly sparkline, signals). Degrades gracefully:
  if the basemap cannot load, the selector and detail panel still work.
- `api/stations.json` now exposes every station with `lat`/`lon`, driver metrics and a
  compact hourly score trace so the map and external clients can render locations.

## Belgium public interface redesign — three reading levels + static JSON API

- Rebuilt `tools/build_belgium_public_site.py` around three reading levels instead of
  showing every card at once:
  - **Vue simple** — operational level, MeteoVoid score, run confidence, critical window,
    main zone and an automatic synthesis sentence.
  - **Vue opérationnelle** — a *Convective Transition* gauge with seven blocks (charge,
    déclencheur, organisation, couvercle, observation, propagation amont, void collapse
    signal), each with a score, colour, explanatory sentence and the responsible drivers;
    an hourly timeline (SVG curve + automatic narrative) and an automatic "why this alert"
    explanation.
  - **Vue expert** — stations/zones, emerging-observation channels, scientific validation,
    source health and the existing maps/graphs/exports, grouped by usage and behind tabs.
- Added a clean static JSON API under `_site/api/`: `latest.json`, `stations.json`,
  `timeline.json`, `transition.json`, `sources.json`, `validation.json` and an
  `index.json` manifest. The page reads these files when served over HTTP and falls back
  to an inlined view-model offline.
- Sober design: light/night-blue palette, white cards, red reserved for real danger,
  orange for watch, blue/grey for information.
- Added `tests/test_build_public_site.py` (API shape, colour mapping, empty-run robustness).

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

## Critical Transition Pack

- Added early warning signals for critical transitions: lag-1 autocorrelation, variance growth, skewness, flickering and station-level transition phase.
- Added an information graph based on lagged correlations and a transfer-entropy proxy between stations.
- Added validation metrics scaffold with POD, FAR, CSI, Brier score, cost-loss thresholds and conformal prediction placeholder.
- Added system self-watchdog outputs for source health, stale run detection, required outputs and graceful degradation.
- Added extended perception status for satellite, GNSS water vapour, pressure crowd sources, radar and lightning readiness.
- Added CAP XML test export and a static JSON API for GitHub Pages.
- Extended the public dashboard with Signaux précoces, Graphe informationnel, Validation and Auto-surveillance tabs.
