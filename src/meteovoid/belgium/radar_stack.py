from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

import numpy as np

from meteovoid.belgium.opera_ord import (
    OPERA_ORD_DEFAULT_BASE_URL,
    analyse_radar_file,
    build_location_query_url,
    inspect_opera_ord as _inspect_opera_ord_v2,
    write_opera_ord_outputs,
)

RAINVIEWER_API_URL = "https://api.rainviewer.com/public/weather-maps.json"
DEFAULT_USER_AGENT = "MeteoVoid-RadarStack/1.0"


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _utc_now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


def _http_json(url: str, *, timeout_s: float) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    with urlopen(request, timeout=timeout_s) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("HTTP JSON response must be an object")
    return payload


def _frame_count(payload: dict[str, Any], key: str) -> int:
    radar = payload.get("radar") if isinstance(payload.get("radar"), dict) else {}
    frames = radar.get(key) if isinstance(radar, dict) else None
    return len(frames) if isinstance(frames, list) else 0


def build_rainviewer_status(*, fetch_live: bool = False, timeout_s: float = 5.0) -> dict[str, Any]:
    """Return transparent RainViewer availability metadata.

    RainViewer is useful for immediate display, but MeteoVoid does not convert
    visual tiles into machine radar evidence.
    """

    status: dict[str, Any] = {
        "contract": "rainviewer_radar_overlay_v1",
        "generated_at": _utc_now(),
        "provider": "RainViewer Weather Maps API",
        "api_url": RAINVIEWER_API_URL,
        "configured": True,
        "fetch_live": bool(fetch_live),
        "status": "client_side_overlay_ready",
        "past_frame_count": None,
        "nowcast_frame_count": None,
        "host": None,
        "last_frame_time_unix": None,
        "evidence_level": "display_only",
        "limits": [
            "RainViewer is used as a visual radar overlay, not as an official warning source.",
            "The map fetches tiles client-side; CI/offline runs do not need external access.",
            "Radar tiles are not treated as verified European radar data for scoring unless a licensed data connector provides machine-readable fields.",
        ],
    }
    if not fetch_live:
        return status
    try:
        payload = _http_json(RAINVIEWER_API_URL, timeout_s=timeout_s)
        radar = payload.get("radar") if isinstance(payload.get("radar"), dict) else {}
        past = radar.get("past") if isinstance(radar, dict) else []
        nowcast = radar.get("nowcast") if isinstance(radar, dict) else []
        frames = [frame for frame in past if isinstance(frame, dict)] if isinstance(past, list) else []
        status.update(
            {
                "status": "ok",
                "version": payload.get("version"),
                "generated_unix": payload.get("generated"),
                "host": payload.get("host"),
                "past_frame_count": _frame_count(payload, "past"),
                "nowcast_frame_count": len(nowcast) if isinstance(nowcast, list) else 0,
                "last_frame_time_unix": frames[-1].get("time") if frames else None,
            }
        )
    except (OSError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        status.update({"status": "error", "detail": str(exc)[:240]})
    return status


def write_rainviewer_map(path: str | Path) -> None:
    """Write a self-contained RainViewer/Leaflet radar overlay page."""

    html = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>MeteoVoid · RainViewer radar</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<style>
body{margin:0;font-family:Inter,Segoe UI,Arial,sans-serif;background:#0e1726;color:#e8eef7}
header{padding:14px 18px;background:#121f34;border-bottom:1px solid rgba(255,255,255,.12)}
#map{height:calc(100vh - 116px);min-height:520px;background:#172338}
.panel{position:absolute;z-index:500;right:18px;top:92px;max-width:360px;background:rgba(14,23,38,.92);border:1px solid rgba(255,255,255,.16);border-radius:16px;padding:14px;box-shadow:0 16px 36px rgba(0,0,0,.28)}
button{border:1px solid rgba(255,255,255,.22);background:#223653;color:#e8eef7;border-radius:10px;padding:8px 10px;margin:4px;cursor:pointer}
button.active{background:#d96b25;color:#fff}.muted{color:#9dafc5}.error{color:#ffb4a8}
a{color:#9fd0ff}
</style>
</head>
<body>
<header>
<h1 style="margin:0;font-size:20px">MeteoVoid · radar RainViewer</h1>
<div class="muted">Affichage immédiat des tuiles radar publiques. Cette couche ne remplace pas OPERA, IRM/KMI ou les alertes officielles.</div>
</header>
<div id="map"></div>
<div class="panel">
<strong>Trames radar</strong>
<div id="status" class="muted">Chargement RainViewer…</div>
<div id="frames" style="margin-top:10px"></div>
<p class="muted" style="font-size:13px">Les tuiles sont chargées côté navigateur via l’API publique RainViewer. MeteoVoid ne fabrique pas de confirmation radar à partir de cette carte.</p>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const map = L.map('map', {preferCanvas: true}).setView([50.65, 4.70], 7);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 12, attribution: '&copy; OpenStreetMap contributors'
}).addTo(map);
const statusEl = document.getElementById('status');
const framesEl = document.getElementById('frames');
let radarLayer = null;
function setFrame(host, frame, index){
  if(radarLayer){ map.removeLayer(radarLayer); }
  const tileUrl = `${host}${frame.path}/256/{z}/{x}/{y}/2/1_1.png`;
  radarLayer = L.tileLayer(tileUrl, {opacity: 0.72, zIndex: 10, maxZoom: 10});
  radarLayer.addTo(map);
  [...framesEl.querySelectorAll('button')].forEach((button, i) => button.classList.toggle('active', i === index));
  const stamp = new Date(frame.time * 1000).toISOString().replace('T', ' ').replace('.000Z', ' UTC');
  statusEl.textContent = `Trame affichée : ${stamp}`;
}
fetch('https://api.rainviewer.com/public/weather-maps.json')
  .then(response => response.json())
  .then(data => {
    const host = data.host;
    const frames = ((data.radar && data.radar.past) || []);
    if(!host || !frames.length){ throw new Error('Aucune trame radar disponible'); }
    framesEl.innerHTML = '';
    const recent = frames.slice(-8);
    recent.forEach((frame, index) => {
      const button = document.createElement('button');
      const date = new Date(frame.time * 1000);
      button.textContent = date.toISOString().substring(11,16);
      button.onclick = () => setFrame(host, frame, index);
      framesEl.appendChild(button);
    });
    setFrame(host, recent[recent.length - 1], recent.length - 1);
  })
  .catch(error => {
    statusEl.innerHTML = `<span class="error">RainViewer indisponible : ${error.message}</span>`;
  });
</script>
</body>
</html>
"""
    Path(path).write_text(html, encoding="utf-8")


def build_opera_ord_query_url(
    *,
    base_url: str = OPERA_ORD_DEFAULT_BASE_URL,
    collection: str = "observations",
    location_id: str = "",
    datetime_range: str = "",
    standard_name: str = "DBZH",
    level: str = "../5.0",
    data_format: str = "ODIM",
    method: str = "scan",
    f: str = "CoverageJSON",
) -> str:
    return build_location_query_url(
        base_url=base_url,
        collection=collection,
        location_id=location_id or "0-578-0-nohur",
        datetime_range=datetime_range,
        standard_name=standard_name,
        level=level,
        data_format=data_format,
        method=method,
        f=f,
    )


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
    return _inspect_opera_ord_v2(
        config_path,
        enabled=enabled,
        timeout_s=timeout_s,
        datetime_range=datetime_range,
        cache_dir=cache_dir,
        download=download,
        max_download_files=max_download_files,
    )


def _load_numeric_array(path: str | Path) -> np.ndarray:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".npy":
        return np.asarray(np.load(p), dtype=float)
    if suffix in {".json", ".geojson"}:
        payload = json.loads(p.read_text(encoding="utf-8"))
        data = payload.get("data") if isinstance(payload, dict) else payload
        return np.asarray(data, dtype=float)
    if suffix in {".csv", ".txt"}:
        return np.loadtxt(p, delimiter="," if suffix == ".csv" else None)
    raise ValueError(f"unsupported radar array fallback format: {p.suffix}")


def analyze_radar_files(paths: list[str | Path]) -> dict[str, Any]:
    frames = [analyse_radar_file(path) for path in paths]
    values: list[float] = []
    for frame in frames:
        if frame.get("status") not in {"analysed_numeric", "analysed_geotiff"}:
            continue
        value = frame.get("max") or frame.get("max_value")
        if isinstance(value, (int, float)) and np.isfinite(value):
            values.append(float(value))
    return {
        "contract": "radar_processing_status_v1",
        "generated_at": _utc_now(),
        "frame_count": len(frames),
        "readable_frame_count": len(values),
        "status": "ok" if values else "no_readable_radar_frames",
        "max_value_over_frames": max(values) if values else None,
        "frames": frames,
        "limits": [
            "wradlib/rasterio are optional and only used when installed and local OPERA/national radar files are provided.",
            "No radar intensity is inferred from RainViewer tile display alone.",
        ],
    }


def compute_pysteps_motion(frames: np.ndarray, *, method: str = "LK") -> dict[str, Any]:
    arr = np.asarray(frames, dtype=float)
    if arr.ndim != 3 or arr.shape[0] < 3:
        return {
            "contract": "pysteps_nowcast_status_v1",
            "generated_at": _utc_now(),
            "status": "insufficient_frames",
            "required": "3D array shaped time,y,x with at least 3 frames",
            "shape": list(arr.shape),
        }
    try:
        from pysteps import motion  # type: ignore[import-not-found]

        oflow_method = motion.get_method(method)
        velocity = np.asarray(oflow_method(arr[-3:, :, :]), dtype=float)
        finite = velocity[np.isfinite(velocity)]
        return {
            "contract": "pysteps_nowcast_status_v1",
            "generated_at": _utc_now(),
            "status": "ok",
            "method": method,
            "input_shape": list(arr.shape),
            "velocity_shape": list(velocity.shape),
            "mean_motion_component": float(np.mean(finite)) if finite.size else None,
            "max_abs_motion_component": float(np.max(np.abs(finite))) if finite.size else None,
            "note": "pySTEPS motion field computed from provided radar frame sequence.",
        }
    except ImportError:
        return {
            "contract": "pysteps_nowcast_status_v1",
            "generated_at": _utc_now(),
            "status": "pysteps_not_installed",
            "input_shape": list(arr.shape),
            "note": "Install the optional radar extra to activate pySTEPS nowcasting.",
        }
    except Exception as exc:  # pragma: no cover - third-party algorithm failures are data-dependent
        return {
            "contract": "pysteps_nowcast_status_v1",
            "generated_at": _utc_now(),
            "status": "pysteps_error",
            "input_shape": list(arr.shape),
            "detail": str(exc)[:240],
        }


def compute_pysteps_from_paths(paths: list[str | Path], *, enabled: bool = False) -> dict[str, Any]:
    if not enabled:
        return {
            "contract": "pysteps_nowcast_status_v1",
            "generated_at": _utc_now(),
            "enabled": False,
            "status": "disabled",
            "note": "pySTEPS nowcasting is opt-in and requires a sequence of local radar frames.",
        }
    arrays: list[np.ndarray] = []
    errors: list[str] = []
    for path in paths:
        try:
            arr = np.asarray(_load_numeric_array(path), dtype=float)
            if arr.ndim == 2:
                arrays.append(arr)
            elif arr.ndim == 3:
                arrays.extend([np.asarray(frame, dtype=float) for frame in arr])
            else:
                errors.append(f"{path}: unsupported shape {arr.shape}")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{path}: {exc}")
    if len(arrays) < 3:
        return {
            "contract": "pysteps_nowcast_status_v1",
            "generated_at": _utc_now(),
            "enabled": True,
            "status": "insufficient_readable_frames",
            "readable_frame_count": len(arrays),
            "errors": errors[:5],
        }
    return compute_pysteps_motion(np.stack(arrays, axis=0))


def _machine_state(opera: dict[str, Any], radar_processing: dict[str, Any]) -> str:
    if opera.get("status") == "metrics_available":
        return "opera_ord_metrics_available"
    if any(item.get("status") == "downloaded" for item in opera.get("files_manifest", []) if isinstance(item, dict)):
        return "opera_ord_files_downloaded"
    if radar_processing.get("readable_frame_count", 0) > 0:
        return "local_radar_frames_readable"
    if opera.get("status") in {"data_links_available", "metadata_available_no_data_links"}:
        return "opera_ord_metadata_available"
    return "no_machine_radar_data"


def build_radar_stack(
    *,
    opera_config_path: str | Path | None = "config/opera_ord.yaml",
    radar_frame_paths: list[str | Path] | None = None,
    enable_rainviewer_live: bool = False,
    enable_opera_ord: bool = False,
    enable_pysteps: bool = False,
    enable_opera_download: bool = False,
    opera_datetime_range: str = "",
    opera_cache_dir: str | Path | None = None,
    timeout_s: float = 8.0,
) -> dict[str, Any]:
    paths = radar_frame_paths or []
    rainviewer = build_rainviewer_status(fetch_live=enable_rainviewer_live, timeout_s=timeout_s)
    opera = inspect_opera_ord(
        opera_config_path,
        enabled=enable_opera_ord,
        timeout_s=timeout_s,
        datetime_range=opera_datetime_range,
        cache_dir=opera_cache_dir,
        download=enable_opera_download,
    )
    downloaded_paths = [
        str(item.get("path"))
        for item in opera.get("files_manifest", [])
        if isinstance(item, dict) and item.get("status") == "downloaded" and item.get("path")
    ]
    radar_processing = analyze_radar_files([*paths, *downloaded_paths])
    nowcast = compute_pysteps_from_paths(paths, enabled=enable_pysteps)
    honest_state = _machine_state(opera, radar_processing)
    return {
        "contract": "meteovoid_european_radar_stack_v2",
        "generated_at": _utc_now(),
        "honest_state": honest_state,
        "rainviewer": rainviewer,
        "opera_ord": opera,
        "opera_radar_metrics": opera.get("metrics", {}),
        "radar_processing": radar_processing,
        "pysteps_nowcast": nowcast,
        "summary": {
            "rainviewer_overlay_ready": rainviewer.get("status")
            in {"client_side_overlay_ready", "ok"},
            "rainviewer_evidence_level": rainviewer.get("evidence_level"),
            "opera_ord_enabled": bool(enable_opera_ord),
            "opera_ord_download_enabled": bool(enable_opera_download),
            "opera_ord_status": opera.get("status"),
            "opera_radar_activity_score": opera.get("radar_activity_score"),
            "readable_radar_frames": radar_processing.get("readable_frame_count", 0),
            "pysteps_status": nowcast.get("status"),
            "machine_radar_confirmation": honest_state
            in {
                "local_radar_frames_readable",
                "opera_ord_files_downloaded",
                "opera_ord_metrics_available",
            },
        },
        "limits": [
            "RainViewer provides immediate visual context only.",
            "OPERA ORD is the preferred European machine-data path when configured and reachable.",
            "OPERA machine confirmation requires metadata plus downloaded/readable files, not just a displayed map.",
            "wradlib and pySTEPS are optional heavy dependencies and only run on provided radar files.",
            "If radar files or licensed endpoints are absent, MeteoVoid reports absence explicitly.",
        ],
    }


def _write_markdown(stack: dict[str, Any], path: Path) -> None:
    summary_any = stack.get("summary")
    summary: dict[str, Any] = summary_any if isinstance(summary_any, dict) else {}
    lines = [
        "# MeteoVoid · European Radar Stack",
        "",
        "Couche radar/nowcasting optionnelle et honnête : affichage RainViewer, connecteur OPERA ORD, traitement wradlib/rasterio et nowcasting pySTEPS si les données sont réellement disponibles.",
        "",
        f"- Généré : `{stack.get('generated_at')}`",
        f"- État honnête : `{stack.get('honest_state')}`",
        f"- Overlay RainViewer : `{summary.get('rainviewer_overlay_ready')}`",
        f"- Niveau de preuve RainViewer : `{summary.get('rainviewer_evidence_level')}`",
        f"- OPERA ORD : `{summary.get('opera_ord_status')}`",
        f"- Score activité OPERA : `{summary.get('opera_radar_activity_score')}`",
        f"- Trames radar lisibles : `{summary.get('readable_radar_frames')}`",
        f"- pySTEPS : `{summary.get('pysteps_status')}`",
        "",
        "## Règle de prudence",
        "",
        "MeteoVoid n’utilise pas une carte visuelle comme preuve radar machine. Une confirmation exploitable exige un endpoint/licence ou des fichiers radar locaux lisibles.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_radar_stack_outputs(
    out_dir: str | Path,
    *,
    opera_config_path: str | Path | None = "config/opera_ord.yaml",
    radar_frame_paths: list[str | Path] | None = None,
    enable_rainviewer_live: bool = False,
    enable_opera_ord: bool = False,
    enable_pysteps: bool = False,
    enable_opera_download: bool = False,
    opera_datetime_range: str = "",
    timeout_s: float = 8.0,
) -> dict[str, Any]:
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    opera_cache_dir = root / "opera_ord_cache"
    stack = build_radar_stack(
        opera_config_path=opera_config_path,
        radar_frame_paths=radar_frame_paths,
        enable_rainviewer_live=enable_rainviewer_live,
        enable_opera_ord=enable_opera_ord,
        enable_pysteps=enable_pysteps,
        enable_opera_download=enable_opera_download,
        opera_datetime_range=opera_datetime_range,
        opera_cache_dir=opera_cache_dir,
        timeout_s=timeout_s,
    )
    write_rainviewer_map(root / "rainviewer_radar_map.html")
    (root / "rainviewer_status.json").write_text(_json_dumps(stack["rainviewer"]), encoding="utf-8")
    # Write full OPERA outputs again with the same settings to keep standalone files stable.
    write_opera_ord_outputs(
        root,
        config_path=opera_config_path,
        enabled=enable_opera_ord,
        timeout_s=timeout_s,
        datetime_range=opera_datetime_range,
        download=enable_opera_download,
    )
    (root / "radar_processing_status.json").write_text(
        _json_dumps(stack["radar_processing"]), encoding="utf-8"
    )
    (root / "pysteps_nowcast_status.json").write_text(
        _json_dumps(stack["pysteps_nowcast"]), encoding="utf-8"
    )
    (root / "radar_stack.json").write_text(_json_dumps(stack), encoding="utf-8")
    _write_markdown(stack, root / "radar_stack_report.md")
    return stack
