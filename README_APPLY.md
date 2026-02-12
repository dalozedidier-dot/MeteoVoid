Patch v2 (recommended): CI override + full live_smoke_report

Why:
- Your logs show meteovoid-api runs `meteovoid uvicorn ...` and crashes with:
  "No such command 'uvicorn'" -> wait /health fails (exit 137) -> artifact misses latest.json/bulletin.

What this patch does:
1) Adds docker-compose.ci.override.yml
   - overrides ONLY meteovoid-api command + healthcheck
   - avoids clobbering your existing docker-compose.yml (simulate/live/etc stay as-is)

2) Replaces .github/workflows/live_smoke.yml
   - uses both compose files: docker-compose.yml + docker-compose.ci.override.yml
   - seeds observations (prefer meteovoid-simulate if present, otherwise redis-cli fallback)
   - saves _ci_out/live_smoke/latest.json
   - runs tools/generate_bulletin.py to produce bulletin.md + bulletin.json + history.*
   - uploads full live_smoke_report artifact

Apply:
- drop the two files at their paths, commit, push, rerun Live Smoke.
