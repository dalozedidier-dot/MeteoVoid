This patch adds graphs to the Live Smoke artifact.

What you get in the live_smoke_report artifact:
- latest.json (raw)
- latest_enriched.json (adds incoherence)
- bulletin.json and bulletin.md (human readable)
- history.csv and history.jsonl (append-only)
- fig_score.png (timeline, anomalous points marked)
- fig_incoherence.png (timeline)
- fig_contributions.png (latest incoherence breakdown)

Apply
- Unzip at repo root and overwrite files.
- Commit and push.
- Run Actions: Live Smoke (Docker Compose)

Notes
- The workflow installs matplotlib on the GitHub runner to generate PNGs.
- It does not change your Docker images.
