from __future__ import annotations

import csv
import html
import json
from pathlib import Path
from typing import Any

VALIDATION_OUTPUTS = {
    "validation_metrics_json": "validation_metrics.json",
    "validation_report_md": "validation_report.md",
    "validation_dashboard_html": "validation_dashboard.html",
}

POSITIVE_LEVELS = {"watch_reinforced", "pre_alert_confirmed", "alert_confirmed", "alert"}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_events(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return [dict(row) for row in reader]


def _matches_window(report: dict[str, Any], row: dict[str, Any]) -> bool:
    start = str(report.get("target_window", {}).get("start") or report.get("window_start") or "")[
        :10
    ]
    end = str(report.get("target_window", {}).get("end") or report.get("window_end") or "")[:10]
    event_start = str(row.get("date_start") or row.get("start") or row.get("date") or "")[:10]
    event_end = str(row.get("date_end") or row.get("end") or row.get("date") or event_start)[:10]
    if not event_start:
        return False
    return (
        (start <= event_start <= end)
        or (start <= event_end <= end)
        or (event_start <= start <= event_end)
    )


def _brier(prob: float, observed: bool) -> float:
    return (prob - (1.0 if observed else 0.0)) ** 2


def build_validation_metrics(report: dict[str, Any]) -> dict[str, Any]:
    replay_path = (
        Path(str(report.get("replay_events") or "")) if report.get("replay_events") else None
    )
    events = _load_events(replay_path)
    matched = [event for event in events if _matches_window(report, event)]
    op = (
        report.get("operational_state") if isinstance(report.get("operational_state"), dict) else {}
    )
    level = str(op.get("level") or "")
    prob = max(
        _as_float(report.get("aggregate", {}).get("national_score")),
        _as_float(op.get("model_score")),
    )
    predicted_positive = level in POSITIVE_LEVELS or prob >= 0.55

    evaluated: list[dict[str, Any]] = []
    tp = fp = fn = tn = 0
    brier_values: list[float] = []
    for event in matched:
        observed = str(
            event.get("expected_detected") or event.get("observed") or event.get("event") or ""
        ).lower() in {
            "1",
            "true",
            "yes",
            "oui",
            "detected",
            "severe",
        }
        if predicted_positive and observed:
            tp += 1
        elif predicted_positive and not observed:
            fp += 1
        elif not predicted_positive and observed:
            fn += 1
        else:
            tn += 1
        brier_values.append(_brier(prob, observed))
        evaluated.append(
            {
                **event,
                "model_probability": round(prob, 6),
                "predicted_positive": predicted_positive,
                "observed_positive": observed,
            }
        )

    pod = tp / (tp + fn) if (tp + fn) else None
    far = fp / (tp + fp) if (tp + fp) else None
    csi = tp / (tp + fp + fn) if (tp + fp + fn) else None
    brier = sum(brier_values) / len(brier_values) if brier_values else None
    if not evaluated:
        status = "needs_verified_events"
    elif pod is not None and csi is not None and csi >= 0.4:
        status = "usable_signal"
    else:
        status = "under_calibration"
    return {
        "generated_at": report.get("generated_at"),
        "run_id": report.get("run_id"),
        "status": status,
        "event_file": str(replay_path) if replay_path else "",
        "matched_event_count": len(evaluated),
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "scores": {
            "pod": pod,
            "far": far,
            "csi": csi,
            "brier_score": brier,
            "model_probability": round(prob, 6),
        },
        "decision_theory": {
            "cost_loss_thresholds": [
                {"cost_loss_ratio": 0.05, "alert_if_probability_ge": 0.05},
                {"cost_loss_ratio": 0.10, "alert_if_probability_ge": 0.10},
                {"cost_loss_ratio": 0.25, "alert_if_probability_ge": 0.25},
                {"cost_loss_ratio": 0.50, "alert_if_probability_ge": 0.50},
            ],
            "note": "Dans un modèle coût-perte, le seuil optimal dépend du rapport coût de l'action / perte évitée.",
        },
        "conformal_prediction": {
            "status": "scaffold",
            "note": "Ajouter un historique d'événements vérifiés pour calculer des intervalles de couverture conformes.",
        },
        "events": evaluated,
    }


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def _render_markdown(data: dict[str, Any]) -> str:
    scores = data.get("scores", {}) if isinstance(data.get("scores"), dict) else {}
    confusion = data.get("confusion", {}) if isinstance(data.get("confusion"), dict) else {}
    return "\n".join(
        [
            "# MeteoVoid Belgique · Validation",
            "",
            f"Statut : **{data.get('status', 'n/a')}**",
            f"Événements appariés : **{data.get('matched_event_count', 0)}**",
            "",
            "## Scores",
            f"- POD : `{_fmt(scores.get('pod'))}`",
            f"- FAR : `{_fmt(scores.get('far'))}`",
            f"- CSI : `{_fmt(scores.get('csi'))}`",
            f"- Brier : `{_fmt(scores.get('brier_score'))}`",
            "",
            "## Matrice de confusion",
            f"- TP : `{confusion.get('tp', 0)}`",
            f"- FP : `{confusion.get('fp', 0)}`",
            f"- FN : `{confusion.get('fn', 0)}`",
            f"- TN : `{confusion.get('tn', 0)}`",
            "",
            "Ce module devient pleinement informatif lorsque le fichier d'événements historiques contient des cas vérifiés.",
        ]
    )


def _render_html(data: dict[str, Any]) -> str:
    scores = data.get("scores", {}) if isinstance(data.get("scores"), dict) else {}
    confusion = data.get("confusion", {}) if isinstance(data.get("confusion"), dict) else {}
    return f"""<!doctype html><html lang='fr'><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width, initial-scale=1'/><title>MeteoVoid · Validation</title><style>
body{{margin:0;font-family:Inter,Segoe UI,Arial,sans-serif;background:#eef3f8;color:#0d1b2e}}header{{background:#173b66;color:white;padding:22px 26px}}.wrap{{padding:22px;max-width:1100px;margin:auto}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}}.card{{background:white;border:1px solid #d9e3ef;border-radius:18px;padding:18px;box-shadow:0 14px 32px rgba(20,42,69,.08)}}.big{{font-size:30px;font-weight:900;display:block;margin-top:8px}}small{{color:#66758a;text-transform:uppercase;font-weight:800;letter-spacing:.08em}}.note{{margin-top:18px;background:#fff7e8;border-left:5px solid #e28a26;border-radius:14px;padding:14px 16px}}
</style></head><body><header><h1>MeteoVoid Belgique · Validation & skill scores</h1><p>POD, FAR, CSI, Brier et cadre coût-perte.</p></header><div class='wrap'><div class='grid'>
<div class='card'><small>POD</small><span class='big'>{html.escape(_fmt(scores.get("pod")))}</span></div>
<div class='card'><small>FAR</small><span class='big'>{html.escape(_fmt(scores.get("far")))}</span></div>
<div class='card'><small>CSI</small><span class='big'>{html.escape(_fmt(scores.get("csi")))}</span></div>
<div class='card'><small>Brier</small><span class='big'>{html.escape(_fmt(scores.get("brier_score")))}</span></div>
</div><div class='note'><strong>Événements appariés : {html.escape(str(data.get("matched_event_count", 0)))}</strong><br>Confusion : TP {confusion.get("tp", 0)}, FP {confusion.get("fp", 0)}, FN {confusion.get("fn", 0)}, TN {confusion.get("tn", 0)}. Ajouter des cas vérifiés pour rendre ce module réfutable.</div></div></body></html>"""


def write_validation_outputs(report: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    data = build_validation_metrics(report)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "validation_metrics.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    (out_dir / "validation_report.md").write_text(_render_markdown(data), encoding="utf-8")
    (out_dir / "validation_dashboard.html").write_text(_render_html(data), encoding="utf-8")
    return data
