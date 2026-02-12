MeteoVoid hotfix v3: Fix Live Smoke exit 137 at "Wait /health"

Root cause (from compose.log):
- meteovoid-api ran: "meteovoid python -m uvicorn ..."
- Error: No such command 'python'
This happens because the Docker image defines ENTRYPOINT=["meteovoid"].

Fix:
- Override meteovoid-api entrypoint to: python -m uvicorn
- Keep the workflow unchanged (it already uses -f docker-compose.yml -f docker-compose.ci.override.yml)

Apply:
1) Replace docker-compose.ci.override.yml at repo root with the file from this zip.
2) Commit + push.
3) Re-run "Live Smoke (Docker Compose)".
Expected:
- Wait /health passes
- live_smoke_report includes latest.json + bulletin.* + compose.log + ps.txt
