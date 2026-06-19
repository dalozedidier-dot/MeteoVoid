from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from meteovoid.belgium.validation_history import update_validation_history  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Append Belgium forecast run to validation history.")
    parser.add_argument("--report", default="_ci_out/belgium_alert/belgium_alert_report.json")
    parser.add_argument("--history-dir", default=".meteovoid_history/belgium_validation")
    parser.add_argument("--verified-events", default="config/belgium_verified_storm_events.csv")
    parser.add_argument("--out-dir", default="_ci_out/belgium_alert")
    args = parser.parse_args(argv)

    report_path = Path(args.report)
    if not report_path.exists():
        raise SystemExit(f"report not found: {report_path}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise SystemExit("report JSON must be an object")
    update_validation_history(
        report=report,
        history_dir=Path(args.history_dir),
        verified_events_csv=Path(args.verified_events),
        out_dir=Path(args.out_dir),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
