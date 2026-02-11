# MeteoVoid hotfix: ruff-format + black (api.py)

Your CI log shows:
- ruff-format: would reformat src/meteovoid/api.py
- black: would reformat src/meteovoid/api.py (diff around dashboard rows.append)

Fix:
- Use the exact formatting black expects for rows.append:
    rows.append("<tr>" f"...")

Apply:
1) Unzip at repo root (keeps paths).
2) Commit + push.
3) CI pre-commit should pass.

This patch includes the mypy-safe _ts_ingest() too.
