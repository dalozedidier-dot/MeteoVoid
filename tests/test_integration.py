from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from meteovoid.cli import app

runner = CliRunner()


def test_end_to_end_scan_default_output(tmp_path: Path) -> None:
    csv = tmp_path / "s.csv"
    csv.write_text(
        "\n".join(
            [
                "timestamp,value",
                "2026-01-01T00:00:00Z,1",
                "2026-01-01T01:30:00Z,2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    res = runner.invoke(app, ["scan", str(csv)])
    assert res.exit_code == 0

    # Default output path is relative to CWD; CliRunner isolates FS.
    out_path = Path("meteo_void_report.json")
    assert out_path.exists()
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert report["void_count"] == 1
