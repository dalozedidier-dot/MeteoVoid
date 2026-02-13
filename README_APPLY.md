Fix for logs_57319537478:
- /health on the HOST failed (no published port in docker-compose.yml),
  causing a health timeout.

This patch makes Live Smoke independent of published ports:
- /health and /latest are polled from INSIDE the meteovoid-api container via python urllib.
- It still writes latest.json to _ci_out/live_smoke/latest.json on the runner.

Adds lightweight incoherence score (Σ wᵢ φᵢ(x)):
- tools/postprocess_live_report.py
- config/incoherence.json
- workflow step to enrich latest.json and generate bulletin.* + history.*

Outputs in live_smoke_report:
- latest.json (enriched)
- bulletin.json + bulletin.md
- history.csv + history.jsonl
- ps.txt + compose.log
