# MeteoVoid Belgium structural hardening patch

This patch is intentionally focused on stability rather than adding another visual layer.

## Included changes

- Removes duplicate renderer definitions from `tools/generate_belgium_alert_report.py`.
- Adds explicit non-official notification fields:
  - `notification_allowed`
  - `public_wording`
  - `official_alert`
- Keeps `public_alert_allowed` only as a backward-compatible deprecated alias.
- Adds minimal JSON contract validation for Belgium outputs.
- Adds schemas in `schemas/` for stable downstream contracts.
- Adds `tools/validate_belgium_contracts.py` and runs it in the Belgium GitHub workflow.
- Makes Redis-backed CLI commands lazy-import their live modules, so `meteovoid scan` can run from a base install.
- Copies `config/` and `tools/` into the Docker image, because the live compose stack and Belgium workflows need those files.
- Adds targeted tests for generated Belgium output contracts.

## Why this patch matters

MeteoVoid Belgium already has many features. The next risk is not missing functionality, but silent breakage: JSON output shape changes, duplicate function definitions, Docker images missing config files, and ambiguous public-alert wording.

This patch makes the system safer to extend.
