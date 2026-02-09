from __future__ import annotations

import json
from pathlib import Path

import typer

from .core import scan_series_for_voids

app = typer.Typer(
    name="meteovoid",
    add_completion=True,
    help="Detects data voids (unexpected gaps) and basic anomalies in CSV time series.",
)


@app.callback()
def _root() -> None:
    """MeteoVoid CLI."""
    # Having a callback forces Typer to generate a Group,
    # so the CLI stays stable as `meteovoid scan ...` even with a single command.
    return


@app.command()
def scan(
    csv: Path = typer.Argument(..., exists=True, readable=True, help="Path to a CSV file."),
    time_col: str = typer.Option("timestamp", "--time-col", help="Name of the timestamp column."),
    value_col: str = typer.Option("value", "--value-col", help="Name of the numeric value column."),
    max_gap_seconds: int = typer.Option(
        3600,
        "--max-gap-seconds",
        help="Gap threshold to call a void.",
    ),
    out: Path = typer.Option(
        Path("meteo_void_report.json"),
        "--out",
        "-o",
        help="Output JSON file.",
    ),
) -> None:
    """Scan a CSV file and output a JSON report."""
    report = scan_series_for_voids(
        csv_path=csv,
        time_col=time_col,
        value_col=value_col,
        max_gap_seconds=max_gap_seconds,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    typer.echo(str(out))


def main(argv: list[str] | None = None) -> None:
    """Console entry point."""
    # Typer uses sys.argv by default; argv is here mainly for testability.
    app(prog_name="meteovoid", args=argv)
