Patch: incoherence score (Σ wᵢ φᵢ(x)) injected into latest.json and bulletin.

Outputs in live_smoke_report artifact:
- latest.json enriched with:
  - incoherence_score
  - incoherence_contributions
  - incoherence {total, breakdown, phis, weights, meta}
- bulletin.json and bulletin.md
- history.csv and history.jsonl (append-only)

φᵢ (minimal, cheap):
- φ_gap: gap duration in hours (max(gap_total_s, missing_time_s)/3600)
- φ_smoke: (smoke_index - baseline)/scale, if smoke/aqi present (or pm25/aqi proxy)
- φ_stuck: 1 if (max-min) <= eps_range and n_points >= min_points
- φ_drift: z-shift of stats.mean versus recent history.csv (needs >=5 history points)

Weights configurable in config/incoherence.json.
Apply:
- tools/postprocess_live_report.py
- config/incoherence.json
- .github/workflows/live_smoke.yml

Commit + push, rerun Live Smoke.
