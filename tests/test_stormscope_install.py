from __future__ import annotations

from pathlib import Path

from tools.build_belgium_public_site import build_index


def test_stormscope_is_global_public_interface(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    site_dir = tmp_path / "site"
    report_dir.mkdir()

    build_index(report_dir, site_dir)

    public_pages = [
        "index.html",
        "classic.html",
        "europe.html",
        "methodology.html",
        "bulletin.html",
        "carte.html",
        "expert.html",
        "chaleur.html",
        "reseau.html",
        "italy.html",
        "austria.html",
        "uk.html",
    ]
    for page in public_pages:
        html = (site_dir / page).read_text(encoding="utf-8")
        assert "MeteoVoid · Storm-scope" in html
        assert "Storm-scope · veille de bascule" in html
        assert '<script src="assets/app.js"></script>' in html
        assert '<script src="assets/site-api-adapter.js"></script>' in html
        assert "Interface classique" not in html

    europe_html = (site_dir / "europe.html").read_text(encoding="utf-8")
    methodology_html = (site_dir / "methodology.html").read_text(encoding="utf-8")
    bulletin_html = (site_dir / "bulletin.html").read_text(encoding="utf-8")

    assert "#europe" in europe_html
    assert "#methode" in methodology_html
    assert "#bulletin" in bulletin_html
    assert "window.MeteoVoidSiteApi" in (site_dir / "assets" / "site-api-adapter.js").read_text(
        encoding="utf-8"
    )
    assert (site_dir / "config" / "belgium_provinces_simplified.geojson").exists()
    assert (site_dir / "assets" / "app.css").exists()
    assert (site_dir / "assets" / "app.js").exists()
    assert "Royaume-Uni" in (site_dir / "uk.html").read_text(encoding="utf-8")
    assert "Italie" in (site_dir / "italy.html").read_text(encoding="utf-8")
