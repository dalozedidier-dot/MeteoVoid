from __future__ import annotations

from pathlib import Path

from tools.build_belgium_public_site import build_index


def test_stormscope_gauge_threshold_is_fixed_and_matches_bascule(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    site_dir = tmp_path / "site"
    report_dir.mkdir()

    build_index(report_dir, site_dir)

    accueil_html = (site_dir / "accueil.html").read_text(encoding="utf-8")
    index_html = (site_dir / "index.html").read_text(encoding="utf-8")
    sw_js = (site_dir / "sw.js").read_text(encoding="utf-8")

    for html in (accueil_html, index_html):
        assert "thresholdBottom=68" in html
        assert "charge=score*100" in html
        assert "BASCULE commence à 0.68" in html
        assert "100-(1-score)*42" not in html
        assert "100-lid*55" not in html
        assert "z-index:3" in html

    assert "gauge-fix" in sw_js
