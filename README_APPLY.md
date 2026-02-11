# MeteoVoid hotfix: black formatting in dashboard (api.py)

Your CI is failing because pre-commit says:
  would reformat src/meteovoid/api.py

Fix:
- Avoid chaining `.replace(...)` directly on the giant triple-quoted HTML.
- Do it in two steps:
    html = """..."""
    html = html.replace("__ROWS__", rows_html)

Apply:
- Unzip at repo root
- Commit + push
- CI should pass pre-commit (black/ruff-format).
