# MeteoVoid hotfix v4: format live.py for ruff-format + black

Logs show:
- ruff-format FAILED: would reformat src/meteovoid/live.py
- black FAILED: would reformat src/meteovoid/live.py

Fix:
- Apply the exact line-break black wants in LiveConfig.thresholds() for the watch expression.

File replaced:
- src/meteovoid/live.py
