"""Master registry of European radar sources, resolved safely for publication.

This module loads ``european_radar_master_sources.yaml`` and turns it into a
*sanitised* model that is safe to write into the public site:

* secret API keys (AEMET, Météo-France, KNMI, MeteoGate) are read from the
  environment only to compute a boolean ``configured`` flag — their values are
  never copied into the output;
* keyless providers (MeteoSwiss, DWD, DMI, RainViewer) expose an ``enabled``
  flag driven by their ``*_ENABLED`` switch;
* every source keeps its documented rate limit, formats, evidence level,
  attribution and operational priority so the Europe/country pages can show an
  honest, fully-detailed source registry.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

DEFAULT_CONFIG = Path("config/european_radar_master_sources.yaml")

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}


def _as_list(obj: Any) -> list[Any]:
    return obj if isinstance(obj, list) else []


def _as_dict(obj: Any) -> dict[str, Any]:
    return obj if isinstance(obj, dict) else {}


def _env_bool(name: str | None, default: bool) -> bool:
    if not name:
        return default
    raw = os.environ.get(str(name))
    if raw is None:
        return default
    val = raw.strip().lower()
    if val in _TRUTHY:
        return True
    if val in _FALSY:
        return False
    return default


def _env_int(name: str | None, default: int) -> int:
    if not name:
        return default
    raw = os.environ.get(str(name))
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except (TypeError, ValueError):
        return default


def load_master_sources(path: str | Path = DEFAULT_CONFIG) -> dict[str, Any]:
    """Load the raw master registry; tolerate a missing or malformed file."""
    p = Path(path)
    if not p.exists():
        return {"sources": [], "settings": {}}
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {"sources": [], "settings": {}}
    return data


def _resolve_settings(settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "cache_minutes": _env_int(
            settings.get("cache_minutes_env"), int(settings.get("cache_minutes_default", 10))
        ),
        "max_requests_per_run": _env_int(
            settings.get("max_requests_per_run_env"),
            int(settings.get("max_requests_per_run_default", 50)),
        ),
        "require_attribution": _env_bool(
            settings.get("require_attribution_env"),
            bool(settings.get("require_attribution_default", True)),
        ),
        "live_country_enabled": _env_bool(settings.get("enable_live_env"), False),
    }


def _resolve_source(raw: dict[str, Any]) -> dict[str, Any]:
    """Sanitise one source: never copy a key value, only a configured boolean."""
    auth = str(raw.get("auth") or "")
    auth_env = raw.get("auth_env")
    enabled_default = bool(raw.get("enabled_default", False))
    needs_key = auth in {"api_key_required", "free_account", "free_account_or_anonymous"}

    if needs_key:
        configured = bool(auth_env) and bool(os.environ.get(str(auth_env)))
        enabled = configured or enabled_default
        if configured:
            status = "national_key_configured"
        elif enabled_default:
            status = "anonymous_or_default_access"
        else:
            status = "interface_ready_awaiting_key"
    else:
        # Keyless provider toggled by a *_ENABLED flag.
        enabled = _env_bool(auth_env, enabled_default)
        configured = False
        status = "enabled_keyless" if enabled else "disabled_keyless"

    evidence = str(raw.get("evidence_level") or "")
    machine_ready = enabled and evidence == "machine_radar_if_file_read"

    out: dict[str, Any] = {
        "id": raw.get("id"),
        "rank": raw.get("rank"),
        "provider": raw.get("provider"),
        "scope": raw.get("scope"),
        "country": raw.get("country"),
        "role": raw.get("role"),
        "auth": auth,
        "auth_env": auth_env,  # the NAME of the variable, never its value
        "requires_key": needs_key,
        "configured": configured,
        "enabled": enabled,
        "machine_evidence_ready": machine_ready,
        "rate_limit": raw.get("rate_limit"),
        "formats": _as_list(raw.get("formats")),
        "evidence_level": evidence,
        "license": raw.get("license"),
        "attribution": raw.get("attribution"),
        "public_reference": raw.get("public_reference"),
        "status_text": raw.get("status_text"),
        "status": status,
    }
    companion = _as_dict(raw.get("companion"))
    if companion:
        out["companion"] = {
            "id": companion.get("id"),
            "provider": companion.get("provider"),
            "role": companion.get("role"),
            "auth": companion.get("auth"),
            "evidence_level": companion.get("evidence_level"),
            "status_text": companion.get("status_text"),
        }
    return out


def build_source_registry(path: str | Path = DEFAULT_CONFIG) -> dict[str, Any]:
    """Build the sanitised, publication-safe radar source registry."""
    raw = load_master_sources(path)
    sources = [_resolve_source(_as_dict(s)) for s in _as_list(raw.get("sources"))]
    sources.sort(key=lambda s: s.get("rank") or 99)
    settings = _resolve_settings(_as_dict(raw.get("settings")))

    configured = [s for s in sources if s["configured"]]
    enabled = [s for s in sources if s["enabled"]]
    machine = [s for s in sources if s["machine_evidence_ready"]]
    return {
        "contract": "meteovoid_radar_sources_public_v1",
        "settings": settings,
        "summary": {
            "source_count": len(sources),
            "enabled_count": len(enabled),
            "configured_key_count": len(configured),
            "machine_ready_count": len(machine),
            "keyless_count": sum(1 for s in sources if not s["requires_key"]),
        },
        "priority_order": [s["provider"] for s in sources],
        "sources": sources,
        "excluded_as_machine_evidence": _as_list(raw.get("excluded_as_machine_evidence")),
        "security_note": (
            "Les clés (AEMET, Météo-France, KNMI, MeteoGate) restent dans les secrets "
            "GitHub Actions ou un .env local. Le site public ne reçoit jamais une valeur "
            "de clé, seulement des booléens configured/enabled et des statuts."
        ),
    }


def sources_for_country(registry: dict[str, Any], country: str) -> list[dict[str, Any]]:
    """Return the master sources relevant to one country (national + pan-European)."""
    out = []
    for src in _as_list(registry.get("sources")):
        if src.get("country") == country or src.get("scope") == "europe":
            out.append(src)
    return out
