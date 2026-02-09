from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from meteovoid.cli import app

runner = CliRunner()


def test_cli_help() -> None:
    res = runner.invoke(app, ["--help"])
    assert res.exit_code == 0
    assert "meteovoid" in res.output.lower()
    assert "scan" in res.output.lower()


def test_cli_scan_writes_report(simple_series_csv: Path, tmp_path: Path) -> None:
    out = tmp_path / "report.json"
    res = runner.invoke(
        app,
        [
            "scan",
            str(simple_series_csv),
            "--max-gap-seconds",
            "3600",
            "--out",
            str(out),
        ],
    )
    assert res.exit_code == 0, res.output
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["void_count"] == 1
