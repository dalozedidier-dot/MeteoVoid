from __future__ import annotations

import json
from pathlib import Path

from tools.build_belgium_public_site import build_index


def test_build_belgium_public_site(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    site_dir = tmp_path / "site"
    report_dir.mkdir()
    (report_dir / "belgium_alert_report.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-06-16T12:00:00+00:00",
                "national_score": 0.7,
                "national_severity": "high",
                "window_start": "2026-06-16",
                "window_end": "2026-06-20",
                "source_ok_count": 14,
                "source_error_count": 1,
                "stations": [
                    {
                        "name": "Uccle / Bruxelles",
                        "severity": "high",
                        "score": 0.73,
                        "sensitive_hour": "2026-06-19T17:00",
                        "signals": ["chaleur", "humidité", "orage"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (report_dir / "alert_state.json").write_text(
        json.dumps(
            {
                "level": "watch_reinforced",
                "public_wording": "veille technique non officielle",
            }
        ),
        encoding="utf-8",
    )
    (report_dir / "source_status.json").write_text(
        json.dumps({"source_ok_count": 14, "source_error_count": 1}), encoding="utf-8"
    )
    (report_dir / "convective_transition_report.json").write_text(
        json.dumps(
            {
                "summary": {
                    "max_convective_coherence_index": 0.66,
                    "max_void_collapse_signal": 0.55,
                    "max_transition_pressure_index": 0.7,
                    "max_latent_risk_gap": 0.45,
                },
                "stations": [
                    {
                        "name": "Uccle / Bruxelles",
                        "void_collapse_signal": 0.55,
                        "convective_coherence_index": 0.66,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (report_dir / "belgium_alert_dashboard.html").write_text("<h1>dashboard</h1>", encoding="utf-8")

    build_index(report_dir, site_dir)

    index = (site_dir / "index.html").read_text(encoding="utf-8")
    assert "MeteoVoid Belgique" in index
    assert "Prototype technique" in index
    assert "reports/latest/belgium_alert_dashboard.html" in index
    assert (site_dir / "reports" / "latest" / "belgium_alert_dashboard.html").exists()
