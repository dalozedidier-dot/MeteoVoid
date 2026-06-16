from __future__ import annotations

import csv
import html
import json
import math
from pathlib import Path
from typing import Any

UPSTREAM_GRAPH_OUTPUTS = {
    "upstream_graph_summary": "upstream_graph_summary.json",
    "upstream_graph_edges_csv": "upstream_graph_edges.csv",
    "upstream_graph_html": "upstream_graph.html",
}

SEVERITY_RANK = {"normal": 0, "watch": 1, "medium": 2, "high": 3, "alert": 4}
SEVERITY_COLORS = {
    "normal": "#4caf50",
    "watch": "#c9b83f",
    "medium": "#f39c34",
    "high": "#e74c3c",
    "alert": "#7e3fd8",
}


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius_km * math.asin(min(1.0, math.sqrt(a)))


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    y = math.sin(dlambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def _station_nodes(report: dict[str, Any]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for row in report.get("stations", []):
        if not isinstance(row, dict):
            continue
        lat = _safe_float(row.get("lat"))
        lon = _safe_float(row.get("lon"))
        if lat is None or lon is None:
            continue
        score = _safe_float(row.get("score")) or 0.0
        severity = str(row.get("severity") or "normal")
        station_id = str(row.get("station_id") or row.get("id") or row.get("name") or "unknown")
        nodes.append(
            {
                "station_id": station_id,
                "name": str(row.get("name") or station_id),
                "lat": lat,
                "lon": lon,
                "score": round(score, 4),
                "severity": severity,
                "rank": SEVERITY_RANK.get(severity, 0),
                "worst_time": row.get("worst_time"),
                "signals": row.get("signals", []),
            }
        )
    return nodes


def _build_edges(nodes: list[dict[str, Any]], max_distance_km: float = 135.0) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for i, left in enumerate(nodes):
        for right in nodes[i + 1 :]:
            dist = _haversine_km(left["lat"], left["lon"], right["lat"], right["lon"])
            if dist > max_distance_km:
                continue
            bearing_lr = _bearing_deg(left["lat"], left["lon"], right["lat"], right["lon"])
            gradient = float(right["score"]) - float(left["score"])
            edges.append(
                {
                    "source": left["station_id"],
                    "target": right["station_id"],
                    "source_name": left["name"],
                    "target_name": right["name"],
                    "distance_km": round(dist, 2),
                    "bearing_deg": round(bearing_lr, 1),
                    "score_gradient": round(gradient, 4),
                    "coherence_weight": round((1.0 - min(dist / max_distance_km, 1.0)) * (1.0 - abs(gradient)), 4),
                }
            )
    return edges


def _graph_metrics(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    high_nodes = [n for n in nodes if n["rank"] >= 3]
    n = len(nodes)
    possible_edges = max(n * (n - 1) / 2, 1)
    density = len(edges) / possible_edges
    high_ratio = len(high_nodes) / max(n, 1)
    avg_score = sum(float(n["score"]) for n in nodes) / max(n, 1)
    max_score = max((float(n["score"]) for n in nodes), default=0.0)

    component_count: int | None = None
    largest_component_size: int | None = None
    betweenness_top: list[dict[str, Any]] = []
    try:
        import networkx as nx  # type: ignore[import-untyped]

        graph = nx.Graph()
        for node in nodes:
            graph.add_node(node["station_id"], **node)
        for edge in edges:
            graph.add_edge(edge["source"], edge["target"], weight=edge["coherence_weight"])
        components = list(nx.connected_components(graph))
        component_count = len(components)
        largest_component_size = max((len(c) for c in components), default=0)
        centrality = nx.betweenness_centrality(graph, normalized=True)
        name_by_id = {n["station_id"]: n["name"] for n in nodes}
        betweenness_top = [
            {"station_id": sid, "name": name_by_id.get(sid, sid), "betweenness": round(value, 4)}
            for sid, value in sorted(centrality.items(), key=lambda item: item[1], reverse=True)[:5]
        ]
    except ModuleNotFoundError:
        component_count = None
        largest_component_size = None

    upstream_coherence_score = min(1.0, 0.45 * avg_score + 0.25 * max_score + 0.20 * density + 0.10 * high_ratio)
    return {
        "node_count": n,
        "edge_count": len(edges),
        "graph_density": round(density, 4),
        "high_or_alert_node_count": len(high_nodes),
        "high_or_alert_ratio": round(high_ratio, 4),
        "average_station_score": round(avg_score, 4),
        "max_station_score": round(max_score, 4),
        "connected_component_count": component_count,
        "largest_component_size": largest_component_size,
        "top_betweenness_nodes": betweenness_top,
        "upstream_coherence_score": round(upstream_coherence_score, 4),
        "interpretation": _interpret(upstream_coherence_score, high_ratio, density),
        "method_note": (
            "Prototype graph-based layer: stations are linked by distance to reveal contiguous risk corridors. "
            "It is not yet a true wind-vector propagation model."
        ),
    }


def _interpret(score: float, high_ratio: float, density: float) -> str:
    if score >= 0.70 and high_ratio >= 0.35:
        return "corridor de risque cohérent : plusieurs stations sensibles sont connectées"
    if score >= 0.50:
        return "signal spatial organisé mais encore à confirmer par les sources dynamiques"
    if density < 0.15:
        return "graphe trop fragmenté pour parler de corridor organisé"
    return "signal spatial faible ou dispersé"


def _write_edges_csv(edges: list[dict[str, Any]], path: Path) -> None:
    fieldnames = [
        "source",
        "target",
        "source_name",
        "target_name",
        "distance_km",
        "bearing_deg",
        "score_gradient",
        "coherence_weight",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(edges)


def _render_graph_html(report: dict[str, Any], nodes: list[dict[str, Any]], edges: list[dict[str, Any]], metrics: dict[str, Any]) -> str:
    nodes_json = json.dumps(nodes, ensure_ascii=False)
    edges_json = json.dumps(edges, ensure_ascii=False)
    title = "MeteoVoid Belgique · Graphe amont"
    metric = metrics.get("upstream_coherence_score", 0)
    interp = html.escape(str(metrics.get("interpretation", "")))
    generated_at = html.escape(str(report.get("generated_at") or ""))
    return f'''<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{html.escape(title)}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<style>
body {{ margin:0; font-family: Inter, system-ui, -apple-system, Segoe UI, sans-serif; background:#eef3f8; color:#0b1f3a; }}
header {{ background:#123a63; color:white; padding:18px 24px; }}
header h1 {{ margin:0; font-size:26px; }}
header p {{ margin:6px 0 0; opacity:.88; }}
.panel {{ margin:16px; padding:16px; border-radius:16px; background:white; box-shadow:0 8px 28px rgba(15,35,70,.08); }}
.kpis {{ display:grid; grid-template-columns:repeat(4,minmax(160px,1fr)); gap:12px; }}
.kpi {{ border:1px solid #dbe6f2; border-radius:14px; padding:14px; }}
.kpi small {{ display:block; color:#667995; font-weight:700; text-transform:uppercase; letter-spacing:.04em; }}
.kpi strong {{ display:block; font-size:28px; margin-top:4px; }}
#map {{ height:70vh; min-height:560px; border-radius:18px; border:1px solid #dbe6f2; }}
.legend {{ background:white; padding:10px 12px; border-radius:12px; box-shadow:0 4px 18px rgba(0,0,0,.15); line-height:1.7; }}
.legend span {{ display:inline-block; width:12px; height:12px; border-radius:999px; margin-right:6px; }}
</style>
</head>
<body>
<header><h1>{html.escape(title)}</h1><p>Lecture expérimentale des corridors spatiaux de risque. Généré : {generated_at}</p></header>
<section class="panel kpis">
  <div class="kpi"><small>Score graphe</small><strong>{metric}</strong></div>
  <div class="kpi"><small>Nœuds</small><strong>{metrics.get('node_count')}</strong></div>
  <div class="kpi"><small>Liens</small><strong>{metrics.get('edge_count')}</strong></div>
  <div class="kpi"><small>Lecture</small><p>{interp}</p></div>
</section>
<section class="panel"><div id="map"></div></section>
<section class="panel"><strong>Note :</strong> ce graphe relie les stations proches pour visualiser des corridors de cohérence. Il ne remplace pas encore un modèle de propagation basé sur les vents, le cisaillement ou les champs NWP.</section>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const nodes = {nodes_json};
const edges = {edges_json};
const colors = {json.dumps(SEVERITY_COLORS)};
const map = L.map('map').setView([50.65, 4.55], 7);
L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{ attribution:'© OpenStreetMap contributors', maxZoom: 18 }}).addTo(map);
const byId = Object.fromEntries(nodes.map(n => [n.station_id, n]));
for (const e of edges) {{
  const a = byId[e.source], b = byId[e.target];
  if (!a || !b) continue;
  const opacity = Math.max(0.18, Math.min(0.75, e.coherence_weight || 0.25));
  L.polyline([[a.lat,a.lon],[b.lat,b.lon]], {{ color:'#123a63', weight:1.2 + 3*opacity, opacity }}).addTo(map)
    .bindPopup(`${{a.name}} → ${{b.name}}<br>Distance: ${{e.distance_km}} km<br>Poids: ${{e.coherence_weight}}`);
}}
for (const n of nodes) {{
  const radius = 7 + 16 * Math.max(0, Math.min(1, n.score || 0));
  L.circleMarker([n.lat,n.lon], {{ radius, color:'#ffffff', weight:2, fillColor:colors[n.severity] || '#666', fillOpacity:.86 }})
    .addTo(map)
    .bindPopup(`<strong>${{n.name}}</strong><br>Score: ${{n.score}}<br>Sévérité: ${{n.severity}}<br>${{n.worst_time || ''}}`);
}}
const legend = L.control({{position:'bottomleft'}});
legend.onAdd = function() {{
  const div = L.DomUtil.create('div','legend');
  div.innerHTML = '<strong>Sévérité</strong><br>' + Object.entries(colors).map(([k,v]) => `<span style="background:${{v}}"></span>${{k}}`).join('<br>');
  return div;
}};
legend.addTo(map);
</script>
</body>
</html>
'''


def write_upstream_graph_outputs(report: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    nodes = _station_nodes(report)
    edges = _build_edges(nodes)
    metrics = _graph_metrics(nodes, edges)
    summary = {
        "generated_at": report.get("generated_at"),
        "source": "risk_by_station graph adjacency",
        "metrics": metrics,
        "nodes": nodes,
    }
    (out_dir / UPSTREAM_GRAPH_OUTPUTS["upstream_graph_summary"]).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_edges_csv(edges, out_dir / UPSTREAM_GRAPH_OUTPUTS["upstream_graph_edges_csv"])
    (out_dir / UPSTREAM_GRAPH_OUTPUTS["upstream_graph_html"]).write_text(
        _render_graph_html(report, nodes, edges, metrics),
        encoding="utf-8",
    )
    return summary
