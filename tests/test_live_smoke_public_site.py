from __future__ import annotations

import json
from pathlib import Path

from tools.build_belgium_public_site import build_index


def test_public_site_ingests_live_smoke_and_opera_artifacts(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    live_dir = tmp_path / "live_smoke"
    opera_dir = tmp_path / "opera_ord"
    site_dir = tmp_path / "site"
    report_dir.mkdir()
    live_dir.mkdir()
    opera_dir.mkdir()

    (live_dir / "latest_enriched.json").write_text(
        json.dumps(
            {
                "station_id": "DEMO_BE_0001",
                "variable": "wind_gust_ms",
                "score": 0.21618,
                "state": "transition",
                "signals": {"flatline": 0.0, "gap": 0.0, "volatility": 0.8},
                "contributions": {"volatility": 0.2},
                "stats": {"n_points": 250, "window_s": 300},
                "meteo": {"severity": "medium", "interpretation": "surveillance"},
                "ts_ingest_iso": "2026-06-24T00:00:12Z",
            }
        ),
        encoding="utf-8",
    )
    (live_dir / "bulletin.md").write_text("# Live Smoke\n", encoding="utf-8")
    (opera_dir / "opera_ord_status.json").write_text(
        json.dumps(
            {
                "contract": "opera_ord_connector_v2",
                "status": "ok",
                "enabled": True,
                "machine_radar_confirmation": False,
                "files_manifest": [{"status": "downloaded"}],
            }
        ),
        encoding="utf-8",
    )
    (opera_dir / "opera_radar_metrics.json").write_text(
        json.dumps(
            {
                "contract": "opera_radar_metrics_v1",
                "status": "no_machine_radar_metrics",
                "analysed_file_count": 1,
                "machine_radar_available": False,
            }
        ),
        encoding="utf-8",
    )

    build_index(report_dir, site_dir, live_smoke_dir=live_dir, opera_ord_dir=opera_dir)

    live_api = json.loads((site_dir / "api" / "live_smoke.json").read_text(encoding="utf-8"))
    watch_api = json.loads((site_dir / "api" / "watch.json").read_text(encoding="utf-8"))
    radar_api = json.loads((site_dir / "api" / "radar.json").read_text(encoding="utf-8"))

    assert live_api["available"] is True
    assert live_api["station_id"] == "DEMO_BE_0001"
    assert live_api["signals"]["volatility"] == 0.8
    assert watch_api["live_smoke"]["available"] is True
    assert radar_api["opera_ord_status"]["status"] == "ok"
    assert (site_dir / "reports" / "latest" / "live_smoke_latest_enriched.json").exists()
