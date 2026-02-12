Patch: fix ruff import sorting + harden Live Smoke

1) tools/generate_bulletin.py
- Fixes Ruff I001 (import block formatting)
- Keeps stations-config fallback as a lazy import to avoid requiring PyYAML unless used

2) .github/workflows/live_smoke.yml
- Uses docker compose exec INSIDE meteovoid-api to wait /health and /latest
  (avoids host port binding issues that cause "curl: couldn't connect")
- Saves latest.json and generates bulletin + history
- Prints meteovoid-api logs tail to the workflow output for easier debugging
