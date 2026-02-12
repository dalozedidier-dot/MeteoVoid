MeteoVoid patch (CI + Live Smoke + ingest + bulletin)

Files included (overwrite in repo):
- .github/workflows/live_smoke.yml
- src/meteovoid/ingest_europe.py
- src/meteovoid/stations_config.py
- tools/generate_bulletin.py

What it fixes:
- pre-commit: black reformat issues (ingest_europe.py + generate_bulletin.py)
- mypy: Optional[int] + redis.xadd typing in ingest_europe.py
- mypy: yaml stubs warning (stations_config.py)
- live smoke: robust /health wait + generates bulletin.md + bulletin.json + history.csv in live_smoke_report artifact

Apply:
1) Unzip at repo root (keep paths).
2) git add -A
3) git commit -m "fix: live smoke health + bulletin, ingest typing/format"
4) git push
