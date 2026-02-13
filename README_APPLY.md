Patch: Incoherence score (gaps + out-of-range + stuck) + bulletin in live_smoke_report

What you get:
- latest.json enriched with an "incoherence" object:
  - score (0..1), severity (low/medium/high)
  - components: gap/range/stuck
  - weights and meta (expected ranges, notes)
- bulletin.md + bulletin.json produced in _ci_out/live_smoke/
- history.csv + history.jsonl appended each run

Files:
- src/meteovoid/incoherence.py
- tools/generate_bulletin.py
- config/incoherence_defaults.json
- tests/test_incoherence.py
- .github/workflows/live_smoke.yml (adds the bulletin generation step)

Apply:
- Unzip at repo root (overwrite files)
- Commit + push
- Re-run Live Smoke
