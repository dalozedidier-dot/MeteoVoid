from __future__ import annotations

import csv
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml  # type: ignore[import-untyped]

from meteovoid.belgium.opera_ord import analyse_radar_file

DEFAULT_CONFIG = "config/european_national_radars.yaml"
DEFAULT_USER_AGENT = "MeteoVoid-EuropeanNationalRadar/1.0"
COUNTRY_ORDER = ["france", "netherlands", "spain", "switzerland"]


def _utc_now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _load_yaml(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    payload = yaml.safe_load(p.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _bbox(country_cfg: dict[str, Any]) -> tuple[float, float, float, float] | None:
    raw = country_cfg.get("bbox")
    if not isinstance(raw, dict):
        return None
    try:
        return (
            float(raw["west"]),
            float(raw["south"]),
            float(raw["east"]),
            float(raw["north"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None


def _clamp01(value: Any) -> float:
    number = _safe_float(value)
    if number is None:
        return 0.0
    return max(0.0, min(1.0, number))


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _format_endpoint(template: str, source: dict[str, Any], api_key: str) -> str:
    out = template.replace("{api_key}", api_key)
    for key, value in source.items():
        if isinstance(value, str):
            out = out.replace("{" + key + "}", value)
    return out


def _http_probe(
    url: str,
    *,
    timeout_s: float,
    user_agent: str,
    max_probe_bytes: int,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    request_headers = {"User-Agent": user_agent, **(headers or {})}
    request = Request(url, headers=request_headers)
    try:
        with urlopen(request, timeout=timeout_s) as response:  # noqa: S310
            sample = response.read(max(0, int(max_probe_bytes)))
            return {
                "ok": True,
                "status": "reachable",
                "http_status": getattr(response, "status", None),
                "content_type": response.headers.get("Content-Type"),
                "sample_bytes": len(sample),
            }
    except HTTPError as exc:
        return {
            "ok": False,
            "status": "http_error",
            "http_status": exc.code,
            "detail": str(exc)[:240],
        }
    except (OSError, URLError, TimeoutError, ValueError) as exc:
        return {"ok": False, "status": "error", "detail": str(exc)[:240]}


def parse_country_files(values: list[str] | None) -> dict[str, list[Path]]:
    """Parse CLI entries shaped country:/path/to/file into a country->files mapping."""

    out: dict[str, list[Path]] = {}
    for raw in values or []:
        if ":" not in raw:
            continue
        country, path = raw.split(":", 1)
        key = country.strip().lower().replace(" ", "_")
        if not key or not path.strip():
            continue
        out.setdefault(key, []).append(Path(path.strip()))
    return out


def _local_files_from_config(country_cfg: dict[str, Any]) -> list[Path]:
    files: list[Path] = []
    for key in ["local_file", "local_files"]:
        value = country_cfg.get(key)
        if isinstance(value, str) and value.strip():
            files.append(Path(value.strip()))
        elif isinstance(value, list):
            files.extend(Path(str(item)) for item in value if str(item).strip())
    return files


def analyse_country_files(
    country_key: str,
    country_cfg: dict[str, Any],
    files: list[Path],
) -> dict[str, Any]:
    bbox = _bbox(country_cfg)
    frame_metrics: list[dict[str, Any]] = []
    readable_values: list[float] = []
    for path in files:
        record: dict[str, Any] = {
            "country": country_key,
            "path": str(path),
            "exists": path.exists(),
        }
        if not path.exists():
            record["status"] = "missing"
            frame_metrics.append(record)
            continue
        try:
            analysis = analyse_radar_file(path, bbox=bbox)
            record.update(analysis)
            record["sha256"] = _hash_file(path)
            record["size_bytes"] = path.stat().st_size
            candidate = analysis.get("p95") or analysis.get("max") or analysis.get("max_value")
            value = _safe_float(candidate)
            if value is not None:
                readable_values.append(value)
        except (OSError, ValueError, RuntimeError) as exc:
            record.update({"status": "analysis_error", "detail": str(exc)[:240]})
        frame_metrics.append(record)
    score = None
    if readable_values:
        # Generic radar intensity proxy; deliberately not an official severity scale.
        score = round(_clamp01(max(readable_values) / 60.0), 3)
    return {
        "country": country_key,
        "status": "metrics_available" if score is not None else "no_readable_country_files",
        "machine_radar_available": score is not None,
        "radar_activity_score": score,
        "file_count": len(files),
        "readable_file_count": len(readable_values),
        "files": frame_metrics,
    }


def _source_status(
    source: dict[str, Any],
    *,
    live: bool,
    timeout_s: float,
    user_agent: str,
    max_probe_bytes: int,
) -> dict[str, Any]:
    evidence = str(source.get("evidence_level") or "interface_only")
    api_key_env = str(source.get("api_key_env") or "")
    api_key = os.getenv(api_key_env, "") if api_key_env else ""
    endpoint_template = str(source.get("endpoint_template") or "")
    base: dict[str, Any] = {
        "id": source.get("id"),
        "provider": source.get("provider"),
        "role": source.get("role"),
        "evidence_level": evidence,
        "expected_format": source.get("expected_format"),
        "update_interval_minutes": source.get("update_interval_minutes"),
        "api_key_env": api_key_env or None,
        "api_key_configured": bool(api_key) if api_key_env else None,
        "public_reference": source.get("public_reference"),
        "license_note": source.get("license_note"),
        "source_family": source.get("source_family"),
        "note": source.get("note"),
        "status": "interface_only_unconfigured",
        "machine_evidence": False,
    }
    if evidence == "opera_ord_fallback":
        base.update(
            {
                "status": "covered_by_opera_ord_connector",
                "machine_evidence": False,
                "note": "Use the OPERA ORD connector for pan-European machine radar files.",
            }
        )
        return base
    if not endpoint_template:
        base.update(
            {
                "status": "endpoint_not_configured",
                "note": "Provider exists, but no public machine endpoint is configured in this registry.",
            }
        )
        return base
    if api_key_env and not api_key:
        base.update(
            {
                "status": "requires_api_key",
                "note": f"Set {api_key_env} to probe this provider endpoint.",
            }
        )
        return base
    endpoint = _format_endpoint(endpoint_template, source, api_key)
    safe_endpoint = endpoint.replace(api_key, "***") if api_key else endpoint
    base["endpoint"] = safe_endpoint
    if not live:
        base.update(
            {
                "status": "configured_not_probed",
                "note": "Live probing disabled; pass --enable-national-radar-live to test endpoint reachability.",
            }
        )
        return base
    probe_headers: dict[str, str] = {}
    if api_key and "api_key=" not in endpoint_template:
        probe_headers["Authorization"] = f"Bearer {api_key}"
    base.update(
        _http_probe(
            endpoint,
            timeout_s=timeout_s,
            user_agent=user_agent,
            max_probe_bytes=max_probe_bytes,
            headers=probe_headers,
        )
    )
    return base


def build_european_national_radar(
    config_path: str | Path | None = DEFAULT_CONFIG,
    *,
    live: bool = False,
    timeout_s: float | None = None,
    country_files: dict[str, list[Path]] | None = None,
) -> dict[str, Any]:
    config = _load_yaml(config_path)
    runtime_raw = config.get("runtime")
    runtime: dict[str, Any] = runtime_raw if isinstance(runtime_raw, dict) else {}
    user_agent = str(runtime.get("user_agent") or DEFAULT_USER_AGENT)
    max_probe_bytes = int(runtime.get("max_probe_bytes") or 2048)
    timeout = float(timeout_s or runtime.get("default_timeout_seconds") or 8.0)
    countries_raw = config.get("countries")
    countries_cfg: dict[str, Any] = countries_raw if isinstance(countries_raw, dict) else {}
    pan_layers_raw = config.get("pan_european_layers")
    pan_layers = pan_layers_raw if isinstance(pan_layers_raw, list) else []
    supplied_files = country_files or {}
    countries: list[dict[str, Any]] = []
    metrics: list[dict[str, Any]] = []
    any_machine = False

    country_keys = [
        *COUNTRY_ORDER,
        *sorted(set(countries_cfg.keys()) - set(COUNTRY_ORDER)),
    ]
    for country_key in country_keys:
        raw_cfg = countries_cfg.get(country_key)
        if not isinstance(raw_cfg, dict):
            continue
        sources_value = raw_cfg.get("sources")
        sources_raw: list[Any] = sources_value if isinstance(sources_value, list) else []
        files = [*_local_files_from_config(raw_cfg), *supplied_files.get(country_key, [])]
        file_metrics = analyse_country_files(country_key, raw_cfg, files)
        any_machine = any_machine or bool(file_metrics.get("machine_radar_available"))
        metrics.append(file_metrics)
        sources = [
            _source_status(
                source,
                live=live,
                timeout_s=timeout,
                user_agent=user_agent,
                max_probe_bytes=max_probe_bytes,
            )
            for source in sources_raw
            if isinstance(source, dict)
        ]
        countries.append(
            {
                "country": country_key,
                "label": raw_cfg.get("label") or country_key.title(),
                "iso2": raw_cfg.get("iso2"),
                "bbox": raw_cfg.get("bbox"),
                "upstream_role": raw_cfg.get("upstream_role"),
                "belgium_relevance": raw_cfg.get("belgium_relevance"),
                "priority_for_belgium": raw_cfg.get("priority_for_belgium"),
                "corridor_family": raw_cfg.get("corridor_family"),
                "watch_zones": (
                    raw_cfg.get("watch_zones")
                    if isinstance(raw_cfg.get("watch_zones"), list)
                    else []
                ),
                "required_env": (
                    raw_cfg.get("required_env")
                    if isinstance(raw_cfg.get("required_env"), list)
                    else []
                ),
                "source_count": len(sources),
                "sources": sources,
                "local_file_metrics": file_metrics,
                "machine_radar_available": bool(file_metrics.get("machine_radar_available")),
                "radar_activity_score": file_metrics.get("radar_activity_score"),
            }
        )

    status = "machine_metrics_available" if any_machine else "interfaces_ready_no_machine_data"
    return {
        "contract": "meteovoid_european_national_radar_v1",
        "generated_at": _utc_now(),
        "enabled": True,
        "live_probe_enabled": bool(live),
        "status": status,
        "countries_requested": ["spain", "france", "switzerland", "netherlands"],
        "pan_european_layers": [layer for layer in pan_layers if isinstance(layer, dict)],
        "countries": countries,
        "metrics": {
            "contract": "meteovoid_european_national_radar_metrics_v1",
            "generated_at": _utc_now(),
            "status": "metrics_available" if any_machine else "no_country_machine_metrics",
            "machine_radar_available": any_machine,
            "countries": metrics,
        },
        "summary": {
            "country_count": len(countries),
            "machine_country_count": sum(
                1 for item in countries if item["machine_radar_available"]
            ),
            "live_probe_enabled": bool(live),
            "status": status,
        },
        "limits": [
            "National radar interfaces are provider-specific and often require API keys, licences or STAC/WMS handling.",
            "MeteoVoid reports interface readiness separately from machine-readable radar evidence.",
            "A country radar source becomes machine evidence only when a local/downloaded file is readable and metrics are computed.",
            "OPERA ORD remains the preferred unified pan-European machine radar path when configured.",
        ],
    }


def write_sources_csv(payload: dict[str, Any], path: str | Path) -> None:
    rows: list[dict[str, Any]] = []
    for country in payload.get("countries", []):
        if not isinstance(country, dict):
            continue
        for source in country.get("sources", []):
            if not isinstance(source, dict):
                continue
            rows.append(
                {
                    "country": country.get("country"),
                    "label": country.get("label"),
                    "provider": source.get("provider"),
                    "source_id": source.get("id"),
                    "status": source.get("status"),
                    "evidence_level": source.get("evidence_level"),
                    "api_key_env": source.get("api_key_env") or "",
                    "api_key_configured": source.get("api_key_configured"),
                    "machine_evidence": source.get("machine_evidence"),
                    "expected_format": source.get("expected_format"),
                    "public_reference": source.get("public_reference"),
                    "source_family": source.get("source_family"),
                }
            )
    with Path(path).open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "country",
                "label",
                "provider",
                "source_id",
                "status",
                "evidence_level",
                "api_key_env",
                "api_key_configured",
                "machine_evidence",
                "expected_format",
                "public_reference",
                "source_family",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def write_map(payload: dict[str, Any], path: str | Path) -> None:
    countries = json.dumps(payload.get("countries", []), ensure_ascii=False)
    html = f"""<!doctype html>
<html lang=\"fr\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
<title>MeteoVoid · radars Europe nationale</title>
<link rel=\"stylesheet\" href=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.css\" />
<style>body{{margin:0;font-family:Inter,Segoe UI,Arial,sans-serif;background:#0e1726;color:#e8eef7}}header{{padding:14px 18px;background:#13213a}}#map{{height:calc(100vh - 88px)}}.legend{{position:absolute;z-index:500;right:14px;top:104px;background:rgba(12,20,34,.93);border:1px solid rgba(255,255,255,.14);border-radius:14px;padding:12px;max-width:360px}}.muted{{color:#9fb0c8}}</style>
</head><body><header><h1 style=\"margin:0;font-size:20px\">MeteoVoid · radars Espagne / France / Suisse / Pays-Bas</h1><div class=\"muted\">Interfaces nationales + OPERA ORD fallback. Les rectangles indiquent les zones suivies, pas une confirmation radar automatique.</div></header><div id=\"map\"></div><div class=\"legend\" id=\"legend\"></div>
<script src=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.js\"></script><script>
const countries = {countries};
const map = L.map('map').setView([47.5, 3.0], 5);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{maxZoom: 10, attribution:'&copy; OpenStreetMap'}}).addTo(map);
function color(c){{ return c.machine_radar_available ? '#2fbf71' : (c.priority_for_belgium === 'high' ? '#f59e0b' : '#60a5fa'); }}
for (const c of countries){{
  const b = c.bbox || {{}}; if([b.south,b.west,b.north,b.east].some(v => v === undefined)) continue;
  const rect = L.rectangle([[b.south,b.west],[b.north,b.east]], {{color: color(c), weight:2, fillOpacity:.12}}).addTo(map);
  const sourceRows = (c.sources || []).map(s => `<li><b>${{s.provider}}</b> · ${{s.status}}</li>`).join('');
  rect.bindPopup(`<b>${{c.label}}</b><br>${{c.upstream_role || ''}}<br><ul>${{sourceRows}}</ul>`);
}}
document.getElementById('legend').innerHTML = `<b>Statut</b><p class=\"muted\">Vert : métriques machine locales disponibles. Orange/bleu : interfaces prêtes mais pas de preuve machine.</p><p>${{countries.length}} pays suivis.</p>`;
</script></body></html>"""
    Path(path).write_text(html, encoding="utf-8")


def write_report(payload: dict[str, Any], path: str | Path) -> None:
    lines = [
        "# MeteoVoid · Radars nationaux Europe",
        "",
        "Extension radar pour Espagne, France, Suisse et Pays-Bas.",
        "",
        f"- Généré : `{payload.get('generated_at')}`",
        f"- Statut : `{payload.get('status')}`",
        f"- Live probe : `{payload.get('live_probe_enabled')}`",
        "",
        "## Pays suivis",
        "",
    ]
    for country in payload.get("countries", []):
        if not isinstance(country, dict):
            continue
        lines.append(
            f"- **{country.get('label')}** (`{country.get('country')}`) · priorité Belgique : `{country.get('priority_for_belgium')}` · machine radar : `{country.get('machine_radar_available')}`"
        )
        for source in country.get("sources", []):
            if isinstance(source, dict):
                lines.append(
                    f"  - {source.get('provider')} · `{source.get('status')}` · preuve `{source.get('evidence_level')}`"
                )
    lines.extend(
        [
            "",
            "## Règle de prudence",
            "",
            "Une interface nationale configurée ne devient pas une confirmation radar machine tant qu’un fichier radar n’est pas téléchargé ou fourni localement, lu et transformé en métriques.",
            "",
            "OPERA ORD reste la couche paneuropéenne unifiée ; les sources nationales servent à enrichir ou vérifier par pays lorsque les accès sont disponibles.",
            "",
        ]
    )
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def write_european_national_radar_outputs(
    out_dir: str | Path,
    *,
    config_path: str | Path | None = DEFAULT_CONFIG,
    live: bool = False,
    timeout_s: float | None = None,
    country_files: dict[str, list[Path]] | None = None,
) -> dict[str, Any]:
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    config = _load_yaml(config_path)
    outputs_raw = config.get("output_files")
    outputs: dict[str, Any] = outputs_raw if isinstance(outputs_raw, dict) else {}
    payload = build_european_national_radar(
        config_path,
        live=live,
        timeout_s=timeout_s,
        country_files=country_files,
    )
    status_name = str(outputs.get("status_json") or "european_national_radar_status.json")
    metrics_name = str(outputs.get("metrics_json") or "european_national_radar_metrics.json")
    csv_name = str(outputs.get("sources_csv") or "european_national_radar_sources.csv")
    map_name = str(outputs.get("map_html") or "european_national_radar_map.html")
    report_name = str(outputs.get("report_md") or "european_national_radar_report.md")
    (root / status_name).write_text(_json_dumps(payload), encoding="utf-8")
    (root / metrics_name).write_text(_json_dumps(payload.get("metrics", {})), encoding="utf-8")
    write_sources_csv(payload, root / csv_name)
    write_map(payload, root / map_name)
    write_report(payload, root / report_name)
    return payload
