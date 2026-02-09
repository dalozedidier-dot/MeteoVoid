from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core import scan_series_for_voids


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="meteovoid", description="Detects data voids and simple anomalies in CSV series."
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    scan = sub.add_parser("scan", help="Scan a CSV file and output a JSON report.")
    scan.add_argument("csv", type=Path, help="Path to a CSV file.")
    scan.add_argument("--time-col", default="timestamp", help="Name of the timestamp column.")
    scan.add_argument("--value-col", default="value", help="Name of the numeric value column.")
    scan.add_argument(
        "--max-gap-seconds", type=int, default=3600, help="Gap threshold to call a void."
    )
    scan.add_argument(
        "--out", type=Path, default=Path("meteo_void_report.json"), help="Output JSON file."
    )

    return p


def main(argv: list[str] | None = None) -> int:
    p = _build_parser()
    args = p.parse_args(argv)

    if args.cmd == "scan":
        report = scan_series_for_voids(
            csv_path=args.csv,
            time_col=args.time_col,
            value_col=args.value_col,
            max_gap_seconds=args.max_gap_seconds,
        )
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(str(args.out))
        return 0

    raise SystemExit(2)
