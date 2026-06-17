from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import yaml  # type: ignore[import-untyped]

OPERA_ORD_DEFAULT_BASE_URL = "https://api.meteogate.eu/eu-eumetnet-weather-radar"
OPERA_COMPOSITE_LOCATION_ID = "0-20010-0-OPERA"
DEFAULT_USER_AGENT = "MeteoVoid-OperaORD/1.0"
DEFAULT_PRODUCTS = ["DBZH", "RATE", "ACRR"]


def _utc_now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _load_yaml_mapping(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    payload = yaml.safe_load(p.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}
    return default


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        out = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(out) or math.isinf(out):
        return default
    return out


def _config_api(config: dict[str, Any]) -> dict[str, Any]:
    api = config.get("api")
    if isinstance(api, dict):
        return api
    return {
        "base_url": config.get("base_url"),
        "timeout_seconds": config.get("timeout_seconds"),
        "max_retries": config.get("max_retries"),
        "user_agent": config.get("user_agent"),
        "api_key_env": config.get("api_key_env"),
    }


def _config_cache(config: dict[str, Any]) -> dict[str, Any]:
    cache = config.get("cache")
    return cache if isinstance(cache, dict) else {}


def _config_products(config: dict[str, Any]) -> dict[str, Any]:
    products = config.get("products")
    return products if isinstance(products, dict) else {}


def _config_outputs(config: dict[str, Any]) -> dict[str, Any]:
    outputs = config.get("outputs")
    return outputs if isinstance(outputs, dict) else {}


def _bbox_from_config(config: dict[str, Any], key: str) -> tuple[float, float, float, float]:
    bbox = config.get(key)
    if isinstance(bbox, dict):
        west = _safe_float(bbox.get("west"), None)
        south = _safe_float(bbox.get("south"), None)
        east = _safe_float(bbox.get("east"), None)
        north = _safe_float(bbox.get("north"), None)
        if west is not None and south is not None and east is not None and north is not None:
            return (west, south, east, north)
    return (-2.5, 47.0, 9.5, 53.5)


def _request_headers(config: dict[str, Any]) -> dict[str, str]:
    api = _config_api(config)
    headers = {"User-Agent": str(api.get("user_agent") or DEFAULT_USER_AGENT)}
    api_key_env = str(api.get("api_key_env") or "METEOGATE_API_KEY")
    api_key = os.getenv(api_key_env, "")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _base_url_from_config(config: dict[str, Any]) -> str:
    api = _config_api(config)
    return str(
        os.getenv("METEOVOID_OPERA_ORD_BASE_URL")
        or api.get("base_url")
        or config.get("base_url")
        or OPERA_ORD_DEFAULT_BASE_URL
    ).rstrip("/")


def build_location_query_url(
    *,
    base_url: str = OPERA_ORD_DEFAULT_BASE_URL,
    collection: str = "observations",
    location_id: str = OPERA_COMPOSITE_LOCATION_ID,
    datetime_range: str = "",
    standard_name: str = "DBZH",
    level: str = "../5.0",
    data_format: str = "ODIM",
    method: str = "comp",
    f: str = "CoverageJSON",
) -> str:
    root = base_url.rstrip("/")
    path = f"{root}/collections/{collection}/locations/{location_id}"
    params = {"f": f}
    if datetime_range:
        params["datetime"] = datetime_range
    if standard_name:
        params["standard_name"] = standard_name
    if level:
        params["level"] = level
    if data_format:
        params["format"] = data_format
    if method:
        params["method"] = method
    return f"{path}?{urlencode(params)}"


def build_items_query_url(
    *,
    base_url: str = OPERA_ORD_DEFAULT_BASE_URL,
    collection: str = "observations",
    bbox: tuple[float, float, float, float] | None = None,
    datetime_range: str = "",
    standard_name: str = "DBZH",
    level: str = "../5.0",
    data_format: str = "ODIM",
    method: str = "scan",
    f: str = "json",
) -> str:
    root = base_url.rstrip("/")
    path = f"{root}/collections/{collection}/items"
    params = {"f": f}
    if bbox is not None:
        params["bbox"] = ",".join(str(v) for v in bbox)
    if datetime_range:
        params["datetime"] = datetime_range
    if standard_name:
        params["standard_name"] = standard_name
    if level:
        params["level"] = level
    if data_format:
        params["format"] = data_format
    if method:
        params["method"] = method
    return f"{path}?{urlencode(params)}"


def extract_data_links(payload: Any) -> list[str]:
    links: list[str] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            href = obj.get("href") or obj.get("data") or obj.get("url")
            if isinstance(href, str) and (href.startswith("http://") or href.startswith("https://")):
                rel = str(obj.get("rel") or "")
                media_type = str(obj.get("type") or obj.get("mediaType") or "")
                lower_href = href.lower()
                if (
                    rel in {"data", "item", "enclosure", "alternate"}
                    or any(token in media_type.lower() for token in ["hdf", "tiff", "geotiff", "octet"])
                    or any(token in lower_href for token in [".h5", ".hdf", ".hdf5", ".tif", ".tiff"])
                ):
                    links.append(href)
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(payload)
    return sorted(set(links))


def _query_json(url: str, *, headers: dict[str, str], timeout_s: float) -> dict[str, Any]:
    request = Request(url, headers=headers)
    with urlopen(request, timeout=timeout_s) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))
    return payload if isinstance(payload, dict) else {"payload": payload}


