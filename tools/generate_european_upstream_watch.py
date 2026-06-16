from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from meteovoid.belgium.upstream_watch import write_upstream_watch_outputs


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate MeteoVoid European upstream watch outputs."
    )
    parser.add_argument(
        "--report-json",
        default="_ci_out/belgium_alert/belgium_alert_report.json",
        help="Belgium alert report JSON used as local fallback and target context",
    )
    parser.add_argument("--out-dir", default="_ci_out/belgium_alert", help="Output directory")
    parser.add_argument(
        "--upstream-config",
        default="config/upstream_regions.yaml",
        help="YAML config defining upstream regions and corridors",
    )
    parser.add_argument(
        "--radar-sources-config",
        default="config/european_radar_sources.yaml",
        help="Optional radar/lightning interface config",
    )
    parser.add_argument(
        "--enable-openmeteo",
        action="store_true",
        help="Enable live Open-Meteo fallback for pressure-level airflow diagnostics",
    )
    parser.add_argument("--forecast-hours", type=int, default=12)
    parser.add_argument("--timezone", default="Europe/Brussels")
    parser.add_argument("--timeout-s", type=float, default=8.0)
    args = parser.parse_args(argv)

    report = _load_json(Path(args.report_json))
    watch = write_upstream_watch_outputs(
        report,
        Path(args.out_dir),
        upstream_config_path=args.upstream_config,
        radar_sources_config_path=args.radar_sources_config,
        openmeteo_enabled=bool(args.enable_openmeteo),
        forecast_hours=int(args.forecast_hours),
        timezone_name=args.timezone,
        timeout_s=float(args.timeout_s),
    )
    print(Path(args.out_dir) / "upstream_watch.json")
    print(Path(args.out_dir) / "european_upstream_map.html")
    print(f"max_corridor_score={watch.get('summary', {}).get('max_corridor_score')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
