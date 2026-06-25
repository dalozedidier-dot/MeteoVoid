"""Static UI smoke checks for generated GitHub Pages artifacts.

The file is executable as a lightweight CI step without browsers, Playwright or
Node. It verifies that the generated site contains the critical containers and
public JSON contracts that previously caused blank maps or unlinked panels.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def assert_site(site_dir: Path) -> None:
    required_pages = [
        "accueil.html",
        "index.html",
        "carte.html",
        "reseau.html",
        "chaleur.html",
        "expert.html",
        "sources.html",
        "validation.html",
        "corridors.html",
        "convergence.html",
        "ledger.html",
        "ops.html",
        "ontology.html",
        "manifest.html",
    ]
    for page in required_pages:
        path = site_dir / page
        assert path.exists(), f"missing page: {page}"
        html = path.read_text(encoding="utf-8")
        assert "MeteoVoid" in html
    accueil_html = (site_dir / "accueil.html").read_text(encoding="utf-8")
    index_html = (site_dir / "index.html").read_text(encoding="utf-8")
    assert "MeteoVoid accueil stormscope portal" in accueil_html
    assert "Entrer · Belgique live" in accueil_html
    assert "api/watch.json" in accueil_html
    assert "MeteoVoid belgium operational stormscope dashboard" in index_html
    assert "Prochaines heures" in index_html
    assert 'href="#carte"' in index_html
    app_js = (site_dir / "assets" / "app.js").read_text(encoding="utf-8")
    assert "map-static-fallback" in app_js
    assert "country-contract-live" in app_js
    assert "Contrat pays live" in app_js
    assert (site_dir / "assets" / "deep-platform-panels.js").exists()
    contracts = [
        "api/countries/index.json",
        "api/temporal_layers.json",
        "api/signal_confidence.json",
        "api/station_quality_map.json",
        "api/platform.json",
        "api/convergence_matrix.json",
        "api/country_comparison.json",
        "api/forecast_ledger.json",
        "api/operational_readiness.json",
        "api/risk_ontology.json",
        "api/action_cards.json",
        "api/ui_contracts.json",
        "api/source_health.json",
        "api/schema_catalog.json",
        "api/public_manifest.json",
    ]
    for contract in contracts:
        payload = json.loads((site_dir / contract).read_text(encoding="utf-8"))
        assert payload.get("contract"), f"missing contract in {contract}"


if __name__ == "__main__":
    assert_site(Path(sys.argv[1] if len(sys.argv) > 1 else "_site"))


def test_ui_smoke_static_on_generated_site(tmp_path: Path) -> None:
    from tools.build_belgium_public_site import build_index

    report_dir = tmp_path / "report"
    site_dir = tmp_path / "site"
    report_dir.mkdir()
    build_index(report_dir, site_dir)
    assert_site(site_dir)
