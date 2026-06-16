from __future__ import annotations

import csv
import html
import json
import math
from pathlib import Path
from statistics import mean, variance
from typing import Any

EARLY_WARNING_OUTPUTS = {
    "early_warning_json": "early_warning_signals.json",
    "early_warning_station_csv": "early_warning_by_station.csv",
    "early_warning_network_csv": "early_warning_network.csv",
    "early_warning_dashboard_html": "early_warning_dashboard.html",
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


def _lag1_autocorrelation(values: list[float]) -> float:
    if len(values) < 3:
        return 0.0
    x = values[:-1]
    y = values[1:]
    mx = mean(x)
    my = mean(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    den_x = math.sqrt(sum((a - mx) ** 2 for a in x))
    den_y = math.sqrt(sum((b - my) ** 2 for b in y))
    if den_x == 0 or den_y == 0:
        return 0.0
    return _clip(num / (den_x * den_y), -1.0, 1.0)


def _skewness(values: list[float]) -> float:
    if len(values) < 3:
        return 0.0
    m = mean(values)
    var = sum((v - m) ** 2 for v in values) / len(values)
    if var <= 1e-12:
        return 0.0
    sd = math.sqrt(var)
    return sum(((v - m) / sd) ** 3 for v in values) / len(values)


def _slope(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    n = len(values)
    xs = list(range(n))
    mx = mean(xs)
    my = mean(values)
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in zip(xs, values)) / den


def _flickering(values: list[float], threshold: float = 0.55) -> float:
    if len(values) < 2:
        return 0.0
    states = [v >= threshold for v in values]
    flips = sum(1 for a, b in zip(states, states[1:]) if a != b)
    return flips / max(1, len(states) - 1)


def _window_values(station: dict[str, Any], key: str, max_points: int = 36) -> list[float]:
    rows = station.get("hourly_risk")
    if not isinstance(rows, list):
        return []
    values = [_as_float(row.get(key)) for row in rows if isinstance(row, dict)]
    return values[-max_points:]


def _station_ews(station: dict[str, Any]) -> dict[str, Any]:
    score_values = _window_values(station, "score")
    dew_values = _window_values(station, "dew_point_c")
    temp_values = _window_values(station, "temperature_c")
    wind_values = _window_values(station, "wind_gust_ms")
    precip_values = _window_values(station, "precip_probability_pct")

    values = score_values if score_values else [_as_float(station.get("score"))]
    recent = values[-12:] if len(values) >= 12 else values
    previous = values[-24:-12] if len(values) >= 24 else values[: max(1, len(values) // 2)]

    recent_var = variance(recent) if len(recent) > 1 else 0.0
    previous_var = variance(previous) if len(previous) > 1 else 0.0
    variance_growth = (recent_var + 1e-6) / (previous_var + 1e-6)
    autocorr = _lag1_autocorrelation(values)
    skew = _skewness(values)
    flicker = _flickering(values)
    score_slope = _slope(values[-18:] if len(values) >= 18 else values)

    dew_slope = _slope(dew_values[-18:] if len(dew_values) >= 18 else dew_values)
    temp_slope = _slope(temp_values[-18:] if len(temp_values) >= 18 else temp_values)
    wind_slope = _slope(wind_values[-18:] if len(wind_values) >= 18 else wind_values)
    precip_slope = _slope(precip_values[-18:] if len(precip_values) >= 18 else precip_values)

    critical_slowing_score = _clip((autocorr + 1.0) / 2.0)
    variance_score = _clip(math.log1p(max(0.0, variance_growth - 1.0)) / math.log(5.0))
    asymmetry_score = _clip(abs(skew) / 2.0)
    flickering_score = _clip(flicker * 2.0)
    trend_score = _clip(max(0.0, score_slope) * 12.0)
    moisture_trend_score = _clip(max(0.0, dew_slope) / 0.35)
    forcing_proxy_score = _clip(max(0.0, precip_slope) / 8.0 + max(0.0, wind_slope) / 3.0)

    ews_score = _clip(
        0.22 * critical_slowing_score
        + 0.18 * variance_score
        + 0.13 * asymmetry_score
        + 0.15 * flickering_score
        + 0.17 * trend_score
        + 0.10 * moisture_trend_score
        + 0.05 * forcing_proxy_score
    )
    if ews_score >= 0.72:
        phase = "critical_transition_watch"
    elif ews_score >= 0.55:
        phase = "destabilizing"
    elif ews_score >= 0.35:
        phase = "weak_signal"
    else:
        phase = "quiet"

    return {
        "station_id": station.get("station_id"),
        "name": station.get("name"),
        "region": station.get("region"),
        "score": round(_as_float(station.get("score")), 6),
        "severity": station.get("severity"),
        "early_warning_score": round(ews_score, 6),
        "phase": phase,
        "lag1_autocorrelation": round(autocorr, 6),
        "variance_growth_ratio": round(variance_growth, 6),
        "skewness": round(skew, 6),
        "flickering_rate": round(flicker, 6),
        "score_slope_per_hour": round(score_slope, 6),
        "dew_point_slope_per_hour": round(dew_slope, 6),
        "precip_probability_slope_per_hour": round(precip_slope, 6),
        "wind_gust_slope_per_hour": round(wind_slope, 6),
    }


def _network_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [_as_float(row.get("early_warning_score")) for row in rows]
    if not scores:
        return {
            "network_early_warning_score": 0.0,
            "critical_station_count": 0,
            "destabilizing_station_count": 0,
            "interpretation": "no_data",
        }
    critical = sum(1 for row in rows if row.get("phase") == "critical_transition_watch")
    destabilizing = sum(1 for row in rows if row.get("phase") in {"critical_transition_watch", "destabilizing"})
    top = max(scores)
    avg = mean(scores)
    concentration = critical / max(1, len(rows))
    network_score = _clip(0.45 * top + 0.35 * avg + 0.20 * concentration)
    if network_score >= 0.70:
        interpretation = "network_transition_watch"
    elif network_score >= 0.50:
        interpretation = "network_destabilizing"
    elif network_score >= 0.30:
        interpretation = "weak_network_signal"
    else:
        interpretation = "quiet_network"
    return {
        "network_early_warning_score": round(network_score, 6),
        "max_station_early_warning_score": round(top, 6),
        "mean_station_early_warning_score": round(avg, 6),
        "critical_station_count": critical,
        "destabilizing_station_count": destabilizing,
        "station_count": len(rows),
        "interpretation": interpretation,
    }


def build_early_warning_report(report: dict[str, Any]) -> dict[str, Any]:
    stations = [s for s in report.get("stations", []) if isinstance(s, dict) and s.get("source_ok")]
    rows = [_station_ews(station) for station in stations]
    summary = _network_summary(rows)
    return {
        "generated_at": report.get("generated_at"),
        "run_id": report.get("run_id"),
        "method": "rolling_early_warning_signals",
        "summary": summary,
        "stations": sorted(rows, key=lambda row: _as_float(row.get("early_warning_score")), reverse=True),
        "notes": [
            "Indicateurs génériques de transition critique : autocorrélation lag-1, variance, asymétrie et flickering.",
            "Ces signaux ne constituent pas une alerte officielle. Ils mesurent une perte de stabilité fonctionnelle dans les séries MeteoVoid.",
        ],
    }


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    fields = [
        "station_id",
        "name",
        "region",
        "severity",
        "score",
        "early_warning_score",
        "phase",
        "lag1_autocorrelation",
        "variance_growth_ratio",
        "skewness",
        "flickering_rate",
        "score_slope_per_hour",
        "dew_point_slope_per_hour",
        "precip_probability_slope_per_hour",
        "wind_gust_slope_per_hour",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _render_dashboard(data: dict[str, Any]) -> str:
    summary = data.get("summary", {}) if isinstance(data.get("summary"), dict) else {}
    rows = data.get("stations", []) if isinstance(data.get("stations"), list) else []
    top_rows = rows[:10]
    table = "".join(
        "<tr>"
        f"<td><strong>{html.escape(str(row.get('name') or row.get('station_id') or ''))}</strong></td>"
        f"<td>{html.escape(str(row.get('phase') or ''))}</td>"
        f"<td>{_as_float(row.get('early_warning_score')):.3f}</td>"
        f"<td>{_as_float(row.get('lag1_autocorrelation')):.3f}</td>"
        f"<td>{_as_float(row.get('variance_growth_ratio')):.2f}</td>"
        f"<td>{_as_float(row.get('flickering_rate')):.3f}</td>"
        "</tr>"
        for row in top_rows
    )
    return f"""<!doctype html>
<html lang='fr'>
<head>
<meta charset='utf-8' />
<meta name='viewport' content='width=device-width, initial-scale=1' />
<title>MeteoVoid Belgique · Signaux précoces</title>
<style>
body{{margin:0;font-family:Inter,Segoe UI,Arial,sans-serif;background:#eef3f8;color:#0d1b2e}}
header{{background:#173b66;color:#fff;padding:22px 26px}}h1{{margin:0;font-size:28px}}.wrap{{padding:22px;max-width:1280px;margin:auto}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}}.card{{background:#fff;border:1px solid #d9e3ef;border-radius:18px;padding:18px;box-shadow:0 14px 32px rgba(20,42,69,.08)}}
.card small{{color:#66758a;text-transform:uppercase;letter-spacing:.08em;font-weight:800}}.big{{font-size:30px;font-weight:900;margin-top:8px;display:block}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:18px;overflow:hidden}}th,td{{padding:11px;border-bottom:1px solid #e2ebf5;text-align:left}}th{{color:#66758a;font-size:12px;text-transform:uppercase}}
.note{{background:#fff7e8;border-left:5px solid #e28a26;border-radius:14px;padding:14px 16px;margin:18px 0}}
@media(max-width:900px){{.grid{{grid-template-columns:1fr}}}}
</style>
</head><body>
<header><h1>MeteoVoid Belgique · Signaux précoces de transition</h1><p>Autocorrélation, variance, asymétrie et flickering sur les séries de risque.</p></header>
<div class='wrap'>
<div class='grid'>
  <div class='card'><small>Score réseau</small><span class='big'>{_as_float(summary.get('network_early_warning_score')):.3f}</span></div>
  <div class='card'><small>Stations critiques</small><span class='big'>{html.escape(str(summary.get('critical_station_count', 0)))}</span></div>
  <div class='card'><small>Stations déstabilisées</small><span class='big'>{html.escape(str(summary.get('destabilizing_station_count', 0)))}</span></div>
  <div class='card'><small>Lecture</small><span class='big' style='font-size:20px'>{html.escape(str(summary.get('interpretation','n/a')))}</span></div>
</div>
<div class='note'><strong>Lecture ORI-C.</strong> Ces indicateurs visent à repérer une perte de stabilité fonctionnelle avant la bascule. Ils ne remplacent pas les avertissements officiels.</div>
<table><thead><tr><th>Station</th><th>Phase</th><th>Score EWS</th><th>ACF lag-1</th><th>Variance ×</th><th>Flickering</th></tr></thead><tbody>{table}</tbody></table>
</div></body></html>"""


def write_early_warning_outputs(report: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    data = build_early_warning_report(report)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "early_warning_signals.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    _write_csv(data.get("stations", []), out_dir / "early_warning_by_station.csv")
    summary = data.get("summary", {}) if isinstance(data.get("summary"), dict) else {}
    with (out_dir / "early_warning_network.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=sorted(summary.keys()))
        writer.writeheader()
        writer.writerow(summary)
    (out_dir / "early_warning_dashboard.html").write_text(_render_dashboard(data), encoding="utf-8")
    return data
