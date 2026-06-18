"""Tests for the sanitised master radar source registry."""

from __future__ import annotations

import json

from meteovoid.radar_sources import build_source_registry, sources_for_country


def test_registry_lists_all_eight_sources_in_priority_order() -> None:
    reg = build_source_registry()
    assert reg["summary"]["source_count"] == 8
    ranks = [s["rank"] for s in reg["sources"]]
    assert ranks == sorted(ranks), "sources must be priority-ordered"
    # MeteoGate OPERA ORD is the European pivot, rank 1
    assert reg["sources"][0]["id"] == "meteogate_opera_ord"
    providers = {s["id"] for s in reg["sources"]}
    assert {
        "aemet_opendata",
        "meteofrance_radar_api",
        "knmi_data_platform",
        "dwd_open_data",
        "dmi_radar",
    } <= providers


def test_keys_are_never_leaked_into_the_published_registry(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("AEMET_API_KEY", "super-secret-value-123")
    monkeypatch.setenv("METEOFRANCE_API_KEY", "another-secret-456")
    reg = build_source_registry()
    blob = json.dumps(reg)
    assert "super-secret-value-123" not in blob
    assert "another-secret-456" not in blob
    aemet = next(s for s in reg["sources"] if s["id"] == "aemet_opendata")
    assert aemet["configured"] is True  # key presence is reflected
    assert aemet["auth_env"] == "AEMET_API_KEY"  # only the variable NAME, not its value
    assert aemet["status"] == "national_key_configured"


def test_keyless_flags_toggle_enabled_state(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("DMI_RADAR_ENABLED", raising=False)
    reg = build_source_registry()
    dmi = next(s for s in reg["sources"] if s["id"] == "dmi_radar")
    assert dmi["enabled"] is False and dmi["requires_key"] is False

    monkeypatch.setenv("DMI_RADAR_ENABLED", "true")
    reg2 = build_source_registry()
    dmi2 = next(s for s in reg2["sources"] if s["id"] == "dmi_radar")
    assert dmi2["enabled"] is True


def test_rainviewer_is_display_only_not_machine_evidence() -> None:
    reg = build_source_registry()
    rv = next(s for s in reg["sources"] if s["id"] == "rainviewer")
    assert rv["evidence_level"] == "display_only"
    assert rv["machine_evidence_ready"] is False


def test_sources_for_country_merges_national_and_pan_european() -> None:
    reg = build_source_registry()
    fr = {s["id"] for s in sources_for_country(reg, "france")}
    assert "meteofrance_radar_api" in fr  # national
    assert "meteogate_opera_ord" in fr  # pan-European pivot
    assert "rainviewer" in fr  # pan-European display
    assert "aemet_opendata" not in fr  # other country's national source excluded


def test_settings_have_safe_defaults() -> None:
    reg = build_source_registry()
    settings = reg["settings"]
    assert settings["cache_minutes"] >= 1
    assert settings["max_requests_per_run"] >= 1
    assert isinstance(settings["require_attribution"], bool)
