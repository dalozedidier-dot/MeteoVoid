# MeteoVoid fix v3: align LiveConfig + fix mypy in stream.py + black format

Your CI failed on:
- black: would reformat src/meteovoid/live.py
- mypy: LiveConfig missing attributes (max_gap_s, impute_mode, etc.)
- mypy: float(overrides.get(...)) with Any|None

This patch:
- Restores a full LiveConfig with the attributes stream.py expects.
- Keeps State alias (imported by stream.py and cli.py).
- Keeps RollingWindow.values(now) (used by tests).
- Updates stream.py to use typed helpers (_get_float/_get_int) so mypy is happy.
- Ensures stats includes dt_median_s (contract expects it).

Files:
- src/meteovoid/live.py
- src/meteovoid/stream.py
