from __future__ import annotations

from pathlib import Path

import pytest

from meteovoid.core import scan_series_for_voids


def test_scan_reads_jsonl_and_json(tmp_path: Path) -> None:
    p_jsonl = tmp_path / "obs.jsonl"
    p_jsonl.write_text(
        '{"timestamp":"2026-01-01T00:00:00Z","value":0}\n'
        '{"timestamp":"2026-01-01T00:00:10Z","value":1}\n',
        encoding="utf-8",
    )
    out = scan_series_for_voids(p_jsonl, max_gap_seconds=3600)
    assert out["void_count"] == 0
    assert out["value_stats"]["count"] == 2

    p_json = tmp_path / "obs.json"
    p_json.write_text(
        '[{"timestamp":"2026-01-01T00:00:00Z","value":0},{"timestamp":"2026-01-01T00:00:10Z","value":1}]',
        encoding="utf-8",
    )
    out2 = scan_series_for_voids(p_json, max_gap_seconds=3600)
    assert out2["void_count"] == 0
    assert out2["value_stats"]["count"] == 2


def test_scan_rejects_unknown_format(tmp_path: Path) -> None:
    p = tmp_path / "x.txt"
    p.write_text("nope", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported input format"):
        scan_series_for_voids(p)
