from __future__ import annotations

import csv
import html
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BE_OUTLINE_LON_LAT: list[tuple[float, float]] = [
    (2.56, 51.09),
    (3.25, 51.37),
    (4.25, 51.50),
    (5.25, 51.34),
    (6.42, 50.75),
    (6.13, 49.50),
    (5.10, 49.48),
    (4.15, 49.77),
    (3.20, 49.95),
    (2.55, 50.73),
]

SEVERITY_COLORS = {
    "normal": "#5da867",
    "watch": "#c8b847",
    "medium": "#e89432",
    "high": "#d9534f",
    "alert": "#6f42c1",
}


@dataclass(frozen=True)
class LayerPoint:
    lat: float
    lon: float
    humidity_pct: float | None
    dew_point_c: float | None
    storm_formation_score: float
    nearest_station: str


def _json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _point_in_polygon(lon: float, lat: float, polygon: list[tuple[float, float]]) -> bool:
    inside = False
    j = len(polygon) - 1
    for i, (xi, yi) in enumerate(polygon):
        xj, yj = polygon[j]
        intersects = (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (
            (yj - yi) or 1e-12
        ) + xi
        if intersects:
            inside = not inside
        j = i
    return inside


def _station_storm_score(station: dict[str, Any]) -> float:
    comps = station.get("components") if isinstance(station.get("components"), dict) else {}
    model_score = _safe_float(station.get("score")) or 0.0
    moisture = _safe_float(comps.get("moisture")) or 0.0
    precipitation = _safe_float(comps.get("precipitation")) or 0.0
    weather_code = _safe_float(comps.get("weather_code")) or 0.0
    wind_gust = _safe_float(comps.get("wind_gust")) or 0.0
    pressure_drop = _safe_float(comps.get("pressure_drop")) or 0.0
    score = (
        model_score * 0.25
        + moisture * 0.22
        + precipitation * 0.22
        + weather_code * 0.18
        + wind_gust * 0.08
        + pressure_drop * 0.05
    )
    return round(_clamp01(score), 6)


def _severity_from_storm_score(score: float) -> str:
    if score >= 0.78:
        return "alert"
    if score >= 0.65:
        return "high"
    if score >= 0.50:
        return "medium"
    if score >= 0.35:
        return "watch"
    return "normal"


def _stations(report: dict[str, Any]) -> list[dict[str, Any]]:
    raw = report.get("stations")
    if not isinstance(raw, list):
        return []
    stations: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        lat = _safe_float(item.get("lat"))
        lon = _safe_float(item.get("lon"))
        if lat is None or lon is None:
            continue
        if item.get("source_ok") is False and _safe_float(item.get("score")) in {None, 0.0}:
            continue
        stations.append(item)
    return stations


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    # Good enough for Belgium-scale interpolation and UI weighting.
    x = (lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2.0)) * 111.32
    y = (lat2 - lat1) * 110.57
    return math.sqrt(x * x + y * y)


def _idw_value(
    lat: float,
    lon: float,
    stations: list[dict[str, Any]],
    key: str,
    *,
    power: float = 2.0,
) -> tuple[float | None, str]:
    weighted = 0.0
    total = 0.0
    nearest_name = ""
    nearest_distance = float("inf")
    for station in stations:
        slat = _safe_float(station.get("lat"))
        slon = _safe_float(station.get("lon"))
        if slat is None or slon is None:
            continue
        value = (
            _station_storm_score(station)
            if key == "storm_formation_score"
            else _safe_float(station.get(key))
        )
        if value is None:
            continue
        distance = max(_distance_km(lat, lon, slat, slon), 1.0)
        if distance < nearest_distance:
            nearest_distance = distance
            nearest_name = str(station.get("name") or station.get("station_id") or "")
        weight = 1.0 / (distance**power)
        weighted += float(value) * weight
        total += weight
    if total <= 0:
        return None, nearest_name
    return weighted / total, nearest_name


