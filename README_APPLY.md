# MeteoVoid hotfix mypy (api.py)

Fix:
- mypy errors in src/meteovoid/api.py lines around _ts_ingest:
  float(payload.get(...)) where payload.get returns Any | None.

Change:
- Narrow None before float(...) to satisfy mypy.

Apply:
- Unzip at repo root (keeps paths)
- Commit + push
- CI should pass mypy.
