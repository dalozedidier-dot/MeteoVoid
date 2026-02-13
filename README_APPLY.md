Fix pre-commit failures for tools/append_live_history.py

From logs:
- ruff: UP038 (use X | Y in isinstance), UP017 (datetime.UTC)
- black: would reformat tools/append_live_history.py

This patch replaces the file with a ruff+black compatible version.

Apply:
- Replace tools/append_live_history.py with the one from this zip.
- Commit + push.
