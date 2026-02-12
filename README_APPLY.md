MeteoVoid hotfix v4: Live Smoke still failing with "No such command 'python'"

Evidence (logs_57258280677.zip):
- docker compose ps shows:
    meteovoid-api  COMMAND "meteovoid python -m ..."
    meteovoid-live COMMAND "meteovoid python -m ..."
- container logs show:
    No such command 'python'

Root cause:
- Image ENTRYPOINT=["meteovoid"] is still active.
- Your CI override changed "command" but not in a way that prevents ENTRYPOINT from prepending "meteovoid".

Fix:
- Override entrypoint to ["sh","-lc"] (guaranteed to replace ENTRYPOINT)
- Provide command as a shell string:
    python -m uvicorn meteovoid.api:app ...
    meteovoid live ...

Apply:
- Replace docker-compose.ci.override.yml with this one.
- Commit + push, rerun Live Smoke.

Expected:
- ps shows meteovoid-api command starts with "sh -lc python -m uvicorn ..."
- /health becomes ok
- live_smoke_report contains latest.json + bulletin.*