def build_weather_layer_grid(report: dict[str, Any], *, step: float = 0.12) -> list[LayerPoint]:
    stations = _stations(report)
    if not stations:
        return []
    min_lon = min(x for x, _ in BE_OUTLINE_LON_LAT)
    max_lon = max(x for x, _ in BE_OUTLINE_LON_LAT)
    min_lat = min(y for _, y in BE_OUTLINE_LON_LAT)
    max_lat = max(y for _, y in BE_OUTLINE_LON_LAT)
    points: list[LayerPoint] = []
    lat = min_lat
    while lat <= max_lat + 1e-9:
        lon = min_lon
        while lon <= max_lon + 1e-9:
            if _point_in_polygon(lon, lat, BE_OUTLINE_LON_LAT):
                humidity, nearest_h = _idw_value(lat, lon, stations, "max_relative_humidity_pct")
                dew, nearest_d = _idw_value(lat, lon, stations, "max_dew_point_c")
                storm, nearest_s = _idw_value(lat, lon, stations, "storm_formation_score")
                points.append(
                    LayerPoint(
                        lat=round(lat, 4),
                        lon=round(lon, 4),
                        humidity_pct=round(humidity, 3) if humidity is not None else None,
                        dew_point_c=round(dew, 3) if dew is not None else None,
                        storm_formation_score=round(storm or 0.0, 6),
                        nearest_station=nearest_s or nearest_d or nearest_h,
                    )
                )
            lon += step
        lat += step
    return points


