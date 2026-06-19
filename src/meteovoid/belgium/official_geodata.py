"""Prepare Belgium administrative map layers for the public page.

The preferred operational source is Belgian official geodata (geo.be / INSPIRE / CadGIS).
Because service URLs can change and are sometimes heavy, the module also supports a
well-documented WGS84 fallback derived from Statbel-based open-data projects. The
status JSON always says which source was actually used.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

DEFAULT_PROVINCE_URL = (
    "https://public.opendatasoft.com/api/explore/v2.1/catalog/datasets/"
    "georef-belgium-province/exports/geojson?lang=fr&timezone=Europe%2FBrussels"
)
DEFAULT_MUNICIPALITY_URL = (
    "https://public.opendatasoft.com/api/explore/v2.1/catalog/datasets/"
    "georef-belgium-municipality/exports/geojson?lang=fr&timezone=Europe%2FBrussels"
)


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _fetch_json(url: str, *, timeout_s: float) -> dict[str, Any]:
    req = Request(url, headers={"User-Agent": "MeteoVoid/Belgium-geodata"})
    with urlopen(req, timeout=timeout_s) as response:  # noqa: S310 - public geodata endpoint
        raw = response.read().decode("utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("GeoJSON payload is not a JSON object")
    return payload


def _load_local(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not a JSON object")
    return payload


def _is_feature_collection(payload: dict[str, Any]) -> bool:
    return payload.get("type") == "FeatureCollection" and isinstance(payload.get("features"), list)


def _write_geojson(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )


def _source_record(
    layer: str, status: str, source: str, path: str, error: str = ""
) -> dict[str, Any]:
    return {"layer": layer, "status": status, "source": source, "path": path, "error": error}


def prepare_belgium_geodata(
    *,
    out_dir: Path,
    fallback_province_geojson: Path,
    province_url: str = DEFAULT_PROVINCE_URL,
    municipality_url: str = DEFAULT_MUNICIPALITY_URL,
    timeout_s: float = 20.0,
    offline: bool = False,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    province_path = out_dir / "belgium_boundaries_provinces.geojson"
    municipality_path = out_dir / "belgium_boundaries_municipalities.geojson"
    records: list[dict[str, Any]] = []

    if offline:
        province_payload = _load_local(fallback_province_geojson)
        _write_geojson(province_payload, province_path)
        records.append(
            _source_record(
                "provinces",
                "fallback_local",
                str(fallback_province_geojson),
                str(province_path),
            )
        )
    else:
        try:
            province_payload = _fetch_json(province_url, timeout_s=timeout_s)
            if not _is_feature_collection(province_payload):
                raise ValueError("province payload is not GeoJSON FeatureCollection")
            _write_geojson(province_payload, province_path)
            records.append(
                _source_record("provinces", "downloaded", province_url, str(province_path))
            )
        except Exception as exc:  # noqa: BLE001 - keep the site build alive
            province_payload = _load_local(fallback_province_geojson)
            _write_geojson(province_payload, province_path)
            records.append(
                _source_record(
                    "provinces",
                    "fallback_local_after_error",
                    str(fallback_province_geojson),
                    str(province_path),
                    str(exc),
                )
            )
        try:
            municipality_payload = _fetch_json(municipality_url, timeout_s=timeout_s)
            if not _is_feature_collection(municipality_payload):
                raise ValueError("municipality payload is not GeoJSON FeatureCollection")
            _write_geojson(municipality_payload, municipality_path)
            records.append(
                _source_record(
                    "municipalities", "downloaded", municipality_url, str(municipality_path)
                )
            )
        except Exception as exc:  # noqa: BLE001 - municipalities are optional/heavy
            records.append(
                _source_record(
                    "municipalities",
                    "unavailable",
                    municipality_url,
                    str(municipality_path),
                    str(exc),
                )
            )

    status = {
        "contract": "meteovoid_belgium_official_geodata_v1",
        "generated_at": _now_iso(),
        "preferred_official_source": "geo.be / INSPIRE Administrative Units / CadGIS",
        "fallback_sources": [
            "Opendatasoft georef Belgium layers based on NGI/AdminVector where reachable",
            "BelgiumMaps.StatBel / Statistics Belgium derived administrative boundaries",
            "mathiasleroy/Belgium-Geographic-Data WGS84 GeoJSON",
        ],
        "layers": records,
        "note": (
            "The public page should display the source/status. If only the local fallback is "
            "available, the map is suitable for display but must not be described as a fresh "
            "official CadGIS download."
        ),
    }
    (out_dir / "official_geodata_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return status
