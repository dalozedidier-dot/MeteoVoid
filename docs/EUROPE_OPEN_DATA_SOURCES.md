# Europe open-data source strategy

MeteoVoid must not mix sources silently. Each map needs one clear operational state:
forecast model, observed radar, or short-term nowcast.

## Current active source

Open-Meteo remains the default Europe-wide forecast source because it works without a key and covers the whole European view consistently. It is used for the browser-side Europe and country pages.

## Candidate enrichments

- Germany: Bright Sky / DWD for observations and MOSMIX forecasts.
- Switzerland: MeteoSwiss Open Data, ideally server-side because STAC and GRIB products need normalization.
- Greece: meteostations-gr-api for live station observations if the service is healthy.
- Europe-wide: Climate Pulse as an aggregator candidate, after contract pinning and health checks.
- Validation and history: Meteostat, plus national APIs where allowed.
- Norway: Frost API, but only after token and secrets handling are documented.

## Integration rule

A candidate source should become active only when it has:

1. a documented schema;
2. source health checks;
3. cache rules;
4. attribution;
5. tests;
6. a visible source label in the UI.

The UI must show what the play button animates:

- forecast model;
- observed radar;
- short-term nowcast.

These three temporalities must not be merged into one ambiguous slider.
