from meteovoid.model_compare import build_model_compare_api


def test_model_compare_contract_uses_map_live_score():
    api = build_model_compare_api(
        {"hours": [{"score": 0.62}]},
        generated_at="2026-01-01T00:00:00+00:00",
    )

    assert api["contract"] == "meteovoid_open_meteo_model_compare_v1"
    assert api["generated_at"] == "2026-01-01T00:00:00+00:00"
    assert len(api["models"]) >= 6
    assert api["agreement"]["label"] in {
        "accord fort",
        "accord partiel",
        "désaccord marqué",
    }
    assert api["most_aggressive"]
    assert api["most_conservative"]
    assert any(item["family"] == "ecmwf" for item in api["models"])
    assert any(item["family"] == "arome" for item in api["models"])
    assert any(item["family"] == "icon" for item in api["models"])
    assert api["grib_direct_roadmap"]


def test_model_compare_contract_tolerates_missing_map_live():
    api = build_model_compare_api(None)

    assert api["center"]["label"] == "Belgique"
    assert all("fallback_score" in item for item in api["models"])
    assert all(
        item["score_source"] == "static_ci_fallback_until_browser_fetch" for item in api["models"]
    )
    assert api["agreement"]["spread"] is not None


def test_model_compare_contract_can_use_station_scores():
    api = build_model_compare_api(
        {"stations": [{"score": "0.4"}, {"score": 0.6}, {"score": None}]},
        region="belgium",
    )

    scores = [item["fallback_score"] for item in api["models"]]
    assert min(scores) >= 0
    assert max(scores) <= 1
    assert api["region"] == "belgium"
