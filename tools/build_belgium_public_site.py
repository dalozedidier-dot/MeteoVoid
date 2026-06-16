from __future__ import annotations

import argparse
import html
import json
import shutil
from pathlib import Path
from typing import Any

PUBLIC_FILES = [
    "belgium_alert_dashboard.html",
    "convective_transition_dashboard.html",
    "belgium_alert_map.html",
    "belgium_weather_layers.html",
    "belgium_radar_map.html",
    "belgium_humidity_map.html",
    "belgium_dewpoint_map.html",
    "belgium_storm_formation_map.html",
    "belgium_province_map.html",
    "belgium_alert_heatmap.html",
    "belgium_windy_compare.html",
    "belgium_alert_report.md",
    "convective_transition_report.md",
    "risk_by_station.csv",
    "risk_timeline.csv",
    "weather_layers_grid.csv",
    "province_summary.csv",
    "belgium_alert_report.json",
    "alert_state.json",
    "source_status.json",
    "official_sources_status.json",
    "nowcast_status.json",
    "convective_transition_report.json",
    "manifest.json",
]

FRAME_OPTIONS = [
    ("Synthèse", "belgium_alert_dashboard.html"),
    ("Transition convective", "convective_transition_dashboard.html"),
    ("Carte risque", "belgium_alert_map.html"),
    ("Cartes avancées", "belgium_weather_layers.html"),
    ("Radar", "belgium_radar_map.html"),
    ("Humidité", "belgium_humidity_map.html"),
    ("Point de rosée", "belgium_dewpoint_map.html"),
    ("Formation orageuse", "belgium_storm_formation_map.html"),
    ("Provinces", "belgium_province_map.html"),
]


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _fmt(value: Any, default: str = "n/a") -> str:
    if value is None or value == "":
        return default
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def _severity_class(value: str) -> str:
    value = (value or "normal").lower()
    if value in {"alert", "red", "void_collapse"}:
        return "sev-alert"
    if value in {"high", "orange", "transition_probable"}:
        return "sev-high"
    if value in {"medium", "level1", "latent_unstable"}:
        return "sev-medium"
    if value in {"watch", "yellow"}:
        return "sev-watch"
    return "sev-normal"


def _top_stations(report: dict[str, Any], limit: int = 7) -> list[dict[str, Any]]:
    stations = report.get("stations")
    if not isinstance(stations, list):
        return []
    usable = [s for s in stations if isinstance(s, dict)]
    return sorted(usable, key=lambda x: float(x.get("score") or 0), reverse=True)[:limit]


def _top_transition(transition: dict[str, Any]) -> list[dict[str, Any]]:
    rows = transition.get("stations")
    if not isinstance(rows, list):
        return []
    usable = [r for r in rows if isinstance(r, dict)]
    return sorted(usable, key=lambda x: float(x.get("void_collapse_signal") or 0), reverse=True)[:5]


def _copy_outputs(report_dir: Path, site_dir: Path) -> Path:
    latest_dir = site_dir / "reports" / "latest"
    latest_dir.mkdir(parents=True, exist_ok=True)
    for name in PUBLIC_FILES:
        src = report_dir / name
        if src.exists() and src.is_file():
            shutil.copy2(src, latest_dir / name)
    return latest_dir


def _button_nav(prefix: str = "reports/latest/") -> str:
    buttons = []
    first = True
    for label, target in FRAME_OPTIONS:
        buttons.append(
            "<button class='tab {active}' data-target='{target}'>{label}</button>".format(
                active="active" if first else "",
                target=html.escape(prefix + target),
                label=html.escape(label),
            )
        )
        first = False
    return "\n".join(buttons)


