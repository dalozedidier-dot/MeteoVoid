# MeteoVoid - Europe page same level patch

This patch keeps the Belgium page unchanged and reinforces the Europe page so it is no longer a light radar appendix.

## Main changes

- Rebuilds `europe.html` with the same visual language as the Belgium page: command bar, theme toggle, tabs, hero, KPI cards, operational chain, country cards, source registry, exports and expert JSON.
- Enriches `api/europe.json` with contract `meteovoid_europe_page_full_v3_same_design`.
- Adds a fuller radar registry for Spain, France, Switzerland and the Netherlands.
- Merges registry sources with runtime status sources so old artifacts still produce a complete Europe page.
- Adds national, display, nowcast, OPERA fallback and model fallback distinctions.
- Keeps the evidence rule strict: display layers and interface-ready providers are not promoted to machine radar proof unless a file is readable and metrics are computed.

## Countries and added sources

### Spain
- AEMET OpenData national radar composition.
- AEMET OpenData regional radar template.
- OPERA ORD fallback.
- RainViewer display.

### France
- Météo-France radar API path.
- AERIS Météo-France radar network reference.
- Météo-France public radar display.
- OPERA ORD fallback.
- RainViewer display.

### Switzerland
- MeteoSwiss precipitation radar STAC products.
- MeteoSwiss hail radar products reference.
- MeteoSwiss short-term nowcasting on request.
- OPERA ORD fallback.
- RainViewer display.

### Netherlands
- KNMI radar reflectivity composites.
- KNMI radar/gauge 5 minute products.
- KNMI radar nowcast up to 2 h.
- KNMI WMS reference.
- OPERA ORD fallback.
- RainViewer display.

## Modified files

```text
config/european_national_radars.yaml
src/meteovoid/belgium/european_national_radar.py
tools/build_belgium_public_site.py
tests/test_build_public_site.py
docs/EUROPE_PAGE_FULL.md
```

## Checks run

```bash
python -m ruff check tools/build_belgium_public_site.py src/meteovoid/belgium/european_national_radar.py tests/test_build_public_site.py tests/test_european_national_radar.py
python -m ruff format --check tools/build_belgium_public_site.py src/meteovoid/belgium/european_national_radar.py tests/test_build_public_site.py tests/test_european_national_radar.py
python -m black --check --diff --workers 1 tools/build_belgium_public_site.py src/meteovoid/belgium/european_national_radar.py tests/test_build_public_site.py tests/test_european_national_radar.py
pytest -q --no-cov tests/test_build_public_site.py tests/test_european_national_radar.py tests/test_radar_stack.py tests/test_upstream_watch.py tests/test_opera_ord.py
PYTHONPATH=src python tools/build_belgium_public_site.py --report-dir /mnt/data/meteo_eu_national_cifix_out --site-dir /mnt/data/meteo_europe_same_design_site
```

Result: targeted checks pass. Full pytest was not run because the sandbox is missing `hypothesis`.
