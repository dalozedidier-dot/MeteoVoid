Patch v8: Make live_smoke_report a real "bulletin + history" bundle

What you get in the artifact:
- latest.json
- bulletin.md + bulletin.json
- history.csv + history.jsonl (always at least 1 row)
- ps.txt + compose.log

Changes:
1) New tool: tools/append_live_history.py
   Appends latest.json into history.csv/history.jsonl (creates header if needed).

2) live_smoke.yml
   Adds a step "Append history" after bulletin generation.
   Also improves fallback seeding to vary values (avoid always score=0).

3) docker-compose.ci.override.yml
   Uses CLI subcommands (serve/live/simulate), compatible with ENTRYPOINT=["meteovoid"].

Apply:
- Replace docker-compose.ci.override.yml
- Replace .github/workflows/live_smoke.yml
- Add tools/append_live_history.py
- Commit + push
