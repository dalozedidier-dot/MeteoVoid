Patch: fix black formatting failures seen in CI logs.

Replaces two files with black-compliant formatting:
- src/meteovoid/incoherence.py
- tools/postprocess_live_report.py

Apply: unzip at repo root (overwrite), commit, push.
