Fix for logs_57266689100.zip:
- /latest timed out with {status: not_found}
- docker compose ps showed meteovoid-live running "meteovoid python -m ..." which never starts (ENTRYPOINT issue)

This patch:
1) docker-compose.ci.override.yml
   - overrides ENTRYPOINT for meteovoid-api, meteovoid-live, meteovoid-simulate using ["sh","-lc"]
   - ensures commands are executed as intended (no "meteovoid python ..." prefix)

2) live_smoke.yml
   - unchanged logic, but logs tail now includes meteovoid-live for easier diagnosis

Apply:
- Replace docker-compose.ci.override.yml
- Replace .github/workflows/live_smoke.yml
- Commit + push, rerun Live Smoke
Expected:
- ps shows meteovoid-live command starts with "sh -lc meteovoid live ..."
- /latest returns a report with score/state
- live_smoke_report artifact includes latest.json + bulletin.* + logs
