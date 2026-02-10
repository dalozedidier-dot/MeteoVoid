from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import typer

from .live import LiveConfig, analyze_window
from .simulate import push_synthetic_stream
from .stream import run_live_worker

app = typer.Typer(
    add_completion=False,
    help="meteovoid: live smoke (Redis Streams) + offline scan (CSV).",
)


def _parse_iso(ts: str) -> datetime:
    s = ts.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    xs = sorted(values)
    # nearest-rank p95
    k = int(round(0.95 * (len(xs) - 1)))
    return float(xs[max(0, min(len(xs) - 1, k))])


def _trend_slope(t: list[float], y: list[float]) -> float:
    n = min(len(t), len(y))
    if n < 2:
        return 0.0
    t0 = t[0]
    tt = [ti - t0 for ti in t[:n]]
    yy = y[:n]
    mt = sum(tt) / n
    my = sum(yy) / n
    num = sum((tt[i] - mt) * (yy[i] - my) for i in range(n))
    den = sum((tt[i] - mt) ** 2 for i in range(n))
    return float(num / den) if den != 0.0 else 0.0


@app.command()
def scan(
    csv_path: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    max_gap_seconds: int = typer.Option(3600, "--max-gap-seconds"),
    out: Path = typer.Option(Path("report.json"), "--out"),
    station_id: str = typer.Option("S1", "--station-id"),
    variable: str = typer.Option("wind_gust_ms", "--variable"),
    window_s: int = typer.Option(1800, "--window-s"),
) -> None:
    """Scan a CSV (timestamp,value) and write a JSON report."""
    times: list[datetime] = []
    values: list[float] = []

    with csv_path.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            ts_raw = (row.get("timestamp") or "").strip()
            v_raw = (row.get("value") or "").strip()
            if not ts_raw or not v_raw:
                continue
            try:
                times.append(_parse_iso(ts_raw))
                values.append(float(v_raw))
            except ValueError:
                continue

    if not times or not values:
        report: dict[str, Any] = {
            "ts": datetime.now().astimezone().isoformat(),
            "station_id": station_id,
            "variable": variable,
            "window_s": window_s,
            "score": 0.0,
            "state": "stable",
            "data_points": 0,
            "missing_frac": 1.0,
            "p95": 0.0,
            "trend": 0.0,
            "explain": {"variance_jump": 0.0, "slope_change": 0.0, "outlier_frac": 0.0},
        }
    else:
        # compute missing
        secs = [dt.timestamp() for dt in times]
        gaps = [secs[i] - secs[i - 1] for i in range(1, len(secs))]
        missing_events = sum(1 for g in gaps if g > float(max_gap_seconds))
        missing_frac = float(missing_events) / float(max(1, missing_events + len(values)))

        cfg = LiveConfig(window_s=window_s)
        base = dict(analyze_window(values, cfg))

        trend = _trend_slope(secs, values)
        p95 = _p95(values)

        variance_jump = float(base.get("score", 0.0))
        slope_change = abs(trend)
        # cheap outlier ratio
        mu = sum(values) / len(values)
        var = sum((v - mu) ** 2 for v in values) / max(1, len(values))
        std = var**0.5
        outlier_frac = (
            float(sum(1 for v in values if std > 0.0 and abs(v - mu) > 3.0 * std)) / float(len(values))
        )

        score = min(1.0, 0.6 * variance_jump + 0.3 * slope_change + 0.1 * outlier_frac)
        state = "stable" if score < 0.15 else "unstable" if score > 0.30 else "transition"

        report = {
            "ts": times[-1].astimezone().isoformat().replace("+00:00", "Z"),
            "station_id": station_id,
            "variable": variable,
            "window_s": window_s,
            "score": float(score),
            "state": state,
            "data_points": int(len(values)),
            "missing_frac": float(missing_frac),
            "p95": float(p95),
            "trend": float(trend),
            "explain": {
                "variance_jump": float(variance_jump),
                "slope_change": float(slope_change),
                "outlier_frac": float(outlier_frac),
            },
        }

    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    typer.echo(str(out))


@app.command()
def simulate(
    redis_url: str = "redis://redis:6379/0",
    stream: str = "meteovoid:observations",
    station_id: str = "S1",
    variable: str = "wind_gust_ms",
    steps: int = 200,
    sleep: float = 0.01,
) -> None:
    push_synthetic_stream(redis_url, stream, station_id, variable, steps, sleep)


@app.command()
def live(
    redis_url: str = "redis://redis:6379/0",
    in_stream: str = "meteovoid:observations",
    out_stream: str = "meteovoid:reports",
) -> None:
    run_live_worker(redis_url, in_stream, out_stream)


@app.command()
def serve(host: str = "0.0.0.0", port: int = 8000) -> None:
    import uvicorn

    uvicorn.run("meteovoid.api:app", host=host, port=port)


def main() -> None:
    app()
