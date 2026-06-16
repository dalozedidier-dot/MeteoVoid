# MeteoVoid Belgium hardening and upstream graph layer

This update turns the Belgium alert package from patch-stacked output generation into a more maintainable and lighter public dashboard build.

## Main corrections

- Removed the duplicated renderer definitions from `tools/generate_belgium_alert_report.py`.
- Kept a single active implementation for map, dashboard and Markdown rendering.
- Made the station GeoJSON lightweight: hourly details remain in `risk_timeseries.json` instead of being repeated in every GeoJSON feature.
- Removed hard Redis typing imports from the base import path.
- Moved Redis imports to live-only execution paths where possible.
- Added a first graph-based upstream layer that uses station adjacency to detect contiguous corridors of risk.

## New graph outputs

The run now generates:

- `upstream_graph_summary.json`
- `upstream_graph_edges.csv`
- `upstream_graph.html`

The graph layer is experimental. It links nearby stations and evaluates whether high-risk stations form a coherent corridor. This is not yet a wind-vector propagation model, but it is the first concrete step toward the original MeteoVoid idea: detecting upstream silence, spatial coherence and risk propagation rather than treating each station as isolated.

## Public page integration

The GitHub Pages public site now copies the graph outputs and includes a `Graphe amont` tab.

## Remaining structural work

The generator is still large and should eventually be split into importable modules under `src/meteovoid/belgium/`:

- sources
- scoring
- graph
- maps
- dashboard
- reports
- validation
- notification

This update removes the most dangerous duplicate-code issue and adds the missing graph direction, but it does not claim to be the full architectural refactor.
