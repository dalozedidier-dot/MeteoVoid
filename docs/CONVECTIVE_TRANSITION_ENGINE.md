# MeteoVoid Convective Transition Engine

The Convective Transition Engine is an experimental MeteoVoid layer designed to detect when an unstable atmosphere begins to organize toward a dangerous convective regime.

It does not replace official warnings. It transforms the existing Belgium forecast outputs into six interpretable indices:

- `convective_load_index`: heat, moisture and potential energy proxy.
- `trigger_readiness_index`: proxy for the likelihood that forcing can initiate convection.
- `storm_organization_potential`: proxy for the environment's ability to sustain organized storms.
- `lid_fragility_index`: proxy for cap erosion until native CIN/LFC variables are integrated.
- `latent_risk_gap`: gap between environmental potential and observed emergence.
- `void_collapse_signal`: final MeteoVoid signal measuring the transition from latent potential to actualized convective risk.

Generated files:

- `convective_transition_report.json`
- `convective_transition_by_station.csv`
- `convective_transition_report.md`
- `convective_transition_dashboard.html`

The engine currently uses variables already available in the Belgium workflow: heat, dew point, humidity, precipitation probability, wind gust proxy, pressure-drop proxy, weather-code signal, model score and external confirmation proxy.

Future native inputs should include CAPE, CIN, 0–6 km shear, SRH, LCL/LFC, theta-e, PWAT, satellite cloud-top cooling, lightning rate and radar cell-growth diagnostics.