def _query_json_safe(url: str, *, headers: dict[str, str], timeout_s: float) -> dict[str, Any]:
    try:
        payload = _query_json(url, headers=headers, timeout_s=timeout_s)
        return {
            "ok": True,
            "status": "ok",
            "payload": payload,
            "links": extract_data_links(payload),
        }
    except HTTPError as exc:
        return {
            "ok": False,
            "status": "no_content" if exc.code == 204 else "rate_limited" if exc.code == 429 else "http_error",
            "http_status": exc.code,
            "detail": str(exc)[:240],
            "links": [],
        }
    except (OSError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "status": "query_error", "detail": str(exc)[:240], "links": []}


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_download_name(url: str, index: int) -> str:
    raw = url.split("/")[-1].split("?")[0].strip()
    if not raw:
        raw = f"opera_ord_{index}.bin"
    safe = "".join(ch if ch.isalnum() or ch in {".", "_", "-"} else "_" for ch in raw)
    return safe[:180] or f"opera_ord_{index}.bin"


def download_data_links(
    links: list[str],
    out_dir: str | Path,
    *,
    headers: dict[str, str] | None = None,
    timeout_s: float = 60.0,
    max_files: int = 8,
) -> list[dict[str, Any]]:
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    out: list[dict[str, Any]] = []
    for index, url in enumerate(links[:max_files], start=1):
        target = root / _safe_download_name(url, index)
        record: dict[str, Any] = {"url": url, "path": str(target), "status": "pending"}
        try:
            request = Request(url, headers=headers or {"User-Agent": DEFAULT_USER_AGENT})
            with urlopen(request, timeout=timeout_s) as response:  # noqa: S310
                with target.open("wb") as fh:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        fh.write(chunk)
            record.update(
                {
                    "status": "downloaded",
                    "size_bytes": target.stat().st_size,
                    "sha256": sha256_file(target),
                    "downloaded_at": _utc_now(),
                }
            )
        except (OSError, URLError, TimeoutError, HTTPError) as exc:
            record.update({"status": "download_error", "detail": str(exc)[:240]})
        out.append(record)
    return out


def _read_numeric_array(path: str | Path) -> np.ndarray:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".npy":
        return np.asarray(np.load(p), dtype=float)
    if suffix in {".csv", ".txt"}:
        return np.loadtxt(p, delimiter="," if suffix == ".csv" else None)
    if suffix in {".json", ".geojson"}:
        payload = json.loads(p.read_text(encoding="utf-8"))
        data = payload.get("data") if isinstance(payload, dict) else payload
        return np.asarray(data, dtype=float)
    raise ValueError(f"unsupported numeric radar format: {suffix}")


def analyse_geotiff(path: str | Path, bbox: tuple[float, float, float, float] | None = None) -> dict[str, Any]:
    try:
        import rasterio  # type: ignore[import-not-found]
        from rasterio.windows import from_bounds  # type: ignore[import-not-found]
    except ImportError as exc:
        return {"ok": False, "status": "rasterio_missing", "detail": str(exc)[:160]}

    try:
        with rasterio.open(Path(path)) as src:
            if bbox is None:
                data = src.read(1, masked=True)
            else:
                window = from_bounds(*bbox, transform=src.transform)
                data = src.read(1, window=window, masked=True)
        values = data.compressed() if hasattr(data, "compressed") else np.asarray(data).ravel()
        values = values[np.isfinite(values)]
        if values.size == 0:
            return {"ok": False, "status": "empty_geotiff_area"}
        return {
            "ok": True,
            "status": "analysed_geotiff",
            "reader": "rasterio",
            "shape": list(data.shape),
            "min": float(np.min(values)),
            "max": float(np.max(values)),
            "mean": float(np.mean(values)),
            "p95": float(np.percentile(values, 95)),
            "finite_count": int(values.size),
        }
    except Exception as exc:  # pragma: no cover - depends on external raster drivers/data
        return {"ok": False, "status": "geotiff_read_error", "detail": str(exc)[:240]}


