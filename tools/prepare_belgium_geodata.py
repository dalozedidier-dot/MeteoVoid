from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from meteovoid.belgium.official_geodata import (  # noqa: E402
    DEFAULT_MUNICIPALITY_URL,
    DEFAULT_PROVINCE_URL,
    prepare_belgium_geodata,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare Belgium administrative GeoJSON layers.")
    parser.add_argument("--out-dir", default="_ci_out/belgium_alert")
    parser.add_argument(
        "--fallback-province-geojson", default="config/belgium_provinces_simplified.geojson"
    )
    parser.add_argument("--province-url", default=DEFAULT_PROVINCE_URL)
    parser.add_argument("--municipality-url", default=DEFAULT_MUNICIPALITY_URL)
    parser.add_argument("--timeout-s", type=float, default=20.0)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args(argv)

    prepare_belgium_geodata(
        out_dir=Path(args.out_dir),
        fallback_province_geojson=Path(args.fallback_province_geojson),
        province_url=args.province_url,
        municipality_url=args.municipality_url,
        timeout_s=args.timeout_s,
        offline=args.offline,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
