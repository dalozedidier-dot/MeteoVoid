from __future__ import annotations

import argparse
from pathlib import Path

from meteovoid.belgium.opera_ord import write_opera_ord_outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Discover/download OPERA ORD MeteoGate radar products for MeteoVoid."
    )
    parser.add_argument("--config", default="config/opera_ord.yaml")
    parser.add_argument("--out-dir", default="_ci_out/opera_ord")
    parser.add_argument(
        "--datetime",
        dest="datetime_range",
        default="",
        help="ORD datetime range, e.g. 2026-06-17T00:00Z/2026-06-17T01:00Z",
    )
    parser.add_argument("--enable", action="store_true", help="Enable live MeteoGate queries")
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download returned OPERA data links into the local cache",
    )
    parser.add_argument("--timeout-s", type=float, default=30.0)
    parser.add_argument("--max-download-files", type=int, default=8)
    args = parser.parse_args(argv)

    status = write_opera_ord_outputs(
        Path(args.out_dir),
        config_path=args.config,
        enabled=bool(args.enable),
        timeout_s=float(args.timeout_s),
        datetime_range=str(args.datetime_range),
        download=bool(args.download),
        max_download_files=int(args.max_download_files),
    )
    print(Path(args.out_dir) / "opera_ord_status.json")
    print(Path(args.out_dir) / "opera_ord_inventory.json")
    print(Path(args.out_dir) / "opera_radar_metrics.json")
    print(f"status={status.get('status')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