def _station_table(report: dict[str, Any]) -> str:
    rows = []
    for station in _top_stations(report):
        severity = str(station.get("severity") or "normal")
        rows.append(
            "<tr>"
            f"<td><strong>{html.escape(str(station.get('name') or station.get('station_id') or ''))}</strong></td>"
            f"<td><span class='badge {_severity_class(severity)}'>{html.escape(severity)}</span></td>"
            f"<td>{html.escape(_fmt(station.get('score')))}</td>"
            f"<td>{html.escape(str(station.get('sensitive_hour') or 'n/a'))}</td>"
            f"<td>{html.escape('; '.join(station.get('signals') or [])[:220])}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _transition_cards(transition: dict[str, Any]) -> str:
    summary = transition.get("summary") if isinstance(transition.get("summary"), dict) else {}
    cards = [
        ("Cohérence convective", summary.get("max_convective_coherence_index")),
        ("Signal void collapse", summary.get("max_void_collapse_signal")),
        ("Pression de transition", summary.get("max_transition_pressure_index")),
        ("Risque latent", summary.get("max_latent_risk_gap")),
    ]
    return "".join(
        f"<div class='mini-card'><span>{html.escape(label)}</span><strong>{html.escape(_fmt(value))}</strong></div>"
        for label, value in cards
    )


def build_index(report_dir: Path, site_dir: Path) -> None:
    report = _load_json(report_dir / "belgium_alert_report.json")
    alert_state = _load_json(report_dir / "alert_state.json")
    transition = _load_json(report_dir / "convective_transition_report.json")
    source_status = _load_json(report_dir / "source_status.json")
    latest_dir = _copy_outputs(report_dir, site_dir)

    model_score = report.get("national_score") or report.get("score")
    severity = str(report.get("national_severity") or report.get("severity") or "n/a")
    op_level = str(alert_state.get("level") or report.get("operational_level") or "n/a")
    generated_at = report.get("generated_at") or alert_state.get("generated_at") or "n/a"
    window = f"{report.get('window_start') or 'n/a'} → {report.get('window_end') or 'n/a'}"
    source_ok = source_status.get("source_ok_count", report.get("source_ok_count", "n/a"))
    source_errors = source_status.get("source_error_count", report.get("source_error_count", "n/a"))
    public_wording = alert_state.get(
        "public_wording",
        "prototype technique non officiel, à utiliser en complément des sources officielles",
    )

    top_transition_rows = _top_transition(transition)
    transition_list = (
        "".join(
            f"<li><strong>{html.escape(str(row.get('name') or row.get('station_id') or ''))}</strong> · "
            f"void {html.escape(_fmt(row.get('void_collapse_signal')))} · "
            f"cohérence {html.escape(_fmt(row.get('convective_coherence_index')))}</li>"
            for row in top_transition_rows
        )
        or "<li>Données de transition non disponibles.</li>"
    )

    index_html = f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>MeteoVoid Belgique · Veille opérationnelle</title>
<style>
:root {{
  --bg:#eef3f8; --surface:#ffffff; --surface2:#f8fafc; --ink:#0d1b2e; --muted:#66758a;
  --blue:#173b66; --blue2:#245b91; --line:#d9e3ef; --green:#4a9f60; --yellow:#bcae35;
  --orange:#e28a26; --red:#d94a44; --purple:#6f42c1; --shadow:0 18px 42px rgba(20,42,69,.11);
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:Inter,Segoe UI,Roboto,Arial,sans-serif; background:var(--bg); color:var(--ink); }}
a {{ color:#1b63b7; font-weight:700; text-decoration:none; }}
.layout {{ display:grid; grid-template-columns:280px minmax(0,1fr); min-height:100vh; }}
aside {{ background:linear-gradient(180deg,#0d1f36,#143b63); color:white; padding:26px 22px; position:sticky; top:0; height:100vh; }}
.logo {{ display:flex; gap:12px; align-items:center; margin-bottom:28px; }}
.logo-mark {{ width:42px; height:42px; border-radius:14px; background:#ffffff22; display:grid; place-items:center; font-weight:900; }}
.nav a {{ display:block; color:#d9e8f7; padding:12px 14px; border-radius:12px; margin:7px 0; font-size:14px; }}
.nav a.active, .nav a:hover {{ background:#ffffff18; color:white; }}
.aside-note {{ position:absolute; left:22px; right:22px; bottom:24px; border:1px solid #ffffff22; border-radius:14px; padding:14px; color:#d7e7f8; font-size:12px; }}
main {{ padding:24px 28px 42px; }}
.hero {{ display:flex; justify-content:space-between; gap:18px; align-items:flex-start; margin-bottom:22px; }}
h1 {{ margin:0; font-size:38px; letter-spacing:-.04em; }}
.lead {{ color:var(--muted); max-width:860px; line-height:1.55; margin:10px 0 0; }}
.timestamp {{ color:var(--muted); font-size:13px; text-align:right; }}
.warning {{ background:#fff7e8; border:1px solid #f0d5a7; border-left:5px solid var(--orange); border-radius:16px; padding:14px 16px; margin:16px 0 22px; line-height:1.45; }}
.grid {{ display:grid; gap:16px; }}
.kpis {{ grid-template-columns:repeat(5,minmax(150px,1fr)); }}
.card {{ background:var(--surface); border:1px solid var(--line); border-radius:20px; padding:18px; box-shadow:var(--shadow); }}
.card small {{ color:var(--muted); text-transform:uppercase; letter-spacing:.08em; font-weight:800; font-size:11px; }}
.card strong.big {{ display:block; font-size:30px; margin:10px 0 4px; letter-spacing:-.03em; }}
.badge {{ display:inline-flex; align-items:center; border-radius:999px; padding:5px 10px; color:white; font-weight:800; font-size:12px; }}
.sev-normal {{ background:var(--green); }} .sev-watch {{ background:var(--yellow); }} .sev-medium {{ background:var(--orange); }} .sev-high {{ background:var(--red); }} .sev-alert {{ background:var(--purple); }}
.two-col {{ grid-template-columns:minmax(0,1.35fr) minmax(320px,.65fr); margin-top:18px; }}
.tabs {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px; }}
.tab {{ border:1px solid #c9d7e8; background:white; color:#173b66; border-radius:999px; padding:9px 13px; font-weight:800; cursor:pointer; }}
.tab.active {{ background:#173b66; color:white; border-color:#173b66; }}
.frame-wrap {{ background:white; border:1px solid var(--line); border-radius:22px; box-shadow:var(--shadow); overflow:hidden; }}
iframe {{ width:100%; height:72vh; min-height:650px; border:0; background:white; display:block; }}
.panel-title {{ margin:0 0 12px; font-size:18px; }}
.insight {{ border:1px solid var(--line); border-radius:16px; padding:14px; margin:11px 0; background:var(--surface2); line-height:1.45; }}
.insight b {{ display:block; margin-bottom:4px; }}
.mini-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; }}
.mini-card {{ background:#f7faff; border:1px solid #dce8f5; border-radius:14px; padding:12px; }}
.mini-card span {{ display:block; color:var(--muted); font-size:12px; }}
.mini-card strong {{ display:block; font-size:22px; margin-top:5px; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th, td {{ border-bottom:1px solid #e3ebf4; padding:10px; text-align:left; vertical-align:top; }}
th {{ color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.07em; }}
.links {{ display:flex; flex-wrap:wrap; gap:10px; }}
.links a {{ background:white; border:1px solid var(--line); border-radius:999px; padding:8px 12px; }}
@media (max-width:1100px) {{ .layout {{ grid-template-columns:1fr; }} aside {{ position:relative; height:auto; }} .aside-note {{ position:static; margin-top:20px; }} .kpis,.two-col {{ grid-template-columns:1fr; }} .hero {{ display:block; }} .timestamp {{ text-align:left; margin-top:10px; }} }}
</style>
</head>
<body>
<div class="layout">
<aside>
  <div class="logo"><div class="logo-mark">MV</div><div><strong>MeteoVoid</strong><br><span>Belgique</span></div></div>
  <nav class="nav">
    <a class="active" href="#overview">Vue d’ensemble</a>
    <a href="#maps">Cartes</a>
    <a href="#transition">Transition convective</a>
    <a href="#stations">Stations</a>
    <a href="#exports">Exports</a>
  </nav>
  <div class="aside-note"><strong>Statut</strong><br>Page statique générée depuis le dernier run GitHub Actions.<br><br>Non officiel · complément de veille.</div>
</aside>
<main>
  <section id="overview" class="hero">
    <div>
      <h1>MeteoVoid Belgique</h1>
      <p class="lead">Observatoire expérimental de vigilance météo. Lecture synthétique du risque, transition convective, cartes avancées et exports auditables.</p>
    </div>
    <div class="timestamp">Dernière génération<br><strong>{html.escape(str(generated_at))}</strong></div>
  </section>
  <div class="warning"><strong>Prototype technique, non grand public.</strong> MeteoVoid ne remplace pas l’IRM/KMI. Lecture actuelle : {html.escape(str(public_wording))}.</div>
  <section class="grid kpis">
    <div class="card"><small>Score national</small><strong class="big">{html.escape(_fmt(model_score))}</strong><span>Signal modèle</span></div>
    <div class="card"><small>Sévérité</small><strong class="big"><span class="badge {_severity_class(severity)}">{html.escape(severity)}</span></strong><span>Dominante actuelle</span></div>
    <div class="card"><small>Niveau opérationnel</small><strong class="big"><span class="badge {_severity_class(op_level)}">{html.escape(op_level)}</span></strong><span>Après confirmation externe</span></div>
    <div class="card"><small>Fenêtre</small><strong class="big" style="font-size:22px">{html.escape(window)}</strong><span>Période analysée</span></div>
    <div class="card"><small>Sources</small><strong class="big">{html.escape(str(source_ok))}/{html.escape(str(source_errors))}</strong><span>OK / erreurs</span></div>
  </section>
  <section id="maps" class="grid two-col">
    <div>
      <div class="tabs">{_button_nav()}</div>
      <div class="frame-wrap"><iframe id="viewer" title="MeteoVoid viewer" src="reports/latest/belgium_alert_dashboard.html" loading="lazy"></iframe></div>
    </div>
    <div>
      <div class="card">
        <h2 class="panel-title">Comment lire la page</h2>
        <div class="insight"><b>1 · Synthèse</b>Score national, niveau opérationnel et zones sensibles. C’est la vue la plus lisible.</div>
        <div class="insight"><b>2 · Transition convective</b>Lecture MeteoVoid : charge, déclencheur, organisation, couvercle, void collapse.</div>
        <div class="insight"><b>3 · Cartes avancées</b>Les couches sont séparées pour éviter l’effet “bouillie de points”. Active une couche à la fois.</div>
      </div>
      <div id="transition" class="card" style="margin-top:16px;">
        <h2 class="panel-title">Indices de transition</h2>
        <div class="mini-grid">{_transition_cards(transition)}</div>
        <ul>{transition_list}</ul>
      </div>
    </div>
  </section>
  <section id="stations" class="card" style="margin-top:18px;">
    <h2 class="panel-title">Stations les plus sensibles</h2>
    <table><thead><tr><th>Station</th><th>Sévérité</th><th>Score</th><th>Heure sensible</th><th>Signaux</th></tr></thead><tbody>{_station_table(report)}</tbody></table>
  </section>
  <section id="exports" class="card" style="margin-top:18px;">
    <h2 class="panel-title">Exports</h2>
    <div class="links">
      <a href="reports/latest/belgium_alert_report.md">Rapport Markdown</a>
      <a href="reports/latest/convective_transition_report.md">Rapport transition</a>
      <a href="reports/latest/risk_by_station.csv">CSV stations</a>
      <a href="reports/latest/risk_timeline.csv">Timeline</a>
      <a href="reports/latest/weather_layers_grid.csv">Grille météo</a>
      <a href="reports/latest/manifest.json">Manifest</a>
    </div>
  </section>
</main>
</div>
<script>
const buttons = Array.from(document.querySelectorAll('.tab'));
const viewer = document.getElementById('viewer');
buttons.forEach(btn => btn.addEventListener('click', () => {{
  buttons.forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  viewer.src = btn.dataset.target;
}}));
</script>
</body>
</html>
"""
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "index.html").write_text(index_html, encoding="utf-8")
    (site_dir / "README.md").write_text(
        "# MeteoVoid Belgique\n\nPage statique générée automatiquement depuis les artefacts MeteoVoid.\n",
        encoding="utf-8",
    )
    if latest_dir.exists():
        (site_dir / "reports" / "latest" / "README.txt").write_text(
            "Derniers artefacts MeteoVoid Belgique publiés via GitHub Pages.\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a cleaner static GitHub Pages site from MeteoVoid Belgium outputs."
    )
    parser.add_argument("--report-dir", required=True, type=Path)
    parser.add_argument("--site-dir", required=True, type=Path)
    args = parser.parse_args()
    build_index(args.report_dir, args.site_dir)


if __name__ == "__main__":
    main()
