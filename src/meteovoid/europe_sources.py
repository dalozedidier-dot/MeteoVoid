"""Europe open-data source registry for MeteoVoid.

The registry keeps national sources visible without pretending that every
provider is already part of the live detection chain. It separates:

* active forecast sources, currently Open-Meteo for all Europe pages;
* active national enrichments, such as Bright Sky for Germany;
* official candidates, such as MeteoSwiss and Meteo-France open data;
* historical validation sources, such as Meteostat;
* experimental scrapers and forks, which are never promoted to core sources.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

DEFAULT_EUROPE_SOURCES = Path("config/europe_open_data_sources.yaml")

CORE_SOURCE_ORDER = [
    "open_meteo",
    "brightsky_dwd",
    "meteoswiss_open_data",
    "meteostat",
    "meteo_france_open_data",
]

EXPERIMENTAL_STATUS = {"experimental", "fork", "scraper_candidate", "not_core"}

COUNTRY_LABELS = {
    "belgium": "Belgique",
    "europe": "Europe",
    "france": "France",
    "germany": "Allemagne",
    "switzerland": "Suisse",
    "netherlands": "Pays-Bas",
    "spain": "Espagne",
    "italy": "Italie",
    "austria": "Autriche",
    "denmark": "Danemark",
    "uk": "Royaume-Uni",
}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def load_europe_sources_config(path: str | Path = DEFAULT_EUROPE_SOURCES) -> dict[str, Any]:
    """Load the Europe source registry, tolerating a missing or partial file."""
    p = Path(path)
    if not p.exists():
        return {"version": 1, "sources": {}, "country_profiles": {}, "experimental_sources": []}
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {"version": 1, "sources": {}, "country_profiles": {}, "experimental_sources": []}
    data.setdefault("sources", {})
    data.setdefault("country_profiles", {})
    data.setdefault("experimental_sources", [])
    return data


def _normalise_source(source_id: str, raw: dict[str, Any]) -> dict[str, Any]:
    status = str(raw.get("status") or "candidate")
    priority = int(raw.get("priority") or 50)
    core_usable = bool(raw.get("core_usable", status in {"active", "active_enrichment"}))
    return {
        "id": source_id,
        "label": raw.get("label") or source_id,
        "status": status,
        "scope": raw.get("scope"),
        "auth": raw.get("auth") or "unknown",
        "roles": [str(role) for role in _as_list(raw.get("role") or raw.get("roles"))],
        "priority": priority,
        "core_usable": core_usable,
        "implementation": raw.get("implementation") or "registry_only",
        "update_interval_minutes": raw.get("update_interval_minutes"),
        "api_base": raw.get("api_base"),
        "documentation": raw.get("documentation"),
        "license_note": raw.get("license_note"),
        "notes": raw.get("notes") or raw.get("note"),
    }


def source_registry(path: str | Path = DEFAULT_EUROPE_SOURCES) -> dict[str, dict[str, Any]]:
    """Return normalised source definitions by source id."""
    cfg = load_europe_sources_config(path)
    raw_sources = _as_dict(cfg.get("sources"))
    return {
        str(source_id): _normalise_source(str(source_id), _as_dict(raw))
        for source_id, raw in raw_sources.items()
    }


def _profile_source_ids(profile: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for key in [
        "forecast_primary",
        "national_observations",
        "national_forecast",
        "official_candidate",
        "historical_validation",
        "radar_candidate",
    ]:
        value = profile.get(key)
        if isinstance(value, str) and value not in ids:
            ids.append(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item not in ids:
                    ids.append(item)
    return ids


def country_source_profile(
    country_key: str,
    path: str | Path = DEFAULT_EUROPE_SOURCES,
) -> dict[str, Any]:
    """Return the ordered source stack for one MeteoVoid country page."""
    cfg = load_europe_sources_config(path)
    registry = source_registry(path)
    profiles = _as_dict(cfg.get("country_profiles"))
    profile = _as_dict(profiles.get(country_key))
    if not profile:
        profile = {
            "label": COUNTRY_LABELS.get(country_key, country_key.title()),
            "forecast_primary": "open_meteo",
            "historical_validation": "meteostat",
        }
    source_ids = _profile_source_ids(profile)
    if "open_meteo" not in source_ids:
        source_ids.insert(0, "open_meteo")
    stack = [registry[src_id] for src_id in source_ids if src_id in registry]
    stack.sort(key=lambda item: (int(item.get("priority") or 50), item["id"]))
    active = [src for src in stack if src.get("status") in {"active", "active_enrichment"}]
    candidates = [
        src
        for src in stack
        if src.get("status") not in {"active", "active_enrichment"} | EXPERIMENTAL_STATUS
    ]
    experimental = [src for src in stack if src.get("status") in EXPERIMENTAL_STATUS]
    return {
        "country": country_key,
        "label": profile.get("label") or COUNTRY_LABELS.get(country_key, country_key.title()),
        "strategy": profile.get("strategy")
        or "Open-Meteo first, national sources only when schema and attribution are explicit.",
        "forecast_primary": profile.get("forecast_primary") or "open_meteo",
        "national_observations": profile.get("national_observations"),
        "national_forecast": profile.get("national_forecast"),
        "official_candidate": profile.get("official_candidate"),
        "historical_validation": profile.get("historical_validation"),
        "radar_candidate": profile.get("radar_candidate"),
        "stack": stack,
        "active": active,
        "candidates": candidates,
        "experimental": experimental,
        "active_count": len(active),
        "candidate_count": len(candidates),
        "experimental_count": len(experimental),
        "open_meteo_primary": bool(profile.get("forecast_primary") in {None, "open_meteo"}),
        "note": profile.get("note"),
    }


def all_country_profiles(path: str | Path = DEFAULT_EUROPE_SOURCES) -> dict[str, dict[str, Any]]:
    """Return source profiles for all configured country pages."""
    cfg = load_europe_sources_config(path)
    profile_keys = set(_as_dict(cfg.get("country_profiles")).keys())
    profile_keys.update({"europe", "belgium", "france", "germany", "switzerland"})
    return {key: country_source_profile(key, path) for key in sorted(profile_keys)}


def build_europe_sources_api(path: str | Path = DEFAULT_EUROPE_SOURCES) -> dict[str, Any]:
    """Build the static ``api/europe_sources.json`` payload."""
    cfg = load_europe_sources_config(path)
    registry = source_registry(path)
    profiles = all_country_profiles(path)
    experimental_raw = _as_list(cfg.get("experimental_sources"))
    experimental = [
        {
            "id": str(item.get("id") or "unknown"),
            "label": item.get("label") or item.get("id") or "source expérimentale",
            "status": item.get("status") or "experimental",
            "reason": item.get("reason")
            or "source non utilisée dans le coeur tant que son contrat n'est pas stable",
            "category": item.get("category") or "experimental",
        }
        for item in experimental_raw
        if isinstance(item, dict)
    ]
    core_sources = [registry[key] for key in CORE_SOURCE_ORDER if key in registry]
    return {
        "contract": "meteovoid_europe_open_data_sources_v2",
        "generated_at": _now_iso(),
        "policy": _as_dict(cfg.get("policy")),
        "active_primary": "open_meteo",
        "core_sources": core_sources,
        "sources": registry,
        "countries": profiles,
        "experimental_sources": experimental,
        "summary": {
            "source_count": len(registry),
            "country_profile_count": len(profiles),
            "core_source_count": len(core_sources),
            "experimental_source_count": len(experimental),
            "active_primary": "open_meteo",
            "rule": (
                "Open-Meteo is the Europe forecast backbone. National providers enrich "
                "country pages only when source, schema, cache and attribution are explicit."
            ),
        },
    }


def public_profile_for_country(country_key: str) -> dict[str, Any]:
    """Small profile used by public APIs without exposing internals."""
    profile = country_source_profile(country_key)
    return {
        "country": profile["country"],
        "label": profile["label"],
        "strategy": profile["strategy"],
        "forecast_primary": profile["forecast_primary"],
        "national_observations": profile.get("national_observations"),
        "national_forecast": profile.get("national_forecast"),
        "official_candidate": profile.get("official_candidate"),
        "historical_validation": profile.get("historical_validation"),
        "radar_candidate": profile.get("radar_candidate"),
        "active_sources": [src["id"] for src in profile["active"]],
        "candidate_sources": [src["id"] for src in profile["candidates"]],
        "experimental_count": profile["experimental_count"],
    }
