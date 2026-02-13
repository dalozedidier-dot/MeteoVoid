MeteoVoid Live Smoke hotfix v7 (host polling + CLI subcommands)

Why this exists:
- Your failing run shows: "service meteovoid-api is not running" during docker compose exec.
- That happens when the API container starts then exits quickly, or restarts.
- Using docker compose exec for health/latest makes the workflow brittle.
- Also, the image uses ENTRYPOINT=["meteovoid"], so the safest is to use CLI subcommands:
  - meteovoid serve / live / simulate

What this patch changes:
1) docker-compose.ci.override.yml
   - meteovoid-api uses: command ["serve", ...]
   - meteovoid-live uses: command ["live", ...]
   - meteovoid-simulate uses: command ["simulate", ...]
2) .github/workflows/live_smoke.yml
   - health + latest are polled from the HOST: http://localhost:8000
     (no docker compose exec needed)
   - logs/ps are always captured

Apply:
- Replace docker-compose.ci.override.yml
- Replace .github/workflows/live_smoke.yml
- Commit + push
- Re-run Live Smoke