def analyse_odim_hdf5(path: str | Path) -> dict[str, Any]:
    try:
        import wradlib as wrl  # type: ignore[import-not-found]
    except ImportError as exc:
        return {"ok": False, "status": "wradlib_missing", "detail": str(exc)[:160]}

    try:
        reader = getattr(getattr(wrl, "io", None), "read_opera_hdf5", None)
        if reader is None:
            return {
                "ok": True,
                "status": "wradlib_available_reader_not_exposed",
                "wradlib_version": getattr(wrl, "__version__", "unknown"),
            }
        raw = reader(str(path))
        keys = sorted(str(key) for key in raw.keys()) if isinstance(raw, dict) else []
        return {
            "ok": True,
            "status": "readable_odim_hdf5",
            "reader": "wradlib",
            "wradlib_version": getattr(wrl, "__version__", "unknown"),
            "top_level_keys": keys[:80],
        }
    except Exception as exc:  # pragma: no cover - ODIM layouts vary by producer/product
        return {"ok": False, "status": "odim_read_error", "detail": str(exc)[:240]}


def analyse_radar_file(path: str | Path, bbox: tuple[float, float, float, float] | None = None) -> dict[str, Any]:
    p = Path(path)
    result: dict[str, Any] = {"path": str(p), "exists": p.exists(), "status": "missing"}
    if not p.exists():
        return result
    suffix = p.suffix.lower()
    if suffix in {".tif", ".tiff"}:
        result.update(analyse_geotiff(p, bbox=bbox))
        return result
    if suffix in {".h5", ".hdf", ".hdf5"}:
        result.update(analyse_odim_hdf5(p))
        return result
    try:
        arr = _read_numeric_array(p)
        values = arr[np.isfinite(arr)]
        result.update(
            {
                "ok": bool(values.size),
                "status": "analysed_numeric" if values.size else "empty_numeric_array",
                "reader": "numeric_fallback",
                "shape": list(arr.shape),
                "min": float(np.min(values)) if values.size else None,
                "max": float(np.max(values)) if values.size else None,
                "mean": float(np.mean(values)) if values.size else None,
                "p95": float(np.percentile(values, 95)) if values.size else None,
                "finite_fraction": float(values.size / arr.size) if arr.size else None,
            }
        )
        return result
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result.update({"status": "unreadable", "detail": str(exc)[:220]})
        return result


def _activity_score_from_metrics(metrics: list[dict[str, Any]]) -> float | None:
    scores: list[float] = []
    for metric in metrics:
        if not metric.get("ok"):
            continue
        value = _safe_float(metric.get("p95"), _safe_float(metric.get("max"), None))
        if value is None:
            continue
        # Conservative generic normalisation: radar reflectivity/rate products have
        # different units, so the score is an activity proxy, not an official scale.
        scores.append(max(0.0, min(1.0, value / 60.0)))
    if not scores:
        return None
    return float(max(scores))


