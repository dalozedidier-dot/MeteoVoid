Hotfix: restore RollingWindow.values(now)

Fixes failing unit test tests/test_live.py::test_analyze_window_transitions
Error was: AttributeError: 'RollingWindow' object has no attribute 'values'

This patch adds values() as a backward-compatible wrapper around samples().
It keeps analyze_window() semantics (score/state) and stays ruff/black/mypy clean.
