Hotfix v6 (CI override uses the meteovoid CLI subcommands)

Why:
- Your image uses ENTRYPOINT=["meteovoid"].
- When docker-compose.yml uses "python -m ..." as command, it becomes:
    meteovoid python -m ...
  and crashes: "No such command 'python'".
- Our earlier uvicorn-based override can also crash if uvicorn isn't in the image.

Fix:
- In docker-compose.ci.override.yml we set:
  - meteovoid-api: command = ["serve", "--host", "0.0.0.0", "--port", "8000"]
  - meteovoid-live: command = ["live", ...]
  - meteovoid-simulate: command = ["simulate", ...]
  This matches the CLI that's already inside the image.

Also:
- live_smoke.yml prints `docker compose ps` to stdout (faster diagnosis when it fails).

Apply:
- Replace docker-compose.ci.override.yml
- Replace .github/workflows/live_smoke.yml
- Commit + push, rerun Live Smoke

Expected:
- meteovoid-api stays running
- meteovoid-live consumes seeded observations and writes reports
- /latest returns a report with score+state
- live_smoke_report includes latest.json + bulletin.* + ps.txt + compose.log
