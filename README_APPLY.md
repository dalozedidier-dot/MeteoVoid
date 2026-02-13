But "Run workflow" missing
- This happens when the workflow file has no "workflow_dispatch".
- This patch re-adds workflow_dispatch so GitHub shows the Run workflow button again.

Live Smoke robustness
- Uses docker-compose.ci.override.yml to bypass the image ENTRYPOINT.
  This avoids the previous crash: "No such command 'uvicorn'" (which was actually "meteovoid uvicorn ...").
- Polls /health and /latest from INSIDE the meteovoid-api container, so it does not depend on published ports.

Apply
- Drop these files at repo root:
  - .github/workflows/live_smoke.yml
  - docker-compose.ci.override.yml
- Commit and push.
- Go to Actions -> Live Smoke (Docker Compose) -> Run workflow.
