from __future__ import annotations

import json
from pathlib import Path

import typer

from .core import scan_series_for_voids
from .simulate import push_synthetic_stream
from .stream import run_live_worker

app = typer.Typer(
    add_completion=False,
    help="meteovoid: offline void scan (CSV) + live pipeline (Redis Streams).",
)


@app.command()
def scan(
    csv_path: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    time_col: str = typer.Option("timestamp", "--time-col"),
    value_col: str = typer.Option("value", "--value-col"),
    max_gap_seconds: int = typer.Option(3600, "--max-gap-seconds"),
    out: Path = typer.Option(Path("meteo_void_report.json"), "--out"),
) -> None:
    """Detect gaps (voids) in a CSV time series and write a JSON report."""
    report = scan_series_for_voids(
        csv_path,
        time_col=time_col,
        value_col=value_col,
        max_gap_seconds=max_gap_seconds,
    )
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    typer.echo(str(out))


@app.command()
def simulate(
    redis_url: str = "redis://redis:6379/0",
    stream: str = "meteovoid:observations",
    station_id: str = "DEMO_BE_0001",
    variable: str = "wind_gust_ms",
    steps: int = 250,
    sleep: float = 0.01,
) -> None:
    """Publish synthetic observations into a Redis Stream."""
    push_synthetic_stream(redis_url, stream, station_id, variable, steps, sleep)


@app.command()
def live(
    redis_url: str = "redis://redis:6379/0",
    in_stream: str = "meteovoid:observations",
    out_stream: str = "meteovoid:reports",
) -> None:
    """Consume observations from Redis Streams and emit live reports."""
    run_live_worker(redis_url, in_stream, out_stream)


@app.command()
def serve(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Serve the live HTTP API (FastAPI)."""
    import uvicorn

    uvicorn.run("meteovoid.api:app", host=host, port=port)


@app.command()
def ingest(
    config: Path = typer.Option(
        Path("config/stations_europe.yaml"),
        "--config",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Stations YAML config path.",
    ),
    redis_url: str = typer.Option("redis://redis:6379/0", "--redis-url"),
    out_stream: str = typer.Option("meteovoid:observations", "--out-stream"),
    poll_seconds: int = typer.Option(60, "--poll-seconds", help="Polling interval in seconds."),
    once: bool = typer.Option(False, "--once", help="Fetch once and exit."),
    per_stream: bool = typer.Option(
        False, "--per-stream", help="Also write per-station/variable stream."
    ),
) -> None:
    """Ingest live weather observations from Open-Meteo into Redis Streams (production mode)."""
    from .ingest_europe import main as _ingest_main

    argv = [
        "--config",
        str(config),
        "--redis-url",
        redis_url,
        "--out-stream",
        out_stream,
        "--poll-seconds",
        str(poll_seconds),
    ]
    if once:
        argv.append("--once")
    if per_stream:
        argv.append("--per-stream")
    raise SystemExit(_ingest_main(argv))


def main() -> None:
    app()