def build_opera_inventory(
    config_path: str | Path | None = "config/opera_ord.yaml",
    *,
    enabled: bool = False,
    timeout_s: float = 8.0,
    datetime_range: str = "",
    products: list[str] | None = None,
) -> dict[str, Any]:
    config = _load_yaml_mapping(config_path)
    api = _config_api(config)
    base_url = _base_url_from_config(config)
    headers = _request_headers(config)
    api_key_env = str(api.get("api_key_env") or "METEOGATE_API_KEY")
    timeout = float(api.get("timeout_seconds") or timeout_s)
    products_cfg = _config_products(config)
    composite_cfg = products_cfg.get("composites") if isinstance(products_cfg.get("composites"), dict) else {}
    product_names = products or list(composite_cfg.get("standard_names") or DEFAULT_PRODUCTS)
    location_id = str(composite_cfg.get("location_id") or OPERA_COMPOSITE_LOCATION_ID)
    method = str(composite_cfg.get("method") or "comp")
    format_priority = list(composite_cfg.get("format_priority") or ["GEOTIFF", "ODIM"])
    old_queries = [q for q in config.get("queries", []) if isinstance(q, dict)] if isinstance(config.get("queries"), list) else []

    inventory: dict[str, Any] = {
        "contract": "opera_ord_inventory_v1",
        "generated_at": _utc_now(),
        "enabled": bool(enabled),
        "base_url": base_url,
        "api_key_configured": bool(os.getenv(api_key_env, "")),
        "datetime_range": datetime_range,
        "status": "disabled" if not enabled else "pending",
        "discovery": {"url": f"{base_url}/collections", "status": "not_fetched"},
        "queries": [],
        "data_links": [],
        "limits": [
            "OPERA ORD is used only through documented MeteoGate/ORD endpoints.",
            "MeteoVoid reports no_content, rate_limited or unavailable instead of inventing radar data.",
            "RainViewer display is not treated as OPERA machine radar evidence.",
        ],
    }

    query_specs: list[dict[str, Any]] = []
    for product in product_names:
        for data_format in format_priority:
            query_specs.append(
                {
                    "id": f"opera_comp_{str(product).lower()}_{str(data_format).lower()}",
                    "mode": "composite_location",
                    "collection": "observations",
                    "location_id": location_id,
                    "standard_name": str(product),
                    "level": "../5.0",
                    "format": str(data_format),
                    "method": method,
                    "f": "CoverageJSON",
                }
            )
    query_specs.extend(old_queries)

    for spec in query_specs:
        url = build_location_query_url(
            base_url=base_url,
            collection=str(spec.get("collection") or "observations"),
            location_id=str(spec.get("location_id") or location_id),
            datetime_range=str(spec.get("datetime") or datetime_range),
            standard_name=str(spec.get("standard_name") or "DBZH"),
            level=str(spec.get("level") or "../5.0"),
            data_format=str(spec.get("format") or "ODIM"),
            method=str(spec.get("method") or "comp"),
            f=str(spec.get("f") or "CoverageJSON"),
        )
        inventory["queries"].append(
            {
                "id": str(spec.get("id") or spec.get("standard_name") or "ord_query"),
                "url": url,
                "standard_name": str(spec.get("standard_name") or "DBZH"),
                "format": str(spec.get("format") or "ODIM"),
                "method": str(spec.get("method") or "comp"),
                "status": "not_fetched",
                "links_count": 0,
            }
        )

    if not enabled:
        return inventory

    discovery = _query_json_safe(f"{base_url}/collections", headers=headers, timeout_s=timeout)
    collections = discovery.get("payload", {}).get("collections") if discovery.get("ok") else None
    inventory["discovery"].update(
        {
            "status": discovery.get("status"),
            "ok": discovery.get("ok"),
            "collections_count": len(collections) if isinstance(collections, list) else None,
            "detail": discovery.get("detail"),
        }
    )
    inventory["status"] = "available" if discovery.get("ok") else str(discovery.get("status"))

    all_links: list[str] = []
    for query in inventory["queries"]:
        if not isinstance(query, dict):
            continue
        result = _query_json_safe(str(query.get("url")), headers=headers, timeout_s=timeout)
        links = result.get("links") if isinstance(result.get("links"), list) else []
        all_links.extend(str(link) for link in links)
        query.update(
            {
                "status": result.get("status"),
                "ok": result.get("ok"),
                "links_count": len(links),
                "http_status": result.get("http_status"),
                "detail": result.get("detail"),
            }
        )

    inventory["data_links"] = sorted(set(all_links))
    if inventory["data_links"]:
        inventory["status"] = "data_links_available"
    elif inventory["status"] == "available":
        inventory["status"] = "metadata_available_no_data_links"
    return inventory


def build_opera_metrics(
    files_manifest: list[dict[str, Any]],
    *,
    bbox: tuple[float, float, float, float] | None = None,
) -> dict[str, Any]:
    metrics: list[dict[str, Any]] = []
    for item in files_manifest:
        if not isinstance(item, dict) or item.get("status") != "downloaded":
            continue
        path = item.get("path")
        if not isinstance(path, str):
            continue
        metrics.append(analyse_radar_file(path, bbox=bbox))
    score = _activity_score_from_metrics(metrics)
    return {
        "contract": "opera_radar_metrics_v1",
        "generated_at": _utc_now(),
        "status": "metrics_available" if score is not None else "no_machine_radar_metrics",
        "machine_radar_available": score is not None,
        "radar_activity_score": score,
        "file_count": len(files_manifest),
        "analysed_file_count": len(metrics),
        "files": metrics,
        "limits": [
            "Metrics are computed only from downloaded/readable OPERA files or local radar files.",
            "Generic radar_activity_score is a MeteoVoid proxy, not an official OPERA warning scale.",
        ],
    }


