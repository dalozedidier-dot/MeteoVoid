"""Generate simple anomaly plots for Live Smoke artifacts.

Inputs
- history.csv produced by tools/postprocess_live_report.py
- latest.json or latest_enriched.json (optional)

Outputs (in out-dir)
- fig_score.png
- fig_incoherence.png
- fig_contributions.png (if incoherence breakdown exists)

The script is robust: if some columns are missing, it still produces what it can.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _parse_dt(value: str) -> datetime | None:
    v = (value or "").strip()
    if not v:
        return None

    # Epoch seconds
    try:
        if all(c in "0123456789.+-" for c in v) and any(c.isdigit() for c in v):
            return datetime.fromtimestamp(float(v), tz=UTC)
    except Exception:
        pass

    # ISO with Z
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(v)
    except Exception:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _safe_float(value: str) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


@dataclass(frozen=True)
class Row:
    ts: datetime
    score: float | None
    state: str
    severity: str
    incoherence_score: float | None


def _read_history(history_csv: Path) -> list[Row]:
    rows: list[Row] = []
    if not history_csv.exists():
        return rows

    with history_csv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for d in reader:
            ts = (
                _parse_dt(d.get("ts_ingest_iso", ""))
                or _parse_dt(d.get("ts_iso", ""))
                or _parse_dt(d.get("ts_ingest", ""))
                or _parse_dt(d.get("ts", ""))
            )
            if ts is None:
                continue

            rows.append(
                Row(
                    ts=ts,
                    score=_safe_float(d.get("score", "")),
                    state=(d.get("state", "") or "").strip(),
                    severity=(d.get("severity", "") or "").strip(),
                    incoherence_score=_safe_float(d.get("incoherence_score", "")),
                )
            )

    rows.sort(key=lambda r: r.ts)
    return rows


def _load_json(p: Path) -> dict[str, Any]:
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return d if isinstance(d, dict) else {}


def _ensure_matplotlib() -> None:
    import matplotlib

    matplotlib.use("Agg")  # type: ignore[call-arg]


def _plot_score(rows: list[Row], out_png: Path) -> None:
    _ensure_matplotlib()
    import matplotlib.pyplot as plt

    if not rows:
        return

    xs = [r.ts for r in rows]
    ys = [r.score if r.score is not None else float("nan") for r in rows]
    flags = [
        (r.state.lower() != "stable") or (r.severity.lower() in {"high", "critical"}) for r in rows
    ]

    fig = plt.figure()
    ax = fig.add_subplot(111)

    ax.plot(xs, ys, marker="o", linewidth=1)

    for x, y, bad in zip(xs, ys, flags, strict=False):
        if bad and y == y:  # not NaN
            ax.scatter([x], [y], marker="x")

    ax.set_title("Score (Live Smoke)")
    ax.set_xlabel("Time (UTC)")
    ax.set_ylabel("score")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_png)
    plt.close(fig)


def _plot_incoherence(rows: list[Row], out_png: Path) -> None:
    _ensure_matplotlib()
    import matplotlib.pyplot as plt

    vals = [(r.ts, r.incoherence_score) for r in rows if r.incoherence_score is not None]
    if not vals:
        return

    xs = [t for t, _ in vals]
    ys = [v for _, v in vals if v is not None]

    fig = plt.figure()
    ax = fig.add_subplot(111)
    ax.plot(xs, ys, marker="o", linewidth=1)
    ax.set_title("Incoherence score")
    ax.set_xlabel("Time (UTC)")
    ax.set_ylabel("incoherence_score")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_png)
    plt.close(fig)


def _plot_contrib(latest: dict[str, Any], out_png: Path) -> None:
    _ensure_matplotlib()
    import matplotlib.pyplot as plt

    breakdown: dict[str, Any] | None = None
    if isinstance(latest.get("incoherence_contributions"), dict):
        breakdown = latest.get("incoherence_contributions")
    else:
        inco = latest.get("incoherence") if isinstance(latest.get("incoherence"), dict) else None
        if isinstance(inco, dict) and isinstance(inco.get("breakdown"), dict):
            breakdown = inco.get("breakdown")

    if not isinstance(breakdown, dict) or not breakdown:
        return

    keys = [k for k in breakdown.keys() if isinstance(k, str)]
    if not keys:
        return

    vals: list[float] = []
    for k in keys:
        v = breakdown.get(k)
        if isinstance(v, int | float) and not isinstance(v, bool):
            vals.append(float(v))
        else:
            vals.append(0.0)

    fig = plt.figure()
    ax = fig.add_subplot(111)
    ax.bar(range(len(keys)), vals)
    ax.set_title("Incoherence contributions (latest)")
    ax.set_xlabel("phi")
    ax.set_ylabel("weighted contribution")
    ax.set_xticks(range(len(keys)))
    ax.set_xticklabels(keys, rotation=45, ha="right")
    fig.tight_layout()
    fig.savefig(out_png)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--history", required=True)
    ap.add_argument("--latest", default="")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = _read_history(Path(args.history))
    latest = _load_json(Path(args.latest)) if args.latest else {}

    _plot_score(rows, out_dir / "fig_score.png")
    _plot_incoherence(rows, out_dir / "fig_incoherence.png")
    _plot_contrib(latest, out_dir / "fig_contributions.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
