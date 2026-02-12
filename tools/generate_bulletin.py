from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


_ID_RE = re.compile(r"^\d+-\d+$")


def _http_json(url: str, timeout_s: float = 2.5) -> dict[str, Any]:
    req = Request(url, headers={"Accept": "application/json"})
    with urlopen(req, timeout=timeout_s) as r:  # noqa: S310
        data = r.read().decode("utf-8", errors="replace")
    obj = json.loads(data)
    if not isinstance(obj, dict):
        raise ValueError("HTTP response is not a JSON object")
    return obj


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return int(default)


def _severity_rank(sev: str) -> int:
    sev = str(sev).lower()
    return {"low": 0, "medium": 1, "high": 2}.get(sev, 0)


def _confidence(missing_time_frac: float, imputed_frac: float) -> str:
    if missing_time_frac > 0.15 or imputed_frac > 0.25:
        return "low"
    if missing_time_frac > 0.05 or imputed_frac > 0.0:
        return "medium"
    return "high"


def _recommendation(severity: str, confidence: str, flags: list[str]) -> str:
    sev = str(severity).lower()
    conf = str(confidence).lower()

    if sev == "high":
        if conf == "low":
            return "Alerte (confiance faible): vérifier capteur et trous de données."
        return "Alerte: action immédiate ou investigation."
    if sev == "medium":
        if "data_hole" in flags:
            return "Surveillance: variabilité + trous de données."
        return "Surveillance: suivre l'évolution et confirmer."
    if conf == "low":
        return "Confiance faible: prioriser la qualité des données."
    return "Rien à signaler."


@dataclass(frozen=True)
class VarRow:
    station_id: str
    variable: str
    score: float
    state: str
    severity: str
    confidence: str
    flags: list[str]
    n_points: int
    gap_count: int
    missing_time_frac: float
    imputed_frac: float
    ts_ingest: float
    trend_score_delta: float | None = None
    trend_points: int | None = None


def _decode_redis_xrange_raw(raw: str) -> list[tuple[str, dict[str, str]]]:
    lines = [ln for ln in raw.splitlines() if ln.strip() != ""]
    out: list[tuple[str, dict[str, str]]] = []
    i = 0
    while i < len(lines):
        msg_id = lines[i].strip()
        if not _ID_RE.match(msg_id):
            i += 1
            continue
        i += 1
        fields: dict[str, str] = {}
        while i + 1 < len(lines) and not _ID_RE.match(lines[i].strip()):
            k = lines[i].strip()
            v = lines[i + 1].strip()
            fields[k] = v
            i += 2
        out.append((msg_id, fields))
    return out


def _try_read_reports_stream(compose_file: str, reports_stream: str) -> list[dict[str, Any]]:
    cmd = [
        "docker",
        "compose",
        "-f",
        compose_file,
        "exec",
        "-T",
        "redis",
        "redis-cli",
        "--raw",
        "XRANGE",
        reports_stream,
        "-",
        "+",
    ]
    try:
        p = subprocess.run(cmd, check=False, capture_output=True, text=True)  # noqa: S603
    except FileNotFoundError:
        return []

    if p.returncode != 0:
        return []

    entries = _decode_redis_xrange_raw(p.stdout)
    history: list[dict[str, Any]] = []
    for msg_id, fields in entries:
        payload = fields.get("payload")
        if not payload:
            continue
        try:
            report_any = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if not isinstance(report_any, dict):
            continue

        station_id = str(fields.get("station_id") or report_any.get("station_id") or "").strip()
        variable = str(fields.get("variable") or report_any.get("variable") or "").strip()

        history.append(
            {
                "stream_id": msg_id,
                "station_id": station_id,
                "variable": variable,
                "ts_ingest": _safe_float(report_any.get("ts_ingest", 0.0)),
                "score": _safe_float(report_any.get("score", 0.0)),
                "state": str(report_any.get("state", "")),
                "severity": str((report_any.get("meteo") or {}).get("severity", "")),
                "flags": (report_any.get("meteo") or {}).get("flags", []),
                "stats": report_any.get("stats", {}),
            }
        )

    return history


