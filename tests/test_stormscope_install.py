from __future__ import annotations

from pathlib import Path

from tools.build_belgium_public_site import build_index


def test_stormscope_is_public_home_and_classic_is_preserved(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    site_dir = tmp_path / "site"
    report_dir.mkdir()

    build_index(report_dir, site_dir)

    index_html = (site_dir / "index.html").read_text(encoding="utf-8")
    classic_html = (site_dir / "classic.html").read_text(encoding="utf-8")

    assert "MeteoVoid · Storm-scope" in index_html
    assert '<script src="assets/site-api-adapter.js"></script>' in index_html
    assert "window.MeteoVoidSiteApi" in (site_dir / "assets" / "site-api-adapter.js").read_text(
        encoding="utf-8"
    )
    assert "Europe classique" in index_html
    assert "Interface classique" in index_html
    assert "Vue simple" in classic_html
    assert (site_dir / "config" / "belgium_provinces_simplified.geojson").exists()
