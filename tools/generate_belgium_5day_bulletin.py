from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from meteovoid.belgium.bulletin_5days import (  # noqa: E402
    DEFAULT_TIMEZONE,
    build_bulletin_5days,
    write_bulletin_outputs,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a classic Belgium 5-day bulletin.")
    parser.add_argument("--zones", default="config/belgium_forecast_zones.yaml")
    parser.add_argument("--out-dir", default="_ci_out/belgium_alert")
    parser.add_argument("--model", default="best_match")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    parser.add_argument("--days", type=int, default=5)
    parser.add_argument("--timeout-s", type=float, default=12.0)
    parser.add_argument("--offline-demo", action="store_true")
    args = parser.parse_args(argv)

    zones_path = Path(args.zones)
    if not zones_path.exists():
        zones_path = None  # use embedded Belgium defaults
    data = build_bulletin_5days(
        zones_config=zones_path,
        model=args.model,
        timezone=args.timezone,
        days=args.days,
        timeout_s=args.timeout_s,
        offline_demo=args.offline_demo,
    )
    write_bulletin_outputs(data, Path(args.out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
