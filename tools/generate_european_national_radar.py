from __future__ import annotations

import argparse
from pathlib import Path

from meteovoid.belgium.european_national_radar import (
    parse_country_files,
    write_european_national_radar_outputs,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate MeteoVoid national radar interface outputs for Spain, France, Switzerland and the Netherlands."
    )
    parser.add_argument("--out-dir", default="_ci_out/belgium_alert")
    parser.add_argument("--config", default="config/european_national_radars.yaml")
    parser.add_argument("--enable-live", action="store_true")
    parser.add_argument("--timeout-s", type=float, default=8.0)
    parser.add_argument(
        "--country-radar-file",
        action="append",
        default=[],
        help="Optional machine radar file as country:/path/file.npy|csv|json|tif. Example: france:/tmp/frame.npy",
    )
    args = parser.parse_args(argv)
    payload = write_european_national_radar_outputs(
        Path(args.out_dir),
        config_path=args.config,
        live=bool(args.enable_live),
        timeout_s=float(args.timeout_s),
        country_files=parse_country_files(list(args.country_radar_file or [])),
    )
    print(Path(args.out_dir) / "european_national_radar_status.json")
    print(f"status={payload.get('status')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
