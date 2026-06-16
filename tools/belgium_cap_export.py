from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

try:
    from belgium_public_contract import build_belgium_public_latest
except ModuleNotFoundError:  # pragma: no cover - package import mode
    from tools.belgium_public_contract import build_belgium_public_latest

CAP_OUTPUTS = {
    "cap_xml": "belgium_alert_cap.xml",
    "belgium_public_latest_json": "belgium_public_latest.json",
    "static_api_json_legacy": "meteovoid_api_latest.json",
}


def _cap_severity(level: str, score: float) -> str:
    if level in {"alert_confirmed", "alert"} or score >= 0.75:
        return "Severe"
    if level in {"pre_alert_confirmed", "watch_reinforced"} or score >= 0.55:
        return "Moderate"
    return "Minor"


def _cap_urgency(level: str) -> str:
    return "Immediate" if level in {"alert_confirmed", "alert"} else "Expected"


def _headline(report: dict[str, Any]) -> str:
    op = (
        report.get("operational_state") if isinstance(report.get("operational_state"), dict) else {}
    )
    level = str(op.get("level") or report.get("aggregate", {}).get("severity") or "watch")
    return f"MeteoVoid Belgique · {level}"


def build_cap_xml(report: dict[str, Any]) -> str:
    op = (
        report.get("operational_state") if isinstance(report.get("operational_state"), dict) else {}
    )
    aggregate = report.get("aggregate") if isinstance(report.get("aggregate"), dict) else {}
    score = float(aggregate.get("national_score") or op.get("model_score") or 0.0)
    level = str(op.get("level") or aggregate.get("severity") or "watch")
    generated = str(report.get("generated_at") or "")
    window = report.get("target_window") if isinstance(report.get("target_window"), dict) else {}
    description = (
        "Bulletin technique expérimental, non officiel. MeteoVoid ne remplace pas les avertissements IRM/KMI. "
        f"Score modèle {score:.3f}, niveau opérationnel {level}."
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
  <identifier>{html.escape(str(report.get('run_id') or 'meteovoid-run'))}</identifier>
  <sender>meteovoid.local</sender>
  <sent>{html.escape(generated)}</sent>
  <status>Test</status>
  <msgType>Alert</msgType>
  <scope>Public</scope>
  <note>Prototype technique non officiel. Ne pas utiliser comme alerte officielle.</note>
  <info>
    <language>fr-BE</language>
    <category>Met</category>
    <event>Veille météorologique expérimentale</event>
    <responseType>Monitor</responseType>
    <urgency>{_cap_urgency(level)}</urgency>
    <severity>{_cap_severity(level, score)}</severity>
    <certainty>Possible</certainty>
    <eventCode><valueName>MeteoVoidOperationalLevel</valueName><value>{html.escape(level)}</value></eventCode>
    <headline>{html.escape(_headline(report))}</headline>
    <description>{html.escape(description)}</description>
    <effective>{html.escape(str(window.get('start') or generated))}</effective>
    <expires>{html.escape(str(window.get('end') or generated))}</expires>
    <area><areaDesc>Belgique et zones frontalières surveillées par MeteoVoid</areaDesc></area>
  </info>
</alert>
"""


def build_static_api(report: dict[str, Any]) -> dict[str, Any]:
    """Legacy alias for older dashboards expecting meteovoid_api_latest.json."""
    data = build_belgium_public_latest(report)
    data["legacy_alias"] = "meteovoid_api_latest.json"
    return data

def write_cap_outputs(report: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "belgium_alert_cap.xml").write_text(build_cap_xml(report), encoding="utf-8")
    (out_dir / "belgium_public_latest.json").write_text(
        json.dumps(
            build_belgium_public_latest(report),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (out_dir / "meteovoid_api_latest.json").write_text(
        json.dumps(build_static_api(report), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
