Fix for logs_57324456881:

Observed error:
- meteovoid-api container ran: "meteovoid uvicorn ..." then exited.
- CLI error: No such command 'uvicorn'.

Root cause:
- The image ENTRYPOINT is "meteovoid", but the CLI does not expose an "uvicorn" subcommand.
- Therefore any compose command like "uvicorn ..." becomes "meteovoid uvicorn ..." and fails.

This patch:
- Adds docker-compose.ci.override.yml forcing correct CLI commands:
  - meteovoid-api: serve --host 0.0.0.0 --port 8000
  - meteovoid-live: live ...
  - meteovoid-simulate: simulate ...
- Updates .github/workflows/live_smoke.yml to always use the override file.

Apply:
- Put docker-compose.ci.override.yml at repo root
- Replace .github/workflows/live_smoke.yml
- Commit + push, rerun Live Smoke
