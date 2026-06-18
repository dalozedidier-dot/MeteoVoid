from __future__ import annotations

import csv
import html
import json
import math
from pathlib import Path
from statistics import mean
from typing import Any

INFORMATION_GRAPH_OUTPUTS = {
    "information_graph_json": "information_graph_summary.json",
    "information_graph_edges_csv": "information_graph_edges.csv",
    "information_graph_html": "information_graph.html",
}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    if math.isnan(value) or math.isinf(value):
        return 0.0
    return max(low, min(high, value))


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1 - a)))


def _series(station: dict[str, Any], key: str = "score") -> list[float]:
    rows = station.get("hourly_risk")
    if not isinstance(rows, list):
        return []
    return [_as_float(row.get(key)) for row in rows if isinstance(row, dict)]


def _corr(x: list[float], y: list[float]) -> float:
    n = min(len(x), len(y))
    if n < 4:
        return 0.0
    x = x[:n]
    y = y[:n]
    mx = mean(x)
    my = mean(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y, strict=False))
    denx = math.sqrt(sum((a - mx) ** 2 for a in x))
    deny = math.sqrt(sum((b - my) ** 2 for b in y))
    if denx == 0 or deny == 0:
        return 0.0
    return max(-1.0, min(1.0, num / (denx * deny)))


def _best_lag_edge(
    source: dict[str, Any], target: dict[str, Any], max_lag: int
) -> dict[str, Any] | None:
    xs = _series(source)
    ys = _series(target)
    if len(xs) < max_lag + 6 or len(ys) < max_lag + 6:
        return None
    best_lag = 0
    best_corr = -1.0
    for lag in range(1, max_lag + 1):
        corr = _corr(xs[:-lag], ys[lag:])
        if corr > best_corr:
            best_corr = corr
            best_lag = lag
    if best_corr < 0.25:
        return None
    _corr(xs[:-1], xs[1:])
    tgt_var = _corr(ys[:-1], ys[1:])
    te_proxy = _clip((best_corr - max(0.0, tgt_var) * 0.35) * 1.15)
    distance = _haversine_km(
        _as_float(source.get("lat")),
        _as_float(source.get("lon")),
        _as_float(target.get("lat")),
        _as_float(target.get("lon")),
    )
    distance_weight = _clip(1.0 - distance / 320.0)
    weight = _clip(0.65 * best_corr + 0.25 * te_proxy + 0.10 * distance_weight)
    return {
        "source_id": source.get("station_id"),
        "source_name": source.get("name"),
        "target_id": target.get("station_id"),
        "target_name": target.get("name"),
        "lag_hours": best_lag,
        "lagged_correlation": round(best_corr, 6),
        "transfer_entropy_proxy": round(te_proxy, 6),
        "distance_km": round(distance, 3),
        "information_weight": round(weight, 6),
    }


def build_information_graph(report: dict[str, Any], max_lag: int = 4) -> dict[str, Any]:
    stations = [s for s in report.get("stations", []) if isinstance(s, dict) and s.get("source_ok")]
    edges: list[dict[str, Any]] = []
    for source in stations:
        for target in stations:
            if source is target:
                continue
            edge = _best_lag_edge(source, target, max_lag=max_lag)
            if edge is not None:
                edges.append(edge)
    edges = sorted(edges, key=lambda row: _as_float(row.get("information_weight")), reverse=True)[
        :80
    ]
    in_strength: dict[str, float] = {}
    out_strength: dict[str, float] = {}
    for edge in edges:
        weight = _as_float(edge.get("information_weight"))
        src = str(edge.get("source_id"))
        tgt = str(edge.get("target_id"))
        out_strength[src] = out_strength.get(src, 0.0) + weight
        in_strength[tgt] = in_strength.get(tgt, 0.0) + weight
    corridor_score = _clip(
        mean([_as_float(e.get("information_weight")) for e in edges[:10]]) if edges else 0.0
    )
    return {
        "generated_at": report.get("generated_at"),
        "run_id": report.get("run_id"),
        "method": "lagged_correlation_transfer_entropy_proxy",
        "summary": {
            "edge_count": len(edges),
            "station_count": len(stations),
            "information_corridor_score": round(corridor_score, 6),
            "top_upstream_station": (
                max(out_strength, key=out_strength.get) if out_strength else None
            ),
            "top_downstream_station": (
                max(in_strength, key=in_strength.get) if in_strength else None
            ),
            "interpretation": (
                "information_corridor_detected"
                if corridor_score >= 0.55
                else "weak_or_fragmented_information_flow"
            ),
        },
        "edges": edges,
    }