def write_weather_layer_grid_csv(points: list[LayerPoint], path: Path) -> None:
    fieldnames = [
        "lat",
        "lon",
        "humidity_pct",
        "dew_point_c",
        "storm_formation_score",
        "storm_formation_level",
        "nearest_station",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for point in points:
            writer.writerow(
                {
                    "lat": point.lat,
                    "lon": point.lon,
                    "humidity_pct": point.humidity_pct,
                    "dew_point_c": point.dew_point_c,
                    "storm_formation_score": point.storm_formation_score,
                    "storm_formation_level": _severity_from_storm_score(
                        point.storm_formation_score
                    ),
                    "nearest_station": point.nearest_station,
                }
            )


def convective_parameters_summary(
    report: dict[str, Any], points: list[LayerPoint]
) -> dict[str, Any]:
    stations = _stations(report)
    dew_values = [p.dew_point_c for p in points if p.dew_point_c is not None]
    humidity_values = [p.humidity_pct for p in points if p.humidity_pct is not None]
    storm_values = [p.storm_formation_score for p in points]
    station_scores = [_station_storm_score(s) for s in stations]
    top_stations = sorted(stations, key=_station_storm_score, reverse=True)[:8]
    return {
        "generated_at": report.get("generated_at"),
        "mode": "derived_from_station_forecasts",
        "source": report.get("source"),
        "limitations": [
            "La couche convective est dérivée des stations Open-Meteo et de leurs composantes de scoring.",
            "CAPE, cisaillement vertical et foudre temps réel ne sont pas encore intégrés comme champs natifs.",
            "La heatmap est une interpolation opérationnelle légère, pas un champ modèle officiel.",
        ],
        "inputs": {
            "station_count": len(stations),
            "grid_point_count": len(points),
            "cape_integrated": False,
            "lightning_potential_integrated": False,
            "radar_overlay_available_in_html": True,
            "windy_optional_compare_available": True,
        },
        "summary": {
            "max_dew_point_c": round(max(dew_values), 3) if dew_values else None,
            "max_relative_humidity_pct": (
                round(max(humidity_values), 3) if humidity_values else None
            ),
            "max_storm_formation_score_grid": round(max(storm_values), 6) if storm_values else None,
            "max_storm_formation_score_station": (
                round(max(station_scores), 6) if station_scores else None
            ),
        },
        "top_storm_formation_stations": [
            {
                "station_id": station.get("station_id"),
                "name": station.get("name"),
                "region": station.get("region"),
                "score": _station_storm_score(station),
                "level": _severity_from_storm_score(_station_storm_score(station)),
                "dew_point_c": station.get("max_dew_point_c"),
                "humidity_pct": station.get("max_relative_humidity_pct"),
                "signals": station.get("signals", []),
            }
            for station in top_stations
        ],
    }


def _html_shell(title: str, body: str, *, subtitle: str = "") -> str:
    subtitle_html = f"<p class='subtitle'>{html.escape(subtitle)}</p>" if subtitle else ""
    return f"""<!doctype html>
<html lang=\"fr\">
<head>
<meta charset=\"utf-8\" />
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
<title>{html.escape(title)}</title>
<link rel=\"stylesheet\" href=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.css\" />
<script src=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.js\"></script>
<style>
:root {{ --ink:#142033; --muted:#697386; --card:#ffffff; --line:#dbe3ef; --bg:#f4f7fb; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:Inter,Segoe UI,Arial,sans-serif; background:var(--bg); color:var(--ink); }}
header {{ padding:22px 28px 14px; background:linear-gradient(135deg,#0f1f35,#1f4a78); color:white; }}
h1 {{ margin:0; font-size:24px; letter-spacing:.2px; }}
.subtitle {{ margin:8px 0 0; color:#d8e6f7; max-width:980px; }}
main {{ padding:18px; }}
.map {{ height:72vh; min-height:560px; border:1px solid var(--line); border-radius:18px; overflow:hidden; box-shadow:0 12px 28px rgba(15,31,53,.12); }}
.panel {{ background:var(--card); border:1px solid var(--line); border-radius:16px; padding:14px; margin-bottom:16px; box-shadow:0 8px 22px rgba(15,31,53,.06); }}
.legend {{ line-height:1.55; font-size:13px; }}
.dot {{ display:inline-block; width:11px; height:11px; border-radius:50%; margin-right:6px; vertical-align:-1px; }}
.note {{ font-size:12px; color:var(--muted); margin-top:10px; }}
.value-pill {{ display:inline-block; padding:4px 8px; border-radius:999px; background:#eef4fb; border:1px solid #d4e2f1; font-size:12px; margin:2px; }}
.controls {{ display:flex; gap:8px; flex-wrap:wrap; align-items:center; }}
.controls button {{ border:1px solid #cbd7e7; background:white; border-radius:999px; padding:7px 12px; cursor:pointer; }}
.controls button.active {{ background:#1f4a78; color:white; border-color:#1f4a78; }}
</style>
</head>
<body>
<header><h1>{html.escape(title)}</h1>{subtitle_html}</header>
<main>{body}</main>
</body>
</html>
"""


def _js_data(report: dict[str, Any], points: list[LayerPoint]) -> tuple[str, str]:
    stations = []
    for station in _stations(report):
        stations.append(
            {
                "lat": _safe_float(station.get("lat")),
                "lon": _safe_float(station.get("lon")),
                "name": station.get("name"),
                "region": station.get("region"),
                "score": _safe_float(station.get("score")) or 0.0,
                "severity": station.get("severity") or "normal",
                "dew": _safe_float(station.get("max_dew_point_c")),
                "humidity": _safe_float(station.get("max_relative_humidity_pct")),
                "storm": _station_storm_score(station),
                "signals": station.get("signals", []),
            }
        )
    grid = [p.__dict__ for p in points]
    return json.dumps(stations, ensure_ascii=False), json.dumps(grid, ensure_ascii=False)


def _leaflet_base_script() -> str:
    return """
const map = L.map('map', { zoomControl: true }).setView([50.64, 4.66], 8);
const osm = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 18,
  attribution: '&copy; OpenStreetMap contributors'
}).addTo(map);
const belgiumBounds = [[49.45, 2.45], [51.55, 6.55]];
map.fitBounds(belgiumBounds);
"""


def _heat_layer_js(field: str, layer_name: str, radius: int = 18) -> str:
    return f"""
function colorFor_{field}(v) {{
  if (v === null || v === undefined || Number.isNaN(v)) return '#9aa8b8';
  if ('{field}' === 'humidity_pct') {{
    if (v >= 90) return '#5b2c83';
    if (v >= 80) return '#3f6fb5';
    if (v >= 70) return '#5aa6a6';
    if (v >= 60) return '#91c46c';
    return '#d6d77a';
  }}
  if ('{field}' === 'dew_point_c') {{
    if (v >= 23) return '#6f2c91';
    if (v >= 21) return '#d84c4c';
    if (v >= 18) return '#e89a3c';
    if (v >= 15) return '#d8c84c';
    return '#70a95d';
  }}
  if (v >= .78) return '#6f42c1';
  if (v >= .65) return '#d9534f';
  if (v >= .50) return '#e89432';
  if (v >= .35) return '#c8b847';
  return '#5da867';
}}
const {layer_name} = L.layerGroup();
grid.forEach(p => {{
  const v = p['{field}'];
  if (v === null || v === undefined) return;
  L.circleMarker([p.lat, p.lon], {{
    radius: {radius},
    stroke: false,
    fillColor: colorFor_{field}(v),
    fillOpacity: .44
  }}).bindPopup(`<strong>${{p.nearest_station || 'zone interpolée'}}</strong><br>{field}: ${{Number(v).toFixed(2)}}`).addTo({layer_name});
}});
"""


def _station_layer_js() -> str:
    colors = json.dumps(SEVERITY_COLORS)
    return f"""
const severityColors = {colors};
const stationLayer = L.layerGroup();
stations.forEach(s => {{
  const color = severityColors[s.severity] || '#5da867';
  const radius = 7 + Math.max(0, Math.min(1, s.score || 0)) * 12;
  L.circleMarker([s.lat, s.lon], {{
    radius,
    color: '#ffffff',
    weight: 1.5,
    fillColor: color,
    fillOpacity: .88
  }}).bindPopup(`<strong>${{s.name}}</strong><br>${{s.region || ''}}<br>Score: ${{Number(s.score || 0).toFixed(3)}}<br>Sévérité: ${{s.severity}}<br>Point de rosée: ${{s.dew ?? 'n/a'}} °C<br>Humidité: ${{s.humidity ?? 'n/a'}} %<br>Formation orageuse: ${{Number(s.storm || 0).toFixed(3)}}<br><small>${{(s.signals || []).join('<br>')}}</small>`).addTo(stationLayer);
}});
"""


def _rainviewer_js() -> str:
    return """
const radarLayerGroup = L.layerGroup();
async function loadRainViewer() {
  try {
    const response = await fetch('https://api.rainviewer.com/public/weather-maps.json');
    const data = await response.json();
    const frames = (data.radar && data.radar.past) ? data.radar.past : [];
    if (!frames.length) return;
    const frame = frames[frames.length - 1];
    const host = data.host || 'https://tilecache.rainviewer.com';
    const path = frame.path;
    const url = `${host}${path}/256/{z}/{x}/{y}/2/1_1.png`;
    L.tileLayer(url, {
      tileSize: 256,
      opacity: .58,
      attribution: 'Radar: RainViewer'
    }).addTo(radarLayerGroup);
  } catch (err) {
    console.warn('RainViewer radar unavailable', err);
  }
}
loadRainViewer();
"""


def render_radar_map_html(report: dict[str, Any], points: list[LayerPoint]) -> str:
    stations_js, grid_js = _js_data(report, points)
    body = f"""
<div class=\"panel\"><div class=\"legend\"><strong>Carte radar pluie</strong><br>
Couche radar RainViewer chargée côté navigateur, stations MeteoVoid en surcouche. Les tuiles radar ne sont pas archivées dans le rapport.</div>
<div class=\"note\">Sources : OpenStreetMap, RainViewer, données stations MeteoVoid.</div></div>
<div id=\"map\" class=\"map\"></div>
<script>
const stations = {stations_js};
const grid = {grid_js};
{_leaflet_base_script()}
{_station_layer_js()}
{_rainviewer_js()}
radarLayerGroup.addTo(map);
stationLayer.addTo(map);
L.control.layers({{'OpenStreetMap': osm}}, {{'Radar pluie RainViewer': radarLayerGroup, 'Stations MeteoVoid': stationLayer}}, {{collapsed:false}}).addTo(map);
</script>
"""
    return _html_shell(
        "MeteoVoid Belgique · Radar pluie",
        body,
        subtitle="Radar RainViewer en surcouche, avec stations de risque MeteoVoid.",
    )


def render_variable_map_html(
    report: dict[str, Any],
    points: list[LayerPoint],
    *,
    field: str,
    title: str,
    subtitle: str,
    legend: str,
) -> str:
    stations_js, grid_js = _js_data(report, points)
    body = f"""
<div class=\"panel\"><div class=\"legend\">{legend}</div>
<div class=\"note\">Interpolation IDW légère depuis les stations. À lire comme une aide visuelle, pas comme un champ officiel.</div></div>
<div id=\"map\" class=\"map\"></div>
<script>
const stations = {stations_js};
const grid = {grid_js};
{_leaflet_base_script()}
{_station_layer_js()}
{_heat_layer_js(field, 'heatLayer')}
heatLayer.addTo(map);
stationLayer.addTo(map);
L.control.layers({{'OpenStreetMap': osm}}, {{'Couche interpolée': heatLayer, 'Stations': stationLayer}}, {{collapsed:false}}).addTo(map);
</script>
"""
    return _html_shell(title, body, subtitle=subtitle)


def render_weather_layers_html(report: dict[str, Any], points: list[LayerPoint]) -> str:
    stations_js, grid_js = _js_data(report, points)
    body = f"""
<div class=\"panel\"><div class=\"controls\">
<button id=\"btnRadar\" class=\"active\">Radar pluie</button>
<button id=\"btnHumidity\" class=\"active\">Humidité</button>
<button id=\"btnDew\">Point de rosée</button>
<button id=\"btnStorm\" class=\"active\">Formation orageuse</button>
<button id=\"btnStations\" class=\"active\">Stations</button>
</div>
<div class=\"note\">Carte multi-couches : radar RainViewer, humidité, point de rosée, risque de formation orageuse et stations MeteoVoid.</div></div>
<div id=\"map\" class=\"map\"></div>
<script>
const stations = {stations_js};
const grid = {grid_js};
{_leaflet_base_script()}
{_station_layer_js()}
{_rainviewer_js()}
{_heat_layer_js('humidity_pct', 'humidityLayer', radius=14)}
{_heat_layer_js('dew_point_c', 'dewLayer', radius=14)}
{_heat_layer_js('storm_formation_score', 'stormLayer', radius=17)}
function toggle(btn, layer) {{
  const el = document.getElementById(btn);
  el.addEventListener('click', () => {{
    if (map.hasLayer(layer)) {{ map.removeLayer(layer); el.classList.remove('active'); }}
    else {{ layer.addTo(map); el.classList.add('active'); }}
  }});
}}
radarLayerGroup.addTo(map);
humidityLayer.addTo(map);
stormLayer.addTo(map);
stationLayer.addTo(map);
toggle('btnRadar', radarLayerGroup);
toggle('btnHumidity', humidityLayer);
toggle('btnDew', dewLayer);
toggle('btnStorm', stormLayer);
toggle('btnStations', stationLayer);
L.control.layers({{'OpenStreetMap': osm}}, {{'Radar pluie': radarLayerGroup, 'Humidité': humidityLayer, 'Point de rosée': dewLayer, 'Formation orageuse': stormLayer, 'Stations': stationLayer}}, {{collapsed:false}}).addTo(map);
</script>
"""
    return _html_shell(
        "MeteoVoid Belgique · Cartes météo avancées",
        body,
        subtitle="Radar, humidité, point de rosée et risque de formation orageuse dans une même interface.",
    )


def render_windy_compare_html(report: dict[str, Any]) -> str:
    generated = html.escape(str(report.get("generated_at") or ""))
    body = f"""
<div class=\"panel\">
<strong>Comparaison Windy optionnelle</strong>
<p>Cette page prépare l'intégration Windy sans exposer de clé API dans les artefacts GitHub.</p>
<p>Pour comparer visuellement, ouvrir Windy avec les couches utiles : pluie et orages, humidité, point de rosée, CAPE, rafales et pression.</p>
<p class=\"note\">Généré par MeteoVoid : {generated}. Le scoring MeteoVoid reste calculé depuis les données exportées dans les fichiers JSON/CSV.</p>
<div class=\"value-pill\">rain & thunder</div>
<div class=\"value-pill\">humidity</div>
<div class=\"value-pill\">dew point</div>
<div class=\"value-pill\">CAPE index</div>
<div class=\"value-pill\">gusts</div>
</div>
<div class=\"panel\">
<label for=\"key\"><strong>Clé Windy Map Forecast API, usage local seulement</strong></label><br>
<input id=\"key\" type=\"password\" placeholder=\"Coller une clé Windy ici localement\" style=\"width:100%;max-width:520px;padding:10px;border:1px solid #cbd7e7;border-radius:10px;margin:8px 0;\" />
<button onclick=\"initWindy()\">Charger la carte Windy</button>
<p class=\"note\">La clé n'est pas stockée par MeteoVoid. Elle est injectée uniquement dans cette session navigateur.</p>
</div>
<div id=\"windy\" class=\"map\"><div style=\"padding:24px;color:#697386;\">Carte Windy non chargée.</div></div>
<script>
function initWindy() {{
  const key = document.getElementById('key').value.trim();
  if (!key) {{ alert('Clé Windy requise pour charger la couche Windy.'); return; }}
  document.getElementById('windy').innerHTML = '';
  const opts = {{ key, verbose: false, lat: 50.64, lon: 4.66, zoom: 7, overlay: 'rain', product: 'ecmwf' }};
  const script = document.createElement('script');
  script.src = 'https://api.windy.com/assets/map-forecast/libBoot.js';
  script.onload = () => windyInit(opts, windyAPI => {{
    const {{ store }} = windyAPI;
    store.set('overlay', 'rain');
  }});
  document.body.appendChild(script);
}}
</script>
"""
    return _html_shell(
        "MeteoVoid Belgique · Comparaison Windy",
        body,
        subtitle="Point d'entrée optionnel pour comparer les couches MeteoVoid avec Windy sans dépendance obligatoire.",
    )


def write_weather_layer_outputs(report: dict[str, Any], out_dir: Path) -> dict[str, str]:
    points = build_weather_layer_grid(report)
    write_weather_layer_grid_csv(points, out_dir / "weather_layers_grid.csv")
    (out_dir / "convective_parameters.json").write_text(
        _json_dumps(convective_parameters_summary(report, points)), encoding="utf-8"
    )
    (out_dir / "belgium_weather_layers.html").write_text(
        render_weather_layers_html(report, points), encoding="utf-8"
    )
    (out_dir / "belgium_radar_map.html").write_text(
        render_radar_map_html(report, points), encoding="utf-8"
    )
    (out_dir / "belgium_humidity_map.html").write_text(
        render_variable_map_html(
            report,
            points,
            field="humidity_pct",
            title="MeteoVoid Belgique · Humidité",
            subtitle="Humidité relative interpolée depuis les stations de veille.",
            legend=(
                "<strong>Humidité relative</strong><br>"
                "Couleurs froides/violettes : humidité très élevée. "
                "À croiser avec point de rosée, CAPE et déclencheurs orageux."
            ),
        ),
        encoding="utf-8",
    )
    (out_dir / "belgium_dewpoint_map.html").write_text(
        render_variable_map_html(
            report,
            points,
            field="dew_point_c",
            title="MeteoVoid Belgique · Point de rosée",
            subtitle="Point de rosée interpolé pour repérer les masses d'air lourdes.",
            legend=(
                "<strong>Point de rosée</strong><br>"
                "Au-delà de 18 °C, l'air devient humide. Au-delà de 21 °C, le potentiel convectif augmente fortement si un forçage arrive."
            ),
        ),
        encoding="utf-8",
    )
    (out_dir / "belgium_storm_formation_map.html").write_text(
        render_variable_map_html(
            report,
            points,
            field="storm_formation_score",
            title="MeteoVoid Belgique · Formation orageuse",
            subtitle="Indice dérivé chaleur, humidité, précipitations, codes météo, rafales et pression.",
            legend=(
                "<strong>Indice de formation orageuse</strong><br>"
                "Score dérivé MeteoVoid. Il indique une zone favorable, pas une cellule orageuse observée."
            ),
        ),
        encoding="utf-8",
    )
    (out_dir / "belgium_windy_compare.html").write_text(
        render_windy_compare_html(report), encoding="utf-8"
    )
    return {
        "weather_layers_grid": "weather_layers_grid.csv",
        "convective_parameters": "convective_parameters.json",
        "weather_layers_html": "belgium_weather_layers.html",
        "radar_map_html": "belgium_radar_map.html",
        "humidity_map_html": "belgium_humidity_map.html",
        "dewpoint_map_html": "belgium_dewpoint_map.html",
        "storm_formation_map_html": "belgium_storm_formation_map.html",
        "windy_compare_html": "belgium_windy_compare.html",
    }
