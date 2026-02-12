Patch: add unit tests to restore coverage >= 85%

Problem (from logs):
- src/meteovoid/ingest_europe.py: 0% covered
- src/meteovoid/stations_config.py: 0% covered

This patch adds:
- tests/test_stations_config.py
- tests/test_ingest_europe.py

These tests are network-free and do not require a real Redis instance.
They also pass Ruff + Black (no unused imports).
