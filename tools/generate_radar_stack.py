from __future__ import annotations

import argparse
from pathlib import Path

from meteovoid.belgium.radar_stack import write_radar_stack_outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate MeteoVoid radar stack outputs.")
    parser.add_argument("--out-dir", default="_ci_out/belgium_alert")
    parser.add_argument("--opera-config", default="config/opera_ord.yaml")
    parser.add_argument("--radar-frame", action="append", default=[])
    parser.add_argument("--enable-rainviewer-live", action="store_true")
    parser.add_argument("--enable-opera-ord", action="store_true")
    parser.add_argument("--enable-pysteps-nowcast", action="store_true")
    parser.add_argument("--timeout-s", type=float, default=8.0)
    args = parser.parse_args(argv)

    stack = write_radar_stack_outputs(
        Path(args.out_dir),
        opera_config_path=args.opera_config,
        radar_frame_paths=list(args.radar_frame),
        enable_rainviewer_live=bool(args.enable_rainviewer_live),
        enable_opera_ord=bool(args.enable_opera_ord),
        enable_pysteps=bool(args.enable_pysteps_nowcast),
        timeout_s=float(args.timeout_s),
    )
    print(Path(args.out_dir) / "radar_stack.json")
    print(Path(args.out_dir) / "rainviewer_radar_map.html")
    print(f"honest_state={stack.get('honest_state')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