def _render_html(data: dict[str, Any]) -> str:
    summary = data.get("summary", {}) if isinstance(data.get("summary"), dict) else {}
    edges = data.get("edges", []) if isinstance(data.get("edges"), list) else []
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(edge.get('source_name') or edge.get('source_id') or ''))}</td>"
        f"<td>→</td>"
        f"<td>{html.escape(str(edge.get('target_name') or edge.get('target_id') or ''))}</td>"
        f"<td>{html.escape(str(edge.get('lag_hours')))}</td>"
        f"<td>{_as_float(edge.get('lagged_correlation')):.3f}</td>"
        f"<td>{_as_float(edge.get('transfer_entropy_proxy')):.3f}</td>"
        f"<td>{_as_float(edge.get('information_weight')):.3f}</td>"
        "</tr>"
        for edge in edges[:25]
    )
    return f"""<!doctype html><html lang='fr'><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width, initial-scale=1'/>
<title>MeteoVoid Belgique · Graphe informationnel</title><style>
body{{margin:0;font-family:Inter,Segoe UI,Arial,sans-serif;background:#eef3f8;color:#0d1b2e}}header{{background:#173b66;color:#fff;padding:22px 26px}}
.wrap{{padding:22px;max-width:1280px;margin:auto}}.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}}.card{{background:#fff;border:1px solid #d9e3ef;border-radius:18px;padding:18px;box-shadow:0 14px 32px rgba(20,42,69,.08)}}
.big{{font-size:28px;font-weight:900;display:block;margin-top:8px}}small{{color:#66758a;text-transform:uppercase;font-weight:800;letter-spacing:.08em}}
table{{margin-top:18px;width:100%;border-collapse:collapse;background:#fff;border-radius:18px;overflow:hidden}}th,td{{padding:10px;border-bottom:1px solid #e2ebf5;text-align:left}}th{{color:#66758a;text-transform:uppercase;font-size:12px}}
.note{{background:#eef6ff;border-left:5px solid #245b91;border-radius:14px;padding:14px;margin:18px 0}}@media(max-width:900px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><header><h1>MeteoVoid Belgique · Graphe informationnel</h1><p>Arêtes apprises par corrélation retardée et proxy d'entropie de transfert.</p></header><div class='wrap'>
<div class='grid'>
<div class='card'><small>Score corridor</small><span class='big'>{_as_float(summary.get("information_corridor_score")):.3f}</span></div>
<div class='card'><small>Arêtes</small><span class='big'>{html.escape(str(summary.get("edge_count", 0)))}</span></div>
<div class='card'><small>Amont dominant</small><span class='big' style='font-size:18px'>{html.escape(str(summary.get("top_upstream_station") or "n/a"))}</span></div>
<div class='card'><small>Aval dominant</small><span class='big' style='font-size:18px'>{html.escape(str(summary.get("top_downstream_station") or "n/a"))}</span></div>
</div><div class='note'><strong>Lecture.</strong> Ce graphe mesure les liens directionnels apparents entre stations. Il ne prouve pas une causalité physique, mais signale les corridors d'information météo à vérifier avec le flux, radar et satellite.</div>
<table><thead><tr><th>Source</th><th></th><th>Cible</th><th>Lag h</th><th>Corr.</th><th>TE proxy</th><th>Poids</th></tr></thead><tbody>{rows}</tbody></table>
</div></body></html>"""


def write_information_graph_outputs(report: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    data = build_information_graph(report)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "information_graph_summary.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    fields = [
        "source_id",
        "source_name",
        "target_id",
        "target_name",
        "lag_hours",
        "lagged_correlation",
        "transfer_entropy_proxy",
        "distance_km",
        "information_weight",
    ]
    with (out_dir / "information_graph_edges.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for edge in data.get("edges", []):
            writer.writerow({field: edge.get(field, "") for field in fields})
    (out_dir / "information_graph.html").write_text(_render_html(data), encoding="utf-8")
    return data