def inspect_opera_ord(
    config_path: str | Path | None = "config/opera_ord.yaml",
    *,
    enabled: bool = False,
    timeout_s: float = 8.0,
    datetime_range: str = "",
    cache_dir: str | Path | None = None,
    download: bool = False,
    max_download_files: int = 8,
) -> dict[str, Any]:
    config = _load_yaml_mapping(config_path)
    inventory = build_opera_inventory(
        config_path,
        enabled=enabled,
        timeout_s=timeout_s,
        datetime_range=datetime_range,
    )
    headers = _request_headers(config)
    cache = _config_cache(config)
    bbox = _bbox_from_config(config, "upstream_bbox")
    cache_root = Path(cache_dir or cache.get("root_dir") or ".cache/opera_ord")
    files: list[dict[str, Any]] = []
    links = [str(link) for link in inventory.get("data_links", []) if isinstance(link, str)]
    if enabled and download and links:
        files = download_data_links(
            links,
            cache_root,
            headers=headers,
            timeout_s=max(float(timeout_s), 30.0),
            max_files=int(max_download_files),
        )
    metrics = build_opera_metrics(files, bbox=bbox)
    status = str(inventory.get("status"))
    if metrics.get("machine_radar_available"):
        status = "metrics_available"
    elif any(item.get("status") == "downloaded" for item in files):
        status = "files_downloaded_not_metric_ready"
    return {
        "contract": "opera_ord_connector_v2",
        "generated_at": _utc_now(),
        "enabled": bool(enabled),
        "download_enabled": bool(download),
        "status": status,
        "base_url": inventory.get("base_url"),
        "discovery_url": inventory.get("discovery", {}).get("url") if isinstance(inventory.get("discovery"), dict) else None,
        "api_key_configured": inventory.get("api_key_configured"),
        "inventory": inventory,
        "files_manifest": files,
        "metrics": metrics,
        "machine_radar_confirmation": bool(metrics.get("machine_radar_available")),
        "radar_activity_score": metrics.get("radar_activity_score"),
        "limits": [
            "Full OPERA ORD mode needs live MeteoGate access and downloadable radar files.",
            "If only metadata are available, MeteoVoid does not claim machine radar confirmation.",
            "If no OPERA files are readable, the honest state remains no_machine_radar_data.",
        ],
    }


def write_opera_ord_outputs(
    out_dir: str | Path,
    *,
    config_path: str | Path | None = "config/opera_ord.yaml",
    enabled: bool = False,
    timeout_s: float = 8.0,
    datetime_range: str = "",
    download: bool = False,
    max_download_files: int = 8,
) -> dict[str, Any]:
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    config = _load_yaml_mapping(config_path)
    outputs = _config_outputs(config)
    cache = _config_cache(config)
    cache_root = Path(cache.get("root_dir") or (root / "opera_ord_cache"))
    if not cache_root.is_absolute():
        cache_root = root / cache_root
    status = inspect_opera_ord(
        config_path,
        enabled=enabled,
        timeout_s=timeout_s,
        datetime_range=datetime_range,
        cache_dir=cache_root,
        download=download,
        max_download_files=max_download_files,
    )
    inventory = status.get("inventory") if isinstance(status.get("inventory"), dict) else {}
    metrics = status.get("metrics") if isinstance(status.get("metrics"), dict) else {}
    files_manifest = status.get("files_manifest") if isinstance(status.get("files_manifest"), list) else []
    (root / str(outputs.get("status_json") or "opera_ord_status.json")).write_text(
        _json_dumps(status), encoding="utf-8"
    )
    (root / str(outputs.get("inventory_json") or "opera_ord_inventory.json")).write_text(
        _json_dumps(inventory), encoding="utf-8"
    )
    (root / str(outputs.get("metrics_json") or "opera_radar_metrics.json")).write_text(
        _json_dumps(metrics), encoding="utf-8"
    )
    (root / str(outputs.get("files_manifest") or "opera_ord_files_manifest.json")).write_text(
        _json_dumps(files_manifest), encoding="utf-8"
    )
    return status
