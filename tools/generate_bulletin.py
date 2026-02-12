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


def _confidence(*, missing_time_frac: float, imputed_frac: float) -> str:
    if missing_time_frac > 0.15 or imputed_frac > 0.20:
        return "low"
    if missing_time_frac > 0.05 or imputed_frac > 0.05:
        return "medium"
    return "high"


def _recommendation(severity: str, confidence: str, flags: list[str]) -> str:
    if severity == "high" or "alert" in flags:
        if confidence == "low":
            return "ALERTE (confiance faible, vérifier capteur et données)"
        return "ALERTE (action rapide recommandée)"
    if severity == "medium" or "watch" in flags:
        if confidence == "low":
            return "SURVEILLANCE (confiance faible, trous ou imputation)"
        return "SURVEILLANCE (suivre l'évolution)"
    if "data_hole" in flags:
        return "STABLE (mais trous de données)"
    return "STABLE"


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True))
            f.write("\n")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys = sorted({k for r in rows for k in r.keys()})
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in keys})


def _try_read_reports_stream(compose_file: str, stream: str) -> list[dict[str, Any]]:
    cmd = [
        "docker",
        "compose",
        "-f",
        compose_file,
        "exec",
        "-T",
        "redis",
        "redis-cli",
        "XRANGE",
        stream,
        "-",
        "+",
    ]
    try:
        cp = subprocess.run(  # noqa: S603,S607
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if cp.returncode != 0:
        return []

    out: list[dict[str, Any]] = []
    lines = [ln.strip() for ln in cp.stdout.splitlines() if ln.strip()]

    i = 0
    while i < len(lines):
        msg_id = lines[i]
        if not _ID_RE.match(msg_id):
            i += 1
            continue
        i += 1
        if i >= len(lines):
            break
        if lines[i] != "1)":
            continue
        i += 1

        fields: dict[str, str] = {}
        while i < len(lines):
            if lines[i].startswith("(") and lines[i].endswith(")"):
                break
            if lines[i] == "2)":
                i += 1
                break
            i += 1

        while i < len(lines):
            if lines[i].startswith("(") and lines[i].endswith(")"):
                break
            key = lines[i]
            i += 1
            if i >= len(lines):
                break
            val = lines[i]
            i += 1
            fields[key] = val

        payload = fields.get("payload")
        if payload:
            try:
                obj = json.loads(payload)
            except json.JSONDecodeError:
                obj = None
            if isinstance(obj, dict):
                out.append(obj)

    return out


def _trend_from_history(history: list[dict[str, Any]]) -> dict[tuple[str, str], tuple[float, int]]:
    by_key: dict[tuple[str, str], list[float]] = {}
    for r in history:
        sid = str(r.get("station_id", "")).strip()
        var = str(r.get("variable", "")).strip()
        if not sid or not var:
            continue
        by_key.setdefault((sid, var), []).append(_safe_float(r.get("score", 0.0)))

    out: dict[tuple[str, str], tuple[float, int]] = {}
    for key, scores in by_key.items():
        if len(scores) >= 2:
            out[key] = (float(scores[-1] - scores[-2]), 2)
    return out


def _load_latest_snapshot(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _collect_reports_from_api(api_url: str) -> list[dict[str, Any]]:
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
            url = f"{api_url.rstrip('/')}/latest?station_id={quote(station_id)}&variable={quote(variable)}"
            try:
                rep = _http_json(url)
            except (URLError, TimeoutError, ValueError):
                continue
            if rep.get("score") is None or rep.get("state") is None:
                continue
            out.append(rep)

    return out


def _collect_reports_from_config(
    api_url: str, cfg_path: str, region: str | None
) -> list[dict[str, Any]]:
    # Lazy import to avoid requiring PyYAML unless this fallback is used.
    from meteovoid.stations_config import load_stations_config  # type: ignore[import-not-found]

    cfg = load_stations_config(cfg_path)
    stations = cfg.stations
    if region:
        r = region.strip().lower()
        stations = [s for s in stations if s.region.lower() == r]

    out: list[dict[str, Any]] = []
    for st in stations:
        for variable in st.variables:
            url = f"{api_url.rstrip('/')}/latest?station_id={quote(st.station_id)}&variable={quote(variable)}"
            try:
                rep = _http_json(url)
            except (URLError, TimeoutError, ValueError):
                continue
            if rep.get("score") is None or rep.get("state") is None:
                continue
            out.append(rep)
    return out


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
    trend_score_delta: float | None
    trend_points: int


def _to_var_row(
    report: dict[str, Any],
    trend: dict[tuple[str, str], tuple[float, int]] | None,
) -> VarRow:
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
    n_tr = 0
    if trend is not None:
        key = (station_id, variable)
        if key in trend:
            delta, n_tr = trend[key]

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
        trend_points=n_tr,
    )


def _station_aggregate(rows: list[VarRow]) -> dict[str, Any]:
    if not rows:
        return {
            "score_global": 0.0,
            "severity_global": "low",
            "confidence_global": "low",
            "worst": [],
        }

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
        "worst": [
            {"variable": w.variable, "severity": w.severity, "score": w.score} for w in worst
        ],
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
    lines.append(
        f"- Alerts: {summary['alerts']} | Watches: {summary['watches']} | Data holes: {summary['data_holes']}"
    )
    lines.append(f"- Generated at: {summary['generated_at_iso']}")
    if summary.get("history_messages", 0) > 0:
        lines.append(f"- History messages: {summary['history_messages']}")
    if summary.get("region"):
        lines.append(f"- Region: {summary['region']}")
    lines.append("")
    lines.append("## Tableau synthèse")
    lines.append("")
    lines.append(
        "| station | variable | score | state | severity | confidence | flags | n_points | gaps | missing | imputed | trend |"
    )
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
                f"- {r.variable}: score={r.score:.3f}, state={r.state}, severity={r.severity}, confidence={r.confidence}, flags={','.join(r.flags)}"
            )
            lines.append(f"  - Recommendation: {rec}")
        lines.append("")

    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--api-url", required=True, help="Base URL of the MeteoVoid API")
    p.add_argument("--out-dir", required=True, help="Output directory (ex: _ci_out/live_smoke)")
    p.add_argument("--compose-file", default="docker-compose.yml", help="Docker compose file path")
    p.add_argument("--reports-stream", default="meteovoid:reports", help="Redis stream for reports")
    p.add_argument("--latest-path", default="latest.json", help="Fallback snapshot path in out-dir")
    p.add_argument(
        "--stations-config",
        default="",
        help="Optional stations YAML config path (fallback if /stations is missing)",
    )
    p.add_argument(
        "--region", default="", help="Optional region filter used with --stations-config"
    )
    args = p.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    generated_at = time.time()
    generated_at_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(generated_at))

    reports: list[dict[str, Any]] = []
    api_ok = False
    stations_ok = True

    try:
        reports = _collect_reports_from_api(args.api_url)
        if reports:
            api_ok = True
    except (OSError, ValueError, URLError, TimeoutError, json.JSONDecodeError):
        stations_ok = False

    if not stations_ok and args.stations_config:
        region = args.region.strip() or None
        reports = _collect_reports_from_config(args.api_url, args.stations_config, region)
        if reports:
            api_ok = True

    if not reports:
        snap = _load_latest_snapshot(out_dir / args.latest_path)
        if snap is not None:
            reports = [snap]

    history = _try_read_reports_stream(args.compose_file, args.reports_stream)
    _write_jsonl(out_dir / "history.jsonl", history)
    _write_csv(out_dir / "history.csv", history)
    trend = _trend_from_history(history) if history else None

    rows = [_to_var_row(r, trend) for r in reports if isinstance(r, dict)]
    rows = [r for r in rows if r.station_id and r.variable]

    stations = len({r.station_id for r in rows})
    variables = len(rows)
    alerts = sum(
        1
        for r in rows
        if _severity_rank(r.severity) >= _severity_rank("high") or "alert" in r.flags
    )
    watches = sum(1 for r in rows if r.severity == "medium" or "watch" in r.flags)
    data_holes = sum(1 for r in rows if "data_hole" in r.flags or r.missing_time_frac > 0.0)

    region_out: str | None = None
    if args.region.strip():
        region_out = args.region.strip().lower()

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
        "region": region_out,
    }

    headline = _headline(summary)

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
