from __future__ import annotations

from pathlib import Path

from tools.build_belgium_public_site import build_index


def test_stormscope_map_has_immediate_fallback_and_safe_geojson(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    site_dir = tmp_path / "site"
    report_dir.mkdir()

    build_index(report_dir, site_dir)

    app_js = (site_dir / "assets" / "app.js").read_text(encoding="utf-8")
    sw_js = (site_dir / "sw.js").read_text(encoding="utf-8")

    assert "safeProvinceGeoJson" in app_js
    assert "seedMapFallback" in app_js
    assert "fetchJsonWithTimeout(url,7000)" in app_js
    assert "local-fallback" in app_js
    assert "tile.openstreetmap.org" in app_js
    assert "map-static-fallback" in app_js
    assert "repli visuel actif" in app_js
    assert "meteovoid-stormscope-static-v5" in sw_js
    assert "networkFirst(event.request)" in sw_js
    assert "trySiteApiMap" in app_js
    assert "alert-watch-live" in app_js
    adapter_js = (site_dir / "assets" / "site-api-adapter.js").read_text(encoding="utf-8")
    assert "loadMapLiveFromSiteApi" in adapter_js
