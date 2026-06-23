from __future__ import annotations

from meteovoid.europe_country import build_all_countries
from meteovoid.europe_sources import (
    build_europe_sources_api,
    country_source_profile,
    public_profile_for_country,
)


def test_europe_sources_promote_only_safe_core_sources() -> None:
    payload = build_europe_sources_api()
    assert payload["contract"] == "meteovoid_europe_open_data_sources_v2"
    assert payload["active_primary"] == "open_meteo"
    assert payload["sources"]["open_meteo"]["status"] == "active"
    assert payload["sources"]["brightsky_dwd"]["status"] == "active_enrichment"
    assert payload["sources"]["meteoswiss_open_data"]["status"] == "official_candidate"
    assert payload["sources"]["meteo_france_open_data"]["status"] == "official_candidate"
    assert payload["sources"]["meteostat"]["status"] == "active_validation_candidate"
    assert payload["experimental_sources"]


def test_country_source_profiles_have_expected_stack() -> None:
    germany = country_source_profile("germany")
    assert germany["forecast_primary"] == "open_meteo"
    assert germany["national_observations"] == "brightsky_dwd"
    assert "brightsky_dwd" in [src["id"] for src in germany["stack"]]

    switzerland = public_profile_for_country("switzerland")
    assert switzerland["official_candidate"] == "meteoswiss_open_data"
    assert switzerland["historical_validation"] == "meteostat"

    france = public_profile_for_country("france")
    assert france["official_candidate"] == "meteo_france_open_data"
    assert france["forecast_primary"] == "open_meteo"


def test_country_models_expose_open_data_stack() -> None:
    models = build_all_countries(run_day="2026-06-18")
    assert models["germany"]["source_stack"]["national_observations"] == "brightsky_dwd"
    assert models["switzerland"]["source_stack"]["official_candidate"] == ("meteoswiss_open_data")
    assert models["france"]["summary"]["forecast_primary"] == "open_meteo"
