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
    standalone_pages = {"accueil.html", "index.html"}
    for page in public_pages:
        html = (site_dir / page).read_text(encoding="utf-8")
        assert "MeteoVoid" in html
        assert "Storm-scope" in html
        if page not in standalone_pages:
            assert '<script src="assets/app.js"></script>' in html
            assert '<script src="assets/site-api-adapter.js"></script>' in html
            assert '<script src="assets/alert-watch-panels.js"></script>' in html
        assert "Interface classique" not in html

    europe_html = (site_dir / "europe.html").read_text(encoding="utf-8")
    methodology_html = (site_dir / "methodology.html").read_text(encoding="utf-8")
    accueil_html = (site_dir / "accueil.html").read_text(encoding="utf-8")
    index_html = (site_dir / "index.html").read_text(encoding="utf-8")
    assert "MeteoVoid accueil stormscope portal" in accueil_html
    assert "Entrer · Belgique en direct" in accueil_html
    assert "Tour d'Europe" in accueil_html
    assert 'href="index.html"' in accueil_html
    assert 'href="sources.html"' in accueil_html
    assert "MeteoVoid belgium standalone stormscope dashboard" in index_html
    assert "Prochaines heures" in index_html
    assert 'href="carte.html"' in index_html
    assert 'href="europe.html"' in index_html

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
    assert (site_dir / "assets" / "alert-watch-panels.js").exists()
    assert (site_dir / "api" / "watch.json").exists()
    assert "meteovoid_belgium_alert_watch_public_v1" in (site_dir / "api" / "watch.json").read_text(
        encoding="utf-8"
    )
    assert "Royaume-Uni" in (site_dir / "uk.html").read_text(encoding="utf-8")
    assert "Italie" in (site_dir / "italy.html").read_text(encoding="utf-8")
