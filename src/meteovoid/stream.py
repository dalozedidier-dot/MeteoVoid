from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

from redis.typing import EncodableT

from .alerts import maybe_send_alert
from .config import StationConfig, env_config_path, load_station_config, resolve_variable_overrides
from . import db as _db
from .live import LiveConfig, RollingWindow, State, analyze_window
from .scoring import compute_composite_score
from .utils import make_redis

StreamFields = dict[str, str]
Message = tuple[str, StreamFields]
XReadResponse = list[tuple[str, list[Message]]]


def _parse_ts(ts: str) -> datetime:
    try:
        return datetime.fromtimestamp(float(ts), tz=UTC)
    except (TypeError, ValueError):
        return datetime(1970, 1, 1, tzinfo=UTC)


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _latest_key(station_id: str, variable: str) -> str:
    return f"meteovoid:latest:{station_id}:{variable}"


def _default_start_id() -> str:
    override = os.getenv("METEOVOID_START_ID")
    if override:
        return override
    if os.getenv("GITHUB_ACTIONS") or os.getenv("CI"):
        return "0-0"
    return "$"


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    xs = sorted(values)
    k = int(round(0.95 * (len(xs) - 1)))
    k = max(0, min(len(xs) - 1, k))
    return float(xs[k])


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    xs = sorted(values)
    n = len(xs)
    mid = n // 2
    if n % 2 == 1:
        return float(xs[mid])
    return float((xs[mid - 1] + xs[mid]) / 2.0)


def _median_dict_vals(d: dict[str, float], exclude_key: str) -> float | None:
    xs = [float(v) for k, v in d.items() if k != exclude_key]
    if len(xs) < 3:
        return None
    return _median(xs)


def _state_from_score(score: float, stable_th: float, unstable_th: float) -> State:
    if score < stable_th:
        return "stable"
    if score > unstable_th:
        return "unstable"
    return "transition"


