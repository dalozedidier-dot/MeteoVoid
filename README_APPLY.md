MeteoVoid - release.yml fix (v2)

Problem (from your logs):
- publish-pypi failed with `invalid-publisher` because PyPI Trusted Publisher is not configured.
- Also, running the workflow on `workflow_dispatch` (main branch) should not attempt to publish.

Fix:
- publish-pypi and github-release now run ONLY on tags (refs/tags/v*).
- publish step supports two modes:
  A) API token via secrets.PYPI_API_TOKEN (works immediately).
  B) Trusted Publisher OIDC (works only after configuring a publisher on PyPI).

Action:
- If you want immediate publishing: add repository secret PYPI_API_TOKEN (PyPI token) and tag vX.Y.Z.
- If you prefer OIDC: configure the Trusted Publisher on PyPI to match:
  repo: dalozedidier-dot/MeteoVoid
  workflow: .github/workflows/release.yml
  environment: pypi
