from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import typer

from .core import scan_series_for_voids
from .simulate import push_synthetic_stream
from .stream import run_live_worker

app = typer.Typer(
    add_completion=False,
    help="meteovoid: offline void scan (CSV) + live smoke (Redis Streams).",
)


@app.command()
def scan(
    csv_path: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Input CSV. Must contain timestamp and value columns.",
    ),
    time_col: str = typer.Option("timestamp", help="Timestamp column name."),
    value_col: str = typer.Option("value", help="Value column name."),
    max_gap_seconds: int = typer.Option(3600, help="Gap threshold (seconds) to count a void."),
    out: Path = typer.Option(Path("meteo_void_report.json"), help="Output JSON report path."),
) -> None:
    """Scan a CSV time series and write a void report as JSON."""
    report: dict[str, Any] = scan_series_for_voids(
        csv_path,
        time_col=time_col,
        value_col=value_col,
        max_gap_seconds=max_gap_seconds,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    typer.echo(str(out))


@app.command()
def live(
    redis_url: str = typer.Option("redis://redis:6379/0", help="Redis URL."),
    in_stream: str = typer.Option("meteovoid:observations", help="Input Redis Stream name."),
    out_stream: str = typer.Option("meteovoid:reports", help="Output Redis Stream name."),
    start_id: str = typer.Option(
        "$",
        help="Redis stream start id. Use 0-0 to consume existing messages.",
    ),
) -> None:
    """Run the long-lived live worker reading Redis Streams."""
    # Allow docker-compose or CI to force consumption from the beginning.
    os.environ.setdefault("METEOVOID_START_ID", start_id)
    run_live_worker(redis_url=redis_url, in_stream=in_stream, out_stream=out_stream)


@app.command()
def simulate(
    redis_url: str = typer.Option("redis://redis:6379/0", help="Redis URL."),
    stream: str = typer.Option("meteovoid:observations", help="Redis Stream name."),
    station_id: str = typer.Option("DEMO_BE_0001", help="Station id."),
    variable: str = typer.Option("wind_gust_ms", help="Variable name."),
    steps: int = typer.Option(250, help="Number of points to generate."),
    sleep: float = typer.Option(0.01, help="Sleep between points (seconds)."),
) -> None:
    """Push synthetic observations into Redis Streams."""
    push_synthetic_stream(
        redis_url=redis_url,
        stream=stream,
        station_id=station_id,
        variable=variable,
        steps=steps,
        sleep=sleep,
    )


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Bind host."),
    port: int = typer.Option(8000, help="Bind port."),
    redis_url: str = typer.Option("redis://redis:6379/0", help="Redis URL."),
) -> None:
    """Start the HTTP API (FastAPI)."""
    os.environ["REDIS_URL"] = redis_url
    import uvicorn  # local import keeps CLI usable without live extras installed

    uvicorn.run("meteovoid.api:app", host=host, port=port, log_level="info")


def main() -> None:
    """Console entrypoint."""
    app()