def _meteo_interpretation(
    *,
    state: str,
    score: float,
    n_points: int,
    missing_time_frac: float,
    gap_count: int,
    gap_max_s: float = 0.0,
    watch_threshold: float,
    alert_threshold: float,
    imputed_frac: float,
    max_imputed_frac: float,
    signals: dict[str, float] | None = None,
    variable: str = "",
) -> dict[str, Any]:
    signals = signals or {}

    flags: list[str] = []
    severity = "low"

    if score >= alert_threshold:
        flags.append("alert")
        severity = "high"
    elif score >= watch_threshold:
        flags.append("watch")
        severity = "medium"
    else:
        if state == "unstable":
            flags.append("alert")
            severity = "high"
        elif state == "transition":
            flags.append("watch")
            severity = "medium"

    if missing_time_frac > 0.05 or gap_count > 0:
        flags.append("data_hole")
        if severity == "low":
            severity = "medium"

    if imputed_frac > 0.0:
        flags.append("imputed")
        if imputed_frac > max_imputed_frac:
            flags.append("imputation_high")
            severity = "high"

    # Explainability flags (soft)
    def _sig(name: str) -> float:
        try:
            return float(signals.get(name, 0.0))
        except (TypeError, ValueError):
            return 0.0

    def _flag_if(name: str, thr: float = 0.45) -> None:
        if _sig(name) >= thr:
            flags.append(name)

    for nm in ("outlier", "flatline", "spike", "drift", "spatial", "multivar"):
        _flag_if(nm)

    # --- Variable context (wind / temperature / pressure) ---
    var_lower = variable.lower()
    is_wind = "wind" in var_lower or "gust" in var_lower
    is_temp = "temp" in var_lower
    is_pressure = "pressure" in var_lower

    # --- Build human phrases ---
    phrases: list[str] = []

    if n_points < 20:
        phrases.append("Peu de points dans la fenêtre, confiance limitée.")

    # Primary state phrase
    if "alert" in flags:
        phrases.append("Instabilité forte, alerte.")
    elif "watch" in flags:
        phrases.append("Variabilité en hausse, surveillance recommandée.")
    else:
        phrases.append("Signal stable.")

    # Data continuity
    if "data_hole" in flags:
        if gap_max_s > 1800:
            minutes = int(gap_max_s // 60)
            phrases.append(f"Trou de données prolongé (> {minutes} min) — lacune inhabituelle.")
        elif gap_max_s > 300:
            phrases.append("Trou de données prolongé dans la fenêtre.")
        else:
            phrases.append("Présence de trous de données dans la fenêtre.")

    # Spatial coherence
    if "spatial" in flags:
        if is_wind:
            phrases.append("Rafales incohérentes avec les stations voisines.")
        elif is_temp:
            phrases.append("Température incohérente par rapport aux stations voisines.")
        elif is_pressure:
            phrases.append("Pression incohérente avec le champ spatial attendu.")
        else:
            phrases.append("Incohérence spatiale avec les stations voisines.")

    # Spike
    if "spike" in flags:
        if is_wind:
            phrases.append("Saut brusque sur le vent — potentiellement non météorologique.")
        elif is_temp:
            phrases.append("Saut brusque de température — potentiellement non météorologique.")
        else:
            phrases.append("Saut brusque potentiellement non météorologique.")

    # Drift
    if "drift" in flags:
        drift_score = _sig("drift")
        if drift_score > 0.7:
            phrases.append("Dérive lente inhabituelle et soutenue sur la fenêtre.")
        else:
            phrases.append("Dérive lente inhabituelle détectée.")

    # Outlier
    if "outlier" in flags:
        outlier_score = _sig("outlier")
        if outlier_score > 0.7:
            phrases.append("Valeurs fortement aberrantes — signal suspect.")
        else:
            phrases.append("Valeurs aberrantes détectées.")

    # Flatline
    if "flatline" in flags:
        phrases.append("Plateau anormal — le capteur pourrait être bloqué ou déconnecté.")

    # Multi-variable
    if "multivar" in flags:
        phrases.append("Incohérence multi-variables : les grandeurs mesurées sur ce site sont décorrélées.")

    # Imputation warning
    if "imputation_high" in flags:
        pct = int(imputed_frac * 100)
        phrases.append(f"Imputation élevée ({pct} % des points) — score à interpréter avec prudence.")

    return {
        "interpretation": " ".join(phrases).strip(),
        "flags": flags,
        "severity": severity,
        "score_hint": "plus le score est haut, plus la stabilité est faible",
        "state_hint": "stable, transition, unstable",
    }


def _impute_values(
    *,
    samples: list[tuple[datetime, float]],
    dt_expected_s: float,
    gap_threshold_s: float,
    mode: str,
    max_points: int,
) -> tuple[list[float], int]:
    if not samples:
        return ([], 0)

    if mode not in {"ffill", "mean"}:
        return ([v for _t, v in samples], 0)

    out: list[float] = [float(samples[0][1])]
    inserted = 0

    dt_expected_s = max(float(dt_expected_s), 0.001)

    for i in range(1, len(samples)):
        prev_t, _prev_v = samples[i - 1]
        t, v = samples[i]
        d = float((t - prev_t).total_seconds())

        if d > gap_threshold_s:
            # Insert points to roughly match the expected cadence.
            k = int(d // dt_expected_s) - 1
            if k > 0:
                k = min(k, max_points - inserted)
                for _ in range(k):
                    if mode == "ffill":
                        fill = out[-1]
                    else:
                        tail = out[-5:]
                        fill = float(sum(tail) / max(1, len(tail)))
                    out.append(float(fill))
                inserted += k

        out.append(float(v))
        if inserted >= max_points:
            break

    return (out, inserted)


def _get_float(overrides: dict[str, Any], key: str, default: float) -> float:
    v = overrides.get(key)
    if v is None:
        return float(default)
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def _get_int(overrides: dict[str, Any], key: str, default: int) -> int:
    v = overrides.get(key)
    if v is None:
        return int(default)
    try:
        return int(v)
    except (TypeError, ValueError):
        return int(default)


def _get_str(overrides: dict[str, Any], key: str, default: str) -> str:
    v = overrides.get(key)
    return str(v) if v is not None else default


def _get_list_str(overrides: dict[str, Any], key: str) -> list[str] | None:
    v = overrides.get(key)
    if v is None:
        return None
    if isinstance(v, list) and all(isinstance(x, str) for x in v):
        return [str(x) for x in v if str(x)]
    return None


def process_observation(
    fields: Mapping[str, Any],
    msg_id: str = "",
    cfg: LiveConfig | None = None,
    windows: dict[tuple[str, str], RollingWindow] | None = None,
    ts_ingest: float | None = None,
    station_config: StationConfig | None = None,
    peer_state: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any] | None:
    cfg = cfg or LiveConfig()
    windows = windows if windows is not None else {}

    station_id_raw = fields.get("station_id")
    variable_raw = fields.get("variable")
    if station_id_raw is None or variable_raw is None:
        return None

    station_id = str(station_id_raw).strip()
    variable = str(variable_raw).strip()
    value = _to_float(fields.get("value"))
    ts = _parse_ts(str(fields.get("ts", "0")))

    if not station_id or not variable or value is None:
        return None

    overrides = resolve_variable_overrides(station_config, station_id=station_id, variable=variable)

    # Allow per-variable rolling window override.
    window_s = _get_int(overrides, "window_s", cfg.window_s)

    stable_th = _get_float(overrides, "stable_threshold", cfg.stable_threshold)
    unstable_th = _get_float(overrides, "unstable_threshold", cfg.unstable_threshold)
    gap_threshold = _get_float(overrides, "max_gap_s", cfg.max_gap_s)

    watch_threshold = _get_float(overrides, "watch_threshold", (stable_th + unstable_th) / 2.0)
    alert_threshold = _get_float(overrides, "alert_threshold", unstable_th)

    impute_mode = _get_str(overrides, "impute_mode", cfg.impute_mode)
    use_imputed_for_score = bool(overrides.get("use_imputed_for_score", cfg.use_imputed_for_score))
    max_imputed_frac = _get_float(overrides, "max_imputed_frac", cfg.max_imputed_frac)
    max_impute_points = _get_int(overrides, "max_impute_points", cfg.max_impute_points)

    key = (station_id, variable)
    win = windows.get(key)
    if win is None or int(win.window_s) != int(window_s):
        win = RollingWindow(window_s=int(window_s))
        windows[key] = win

    win.push(ts, float(value))

    samples = win.samples(ts)
    values = [v for _t, v in samples]

    # Base (backward compatible): normalized volatility score + timestamp
    base = dict(analyze_window(values, cfg))
    base_score = float(cast(float, base.get("score", 0.0)))

    n = len(values)
    v_min = float(min(values)) if values else 0.0
    v_max = float(max(values)) if values else 0.0
    v_mean = float(sum(values) / n) if n else 0.0
    v_p95 = _p95(values)

    deltas: list[float] = []
    for i in range(1, len(samples)):
        deltas.append(float((samples[i][0] - samples[i - 1][0]).total_seconds()))

    # Important: do not let a single large gap inflate the expected cadence.
    # Use the median of "regular" deltas (<= gap_threshold) when available.
    deltas_pos = [d for d in deltas if d > 0.0]
    deltas_regular = [d for d in deltas_pos if d <= gap_threshold]

    dt_expected_s = _median(deltas_regular) if deltas_regular else _median(deltas_pos)
    dt_expected_s = max(float(dt_expected_s), 0.001)

    gaps = [d for d in deltas_pos if d > gap_threshold]
    gap_count = len(gaps)
    gap_max = float(max(gaps)) if gaps else 0.0
    gap_total = float(sum(gaps)) if gaps else 0.0

    missing_time_s = float(sum(max(0.0, d - dt_expected_s) for d in gaps)) if gaps else 0.0
    missing_time_frac = float(min(1.0, missing_time_s / float(max(1, window_s))))

    imputed_values: list[float] = values
    imputed_points = 0
    if impute_mode in {"ffill", "mean"} and samples and gap_count > 0:
        imputed_values, imputed_points = _impute_values(
            samples=samples,
            dt_expected_s=dt_expected_s,
            gap_threshold_s=gap_threshold,
            mode=impute_mode,
            max_points=max_impute_points,
        )

    total_points = max(1, len(values) + imputed_points)
    imputed_frac = float(imputed_points / float(total_points)) if imputed_points > 0 else 0.0

    # Peers (spatial check): median mean over other stations for the same variable
    peer_median = None
    if peer_state is not None:
        block = peer_state.get(variable)
        if isinstance(block, dict):
            peer_median = _median_dict_vals(block, exclude_key=station_id)

    # Multi-variable peers: read from windows within the same station
    multivar_peers: dict[str, list[float]] = {}
    peers_list = _get_list_str(overrides, "multivar_peers") or []
    for pvar in peers_list:
        if pvar == variable:
            continue
        other = windows.get((station_id, pvar))
        if other is None:
            continue
        multivar_peers[pvar] = other.values(ts)

    # Composite score (normalized in [0..1])
    comp = compute_composite_score(
        samples=samples,
        values=imputed_values if (use_imputed_for_score and imputed_points > 0) else values,
        window_s=int(window_s),
        missing_time_frac=missing_time_frac,
        overrides=overrides,
        peer_median=peer_median,
        peer_tol=_get_float(overrides, "spatial_tol", 0.0) if peer_median is not None else None,
        multivar_peers=multivar_peers if multivar_peers else None,
    )

    score_raw = base_score
    score_imputed = comp.score if (use_imputed_for_score and imputed_points > 0) else base_score
    score = float(comp.score)

    state = _state_from_score(score, stable_th, unstable_th)

    base["score"] = float(score)
    base["state"] = state

    meteo = _meteo_interpretation(
        state=state,
        score=float(score),
        n_points=n,
        missing_time_frac=missing_time_frac,
        gap_count=gap_count,
        gap_max_s=gap_max,
        watch_threshold=watch_threshold,
        alert_threshold=alert_threshold,
        imputed_frac=imputed_frac,
        max_imputed_frac=max_imputed_frac,
        signals=comp.signals,
        variable=variable,
    )

    report: dict[str, Any] = {}
    report.update(base)
    report.update(
        {
            "station_id": station_id,
            "variable": variable,
            "stream_id": msg_id,
            "ts_ingest": float(ts_ingest if ts_ingest is not None else time.time()),
            "signals": comp.signals,
            "contributions": comp.contributions,
            "score_meta": {"weights": comp.weights, "meta": comp.meta},
            "stats": {
                "n_points": int(n),
                "min": v_min,
                "max": v_max,
                "mean": v_mean,
                "p95": v_p95,
                "dt_median_s": float(dt_expected_s),
                "gap_threshold_s": float(gap_threshold),
                "gap_count": int(gap_count),
                "gap_max_s": gap_max,
                "gap_total_s": gap_total,
                "missing_time_s": missing_time_s,
                "missing_time_frac": missing_time_frac,
                "impute_mode": impute_mode,
                "imputed_points": int(imputed_points),
                "imputed_frac": imputed_frac,
                "score_raw": float(score_raw),
                "score_imputed": float(score_imputed),
                "use_imputed_for_score": bool(use_imputed_for_score),
                "window_s": int(window_s),
            },
            "meteo": meteo,
        }
    )
    return report


def run_live_worker(
    redis_url: str,
    in_stream: str,
    out_stream: str,
    cfg: LiveConfig | None = None,
    start_id: str | None = None,
    max_messages: int | None = None,
    max_idle_s: float | None = None,
) -> None:
    r = make_redis(redis_url)
    cfg = cfg or LiveConfig()

    # Initialise DB schema (no-op if DATABASE_URL is unset)
    _db.ensure_schema()

    station_cfg = load_station_config(env_config_path())

    windows: dict[tuple[str, str], RollingWindow] = {}
    peer_means: dict[str, dict[str, float]] = {}

    last_id = start_id if start_id is not None else _default_start_id()
    processed = 0
    last_progress = time.time()

    while True:
        resp_any = r.xread({in_stream: last_id}, block=1000, count=200)
        resp = cast(XReadResponse, resp_any)

        if not resp:
            if max_idle_s is not None and (time.time() - last_progress) > float(max_idle_s):
                return
            continue

        for _stream_name, messages in resp:
            for msg_id, fields in messages:
                last_id = msg_id

                report = process_observation(
                    fields,
                    msg_id=msg_id,
                    cfg=cfg,
                    windows=windows,
                    station_config=station_cfg,
                    peer_state=peer_means,
                )
                if report is None:
                    continue

                last_progress = time.time()
                processed += 1

                station_id = cast(str, report["station_id"])
                variable = cast(str, report["variable"])

                # Update peer stats for spatial consistency checks
                stats_any = report.get("stats", {})
                if isinstance(stats_any, dict):
                    m_any = stats_any.get("mean")
                    if m_any is None:
                        mean_val = None
                    else:
                        try:
                            mean_val = float(m_any)
                        except (TypeError, ValueError):
                            mean_val = None
                    if mean_val is not None:
                        peer_means.setdefault(variable, {})[station_id] = float(mean_val)

                payload = json.dumps(report, separators=(",", ":"), sort_keys=True)

                r.set(_latest_key(station_id, variable), payload)

                out_fields: dict[EncodableT, EncodableT] = {
                    "station_id": station_id,
                    "variable": variable,
                    "payload": payload,
                }
                r.xadd(out_stream, out_fields)

                _ = maybe_send_alert(report)

                # Persist to PostgreSQL (no-op when DATABASE_URL unset)
                _db.insert_report(report)

                if max_messages is not None and processed >= int(max_messages):
                    return