def _load_latest_snapshot(latest_path: Path) -> dict[str, Any] | None:
    try:
        obj = json.loads(latest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(obj, dict) and obj.get("score") is not None and obj.get("state") is not None:
        return obj
    return None


def _collect_reports(api_url: str) -> list[dict[str, Any]]:
    stations_url = f"{api_url.rstrip('/')}/stations"
    stations_obj = _http_json(stations_url)
    stations = stations_obj.get("stations", {})

    out: list[dict[str, Any]] = []
    if not isinstance(stations, dict):
        return out

    for station_id, vars_any in stations.items():
        if not isinstance(station_id, str) or not station_id:
            continue
        if not isinstance(vars_any, list):
            continue
        for variable in vars_any:
            if not isinstance(variable, str) or not variable:
                continue
            url = (
                f"{api_url.rstrip('/')}/latest?station_id={quote(station_id)}&variable={quote(variable)}"
            )
            try:
                rep = _http_json(url)
            except (URLError, TimeoutError, ValueError):
                continue
            if rep.get("score") is None or rep.get("state") is None:
                continue
            out.append(rep)

    return out


def _to_var_row(report: dict[str, Any], trend: dict[tuple[str, str], tuple[float, int]] | None) -> VarRow:
    station_id = str(report.get("station_id", "")).strip()
    variable = str(report.get("variable", "")).strip()

    score = _safe_float(report.get("score", 0.0))
    state = str(report.get("state", "")).strip()

    meteo = report.get("meteo") or {}
    if not isinstance(meteo, dict):
        meteo = {}
    flags_any = meteo.get("flags", [])
    flags = [str(x) for x in flags_any] if isinstance(flags_any, list) else []

    stats = report.get("stats") or {}
    if not isinstance(stats, dict):
        stats = {}

    missing_time_frac = _safe_float(stats.get("missing_time_frac", 0.0))
    imputed_frac = _safe_float(stats.get("imputed_frac", 0.0))
    n_points = _safe_int(stats.get("n_points", 0))
    gap_count = _safe_int(stats.get("gap_count", 0))

    ts_ingest = _safe_float(report.get("ts_ingest", 0.0))

    severity = str(meteo.get("severity", "")).strip().lower()
    if not severity:
        severity = "high" if state == "unstable" else "medium" if state == "transition" else "low"

    conf = _confidence(missing_time_frac=missing_time_frac, imputed_frac=imputed_frac)

    delta: float | None = None
    ntrend: int | None = None
    if trend is not None:
        key = (station_id, variable)
        if key in trend:
            delta, ntrend = trend[key]

    return VarRow(
        station_id=station_id,
        variable=variable,
        score=score,
        state=state,
        severity=severity,
        confidence=conf,
        flags=flags,
        n_points=n_points,
        gap_count=gap_count,
        missing_time_frac=missing_time_frac,
        imputed_frac=imputed_frac,
        ts_ingest=ts_ingest,
        trend_score_delta=delta,
        trend_points=ntrend,
    )


def _trend_from_history(history: list[dict[str, Any]]) -> dict[tuple[str, str], tuple[float, int]]:
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in history:
        sid = str(row.get("station_id", "")).strip()
        var = str(row.get("variable", "")).strip()
        if not sid or not var:
            continue
        by_key.setdefault((sid, var), []).append(row)

    out: dict[tuple[str, str], tuple[float, int]] = {}
    for key, rows in by_key.items():
        rows_sorted = sorted(rows, key=lambda r: str(r.get("stream_id", "")))
        if len(rows_sorted) < 2:
            continue
        first = _safe_float(rows_sorted[0].get("score", 0.0))
        last = _safe_float(rows_sorted[-1].get("score", 0.0))
        out[key] = (last - first, len(rows_sorted))
    return out


def _station_aggregate(rows: list[VarRow]) -> dict[str, Any]:
    if not rows:
        return {"score_global": 0.0, "severity_global": "low", "confidence_global": "low", "worst": []}

    # Simple average. Weighting can be added later via station config.
    score_global = float(sum(r.score for r in rows) / float(len(rows)))

    sev_global = "low"
    conf_global = "high"
    for r in rows:
        if _severity_rank(r.severity) > _severity_rank(sev_global):
            sev_global = r.severity
        if r.confidence == "low":
            conf_global = "low"
        elif r.confidence == "medium" and conf_global != "low":
            conf_global = "medium"

    worst = sorted(rows, key=lambda r: (_severity_rank(r.severity), r.score), reverse=True)[:5]
    return {
        "score_global": score_global,
        "severity_global": sev_global,
        "confidence_global": conf_global,
        "worst": [{"variable": w.variable, "severity": w.severity, "score": w.score} for w in worst],
    }


def _headline(summary: dict[str, Any]) -> str:
    if summary.get("alerts", 0) > 0:
        return "ALERTE"
    if summary.get("watches", 0) > 0:
        return "SURVEILLANCE"
    return "STABLE"


def _write_markdown(path: Path, headline: str, summary: dict[str, Any], rows: list[VarRow]) -> None:
    lines: list[str] = []
    lines.append(f"# Bulletin MeteoVoid Live: {headline}")
    lines.append("")
    lines.append(f"- Stations: {summary['stations']}")
    lines.append(f"- Variables: {summary['variables']}")
    lines.append(f"- Alerts: {summary['alerts']} | Watches: {summary['watches']} | Data holes: {summary['data_holes']}")
    lines.append(f"- Generated at: {summary['generated_at_iso']}")
    if summary.get("history_messages", 0) > 0:
        lines.append(f"- History messages: {summary['history_messages']}")
    lines.append("")
    lines.append("## Tableau synthèse")
    lines.append("")
    lines.append("| station | variable | score | state | severity | confidence | flags | n_points | gaps | missing | imputed | trend |")
    lines.append("|---|---|---:|---|---|---|---|---:|---:|---:|---:|---:|")
    for r in sorted(rows, key=lambda x: (_severity_rank(x.severity), x.score), reverse=True):
        flags = ",".join(r.flags)
        missing = f"{r.missing_time_frac:.3f}"
        imputed = f"{r.imputed_frac:.3f}"
        trend = ""
        if r.trend_score_delta is not None:
            trend = f"{r.trend_score_delta:+.3f}"
        lines.append(
            f"| {r.station_id} | {r.variable} | {r.score:.3f} | {r.state} | {r.severity} | {r.confidence} | {flags} | {r.n_points} | {r.gap_count} | {missing} | {imputed} | {trend} |"
        )

    # Per-station details
    lines.append("")
    lines.append("## Détails par station")
    lines.append("")
    by_station: dict[str, list[VarRow]] = {}
    for r in rows:
        by_station.setdefault(r.station_id, []).append(r)

    for station_id in sorted(by_station.keys()):
        srows = by_station[station_id]
        agg = _station_aggregate(srows)
        lines.append(f"### {station_id}")
        lines.append("")
        lines.append(
            f"Score global: {agg['score_global']:.3f} | Severity: {agg['severity_global']} | Confidence: {agg['confidence_global']}"
        )
        lines.append("")
        for r in sorted(srows, key=lambda x: (_severity_rank(x.severity), x.score), reverse=True):
            rec = _recommendation(r.severity, r.confidence, r.flags)
            lines.append(
                f"- {r.variable}: score={r.score:.3f} state={r.state} severity={r.severity} confidence={r.confidence} flags={','.join(r.flags)}"
            )
            lines.append(f"  - {rec}")
        lines.append("")

    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _write_json(path: Path, obj: dict[str, Any]) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_history(out_dir: Path, history: list[dict[str, Any]]) -> None:
    if not history:
        return

    jsonl = out_dir / "history.jsonl"
    with jsonl.open("w", encoding="utf-8") as f:
        for row in history:
            f.write(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n")

    csv_path = out_dir / "history.csv"
    cols = [
        "stream_id",
        "ts_ingest",
        "station_id",
        "variable",
        "score",
        "state",
        "severity",
        "missing_time_frac",
        "imputed_frac",
        "gap_count",
        "n_points",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for row in history:
            stats = row.get("stats") or {}
            if not isinstance(stats, dict):
                stats = {}
            w.writerow(
                {
                    "stream_id": row.get("stream_id", ""),
                    "ts_ingest": _safe_float(row.get("ts_ingest", 0.0)),
                    "station_id": row.get("station_id", ""),
                    "variable": row.get("variable", ""),
                    "score": _safe_float(row.get("score", 0.0)),
                    "state": row.get("state", ""),
                    "severity": row.get("severity", ""),
                    "missing_time_frac": _safe_float(stats.get("missing_time_frac", 0.0)),
                    "imputed_frac": _safe_float(stats.get("imputed_frac", 0.0)),
                    "gap_count": _safe_int(stats.get("gap_count", 0)),
                    "n_points": _safe_int(stats.get("n_points", 0)),
                }
            )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--api-url", required=True, help="Base URL of the MeteoVoid API, e.g. http://localhost:8000")
    p.add_argument("--out-dir", required=True, help="Output directory (e.g. _ci_out/live_smoke)")
    p.add_argument("--compose-file", default="docker-compose.yml", help="Docker compose file path")
    p.add_argument("--reports-stream", default="meteovoid:reports", help="Redis stream for reports")
    p.add_argument(
        "--latest-path",
        default="latest.json",
        help="Fallback snapshot when API is unavailable (relative to out-dir)",
    )
    args = p.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    generated_at = time.time()
    generated_at_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(generated_at))

    # 1) Try to collect full set via API.
    reports: list[dict[str, Any]] = []
    api_ok = False
    try:
        reports = _collect_reports(args.api_url)
        if reports:
            api_ok = True
    except (OSError, ValueError, URLError, TimeoutError, json.JSONDecodeError):
        api_ok = False

    # 2) Fallback to existing latest.json if needed.
    if not reports:
        snap = _load_latest_snapshot(out_dir / args.latest_path)
        if snap is not None:
            reports = [snap]

    # 3) History (best effort).
    history = _try_read_reports_stream(args.compose_file, args.reports_stream)
    _write_history(out_dir, history)
    trend = _trend_from_history(history) if history else None

    rows = [_to_var_row(r, trend) for r in reports if isinstance(r, dict)]
    rows = [r for r in rows if r.station_id and r.variable]

    # Summary counts
    stations = len({r.station_id for r in rows})
    variables = len(rows)
    alerts = sum(1 for r in rows if _severity_rank(r.severity) >= _severity_rank("high") or "alert" in r.flags)
    watches = sum(1 for r in rows if r.severity == "medium" or "watch" in r.flags)
    data_holes = sum(1 for r in rows if "data_hole" in r.flags or r.missing_time_frac > 0.0)

    summary = {
        "generated_at": generated_at,
        "generated_at_iso": generated_at_iso,
        "stations": stations,
        "variables": variables,
        "alerts": alerts,
        "watches": watches,
        "data_holes": data_holes,
        "api_ok": api_ok,
        "history_messages": len(history),
    }

    headline = _headline(summary)

    # Station aggregates
    by_station: dict[str, list[VarRow]] = {}
    for r in rows:
        by_station.setdefault(r.station_id, []).append(r)

    stations_obj: dict[str, Any] = {}
    for sid, srows in by_station.items():
        stations_obj[sid] = _station_aggregate(srows)

    bulletin = {
        "headline": headline,
        "summary": summary,
        "stations": stations_obj,
        "variables": [
            {
                "station_id": r.station_id,
                "variable": r.variable,
                "score": r.score,
                "state": r.state,
                "severity": r.severity,
                "confidence": r.confidence,
                "flags": r.flags,
                "n_points": r.n_points,
                "gap_count": r.gap_count,
                "missing_time_frac": r.missing_time_frac,
                "imputed_frac": r.imputed_frac,
                "ts_ingest": r.ts_ingest,
                "trend_score_delta": r.trend_score_delta,
                "trend_points": r.trend_points,
                "recommendation": _recommendation(r.severity, r.confidence, r.flags),
            }
            for r in rows
        ],
    }

    _write_json(out_dir / "bulletin.json", bulletin)
    _write_markdown(out_dir / "bulletin.md", headline, summary, rows)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
