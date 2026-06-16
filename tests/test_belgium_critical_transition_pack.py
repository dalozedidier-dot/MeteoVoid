from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_critical_transition_pack_outputs(tmp_path: Path) -> None:
    cmd = [
        sys.executable,
        "tools/generate_belgium_alert_report.py",
        "--offline-demo",
        "--out-dir",
        str(tmp_path),
        "--no-history",
    ]
    subprocess.run(cmd, check=True)
    required = [
        "early_warning_signals.json",
        "early_warning_by_station.csv",
        "early_warning_network.csv",
        "early_warning_dashboard.html",
        "information_graph_summary.json",
        "information_graph_edges.csv",
        "information_graph.html",
        "validation_metrics.json",
        "validation_report.md",
        "validation_dashboard.html",
        "self_watchdog.json",
        "self_watchdog.html",
        "observation_gap_status.json",
        "belgium_alert_cap.xml",
        "meteovoid_api_latest.json",
    ]
    for name in required:
        assert (tmp_path / name).exists(), name

    ews = json.loads((tmp_path / "early_warning_signals.json").read_text(encoding="utf-8"))
    assert "network_early_warning_score" in ews["summary"]

    graph = json.loads((tmp_path / "information_graph_summary.json").read_text(encoding="utf-8"))
    assert "information_corridor_score" in graph["summary"]

    watchdog = json.loads((tmp_path / "self_watchdog.json").read_text(encoding="utf-8"))
    assert watchdog["state"] in {"healthy_run", "watch_run", "degraded_run"}

    cap = (tmp_path / "belgium_alert_cap.xml").read_text(encoding="utf-8")
    assert "urn:oasis:names:tc:emergency:cap:1.2" in cap
    assert "Prototype technique non officiel" in cap


def test_public_site_includes_critical_transition_tabs(tmp_path: Path) -> None:
    out = tmp_path / "out"
    site = tmp_path / "site"
    subprocess.run(
        [sys.executable, "tools/generate_belgium_alert_report.py", "--offline-demo", "--out-dir", str(out), "--no-history"],
        check=True,
    )
    subprocess.run(
        [sys.executable, "tools/build_belgium_public_site.py", "--report-dir", str(out), "--site-dir", str(site)],
        check=True,
    )
    html = (site / "index.html").read_text(encoding="utf-8")
    assert "Signaux précoces" in html
    assert "Graphe informationnel" in html
    assert "Auto-surveillance" in html
    assert (site / "reports" / "latest" / "early_warning_dashboard.html").exists()
    assert (site / "reports" / "latest" / "information_graph.html").exists()
