from __future__ import annotations

import json
import time
from pathlib import Path

import typer

from .core import scan_series_for_voids

app = typer.Typer(
    name="meteovoid",
    add_completion=True,
    help="MeteoVoid CLI. Batch void scanning and live instability scoring for time-series streams.",
)


@app.callback()
def _root() -> None:
    """MeteoVoid CLI."""


@app.command()
def scan(
    csv: Path = typer.Argument(..., exists=True, readable=True, help="Path to a CSV file."),
    time_col: str = typer.Option("timestamp", "--time-col", help="Name of the timestamp column."),
    value_col: str = typer.Option("value", "--value-col", help="Name of the numeric value column."),
    max_gap_seconds: int = typer.Option(3600, "--max-gap-seconds", help="Gap threshold to call a void."),
    out: Path = typer.Option(Path("meteo_void_report.json"), "--out", "-o", help="Output JSON file."),
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


@app.command("live")
def live_cmd(
    redis_url: str = typer.Option("redis://redis:6379/0", "--redis-url", help="Redis connection URL."),
    in_stream: str = typer.Option(
        "meteovoid:observations", "--in-stream", help="Redis stream name for incoming observations."
    ),
    out_stream: str = typer.Option(
        "meteovoid:reports", "--out-stream", help="Redis stream name for outgoing reports."
    ),
    window_s: int = typer.Option(1800, "--window-s", help="Rolling window size in seconds."),
    expected_interval_s: int = typer.Option(60, "--interval-s", help="Expected sampling interval in seconds."),
    stable_threshold: float = typer.Option(0.15, "--stable-threshold", help="Stable threshold for score."),
    unstable_threshold: float = typer.Option(0.30, "--unstable-threshold", help="Unstable threshold for score."),
) -> None:
    """Run the live worker: reads observations from Redis Streams and emits live reports."""
    from .stream import live_worker

    live_worker(
        redis_url=redis_url,
        in_stream=in_stream,
        out_stream=out_stream,
        window_s=window_s,
        expected_interval_s=expected_interval_s,
        stable_threshold=stable_threshold,
        unstable_threshold=unstable_threshold,
    )


@app.command("simulate")
def simulate_cmd(
    redis_url: str = typer.Option("redis://redis:6379/0", "--redis-url", help="Redis connection URL."),
    stream: str = typer.Option("meteovoid:observations", "--stream", help="Redis stream to publish observations into."),
    seconds: int = typer.Option(3 * 3600, "--seconds", help="Duration of the synthetic dataset to publish."),
    interval_s: int = typer.Option(60, "--interval-s", help="Sampling interval in seconds."),
    seed: int = typer.Option(7, "--seed", help="Random seed."),
    sleep: float = typer.Option(0.0, "--sleep", help="Sleep between points to emulate real time."),
) -> None:
    """Publish a synthetic time series to Redis Streams."""
    from .simulate import synthetic_wind_gust_series
    from .stream import make_redis, stream_observations
    from datetime import datetime, timedelta, timezone

    r = make_redis(redis_url)
    start = datetime.now(timezone.utc) - timedelta(seconds=seconds)

    for obs in synthetic_wind_gust_series(start=start, seconds=seconds, interval_s=interval_s, seed=seed):
        stream_observations(r, stream, obs)
        if sleep > 0:
            time.sleep(sleep)

    typer.echo(f"Published synthetic observations to {stream}")


@app.command("serve")
def serve_cmd(
    host: str = typer.Option("0.0.0.0", "--host", help="Host to bind."),
    port: int = typer.Option(8000, "--port", help="Port to bind."),
) -> None:
    """Run the live API server (FastAPI + Uvicorn)."""
    import uvicorn
    from .api import app as api_app

    uvicorn.run(api_app, host=host, port=port, log_level="info")


def main(argv: list[str] | None = None) -> None:
    """Console entry point."""
    app(prog_name="meteovoid", args=argv)
