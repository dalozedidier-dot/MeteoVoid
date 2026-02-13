from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def _safe_float(x: Any) -> float | None:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _safe_int(x: Any) -> int | None:
    try:
        if x is None:
            return None
        return int(x)
    except Exception:
        return None


@dataclass(frozen=True)
class IncoherenceConfig:
    variables: dict[str, dict[str, Any]]
    severity: dict[str, float]


def load_incoherence_config(path: str | Path) -> IncoherenceConfig:
    """Load incoherence config from JSON.

    The file format is JSON-only on purpose, to keep CI tools dependency-free.
    """
    p = Path(path)
    obj = json.loads(p.read_text(encoding="utf-8"))

    if not isinstance(obj, dict):
        raise ValueError("incoherence config must be a JSON object")

    variables_any = obj.get("variables", {})
    if not isinstance(variables_any, dict):
        raise ValueError("incoherence config: 'variables' must be an object")

    severity_any = obj.get("severity", {})
    if not isinstance(severity_any, dict):
        raise ValueError("incoherence config: 'severity' must be an object")

    severity: dict[str, float] = {}
    for k, v in severity_any.items():
        if isinstance(k, str) and k and isinstance(v, int | float):
            severity[k] = float(v)

    # Safe defaults if missing
    if "medium" not in severity:
        severity["medium"] = 0.2
    if "high" not in severity:
        severity["high"] = 0.4

    variables: dict[str, dict[str, Any]] = {}
    for var, cfg in variables_any.items():
        if isinstance(var, str) and var and isinstance(cfg, dict):
            variables[var] = dict(cfg)

    return IncoherenceConfig(variables=variables, severity=severity)


def compute_incoherence_from_latest(
    *, latest: dict[str, Any], cfg: IncoherenceConfig
) -> dict[str, Any]:
    """Compute an incoherence score from a /latest-like payload.

    Components (phi in [0..1]):
    - gap: stats.missing_time_frac
    - range: exceedance of stats.min/stats.max vs configured plausible range
    - stuck: low dynamic range (max-min) vs eps_range

    Returns a dict that can be inserted as latest["incoherence"].
    """
    variable = latest.get("variable")
    if not isinstance(variable, str) or not variable:
        variable = "unknown"

    stats_any = latest.get("stats", {})
    stats: dict[str, Any] = stats_any if isinstance(stats_any, dict) else {}

    missing_time_frac = _safe_float(stats.get("missing_time_frac")) or 0.0
    vmin = _safe_float(stats.get("min"))
    vmax = _safe_float(stats.get("max"))
    n_points = _safe_int(stats.get("n_points")) or 0

    # Config resolution: variable-specific or fallback to "__default__"
    vcfg = cfg.variables.get(variable) or cfg.variables.get("__default__") or {}

    # Weights
    weights_any = vcfg.get("weights", {})
    weights: dict[str, float] = {"gap": 0.45, "range": 0.35, "stuck": 0.20}
    if isinstance(weights_any, dict):
        for k in ("gap", "range", "stuck"):
            w = weights_any.get(k)
            if isinstance(w, int | float):
                weights[k] = float(w)

    wsum = float(sum(weights.values()))
    if wsum <= 0.0:
        weights = {"gap": 1.0, "range": 0.0, "stuck": 0.0}
        wsum = 1.0

    phi_gap = _clamp01(float(missing_time_frac))

    # φ_range
    range_any = vcfg.get("range", {})
    lo = None
    hi = None
    if isinstance(range_any, dict):
        lo = _safe_float(range_any.get("min"))
        hi = _safe_float(range_any.get("max"))

    phi_range = 0.0
    range_notes: list[str] = []
    if lo is not None and hi is not None and hi > lo and vmin is not None and vmax is not None:
        span = hi - lo
        below = max(0.0, (lo - vmin) / span)
        above = max(0.0, (vmax - hi) / span)
        phi_range = _clamp01(below + above)
        if below > 0.0:
            range_notes.append("min_below_range")
        if above > 0.0:
            range_notes.append("max_above_range")

    # φ_stuck
    stuck_any = vcfg.get("stuck", {})
    eps_range = 0.0
    min_points = 30
    if isinstance(stuck_any, dict):
        er = stuck_any.get("eps_range")
        mp = stuck_any.get("min_points")
        if isinstance(er, int | float):
            eps_range = float(er)
        if isinstance(mp, int):
            min_points = mp

    phi_stuck = 0.0
    if eps_range > 0.0 and vmin is not None and vmax is not None and n_points >= min_points:
        observed_range = max(0.0, vmax - vmin)
        phi_stuck = _clamp01(1.0 - (observed_range / eps_range))

    score = (
        weights["gap"] * phi_gap + weights["range"] * phi_range + weights["stuck"] * phi_stuck
    ) / wsum
    score = _clamp01(score)

    med = float(cfg.severity.get("medium", 0.2))
    high = float(cfg.severity.get("high", 0.4))
    if score >= high:
        severity = "high"
    elif score >= med:
        severity = "medium"
    else:
        severity = "low"

    components = {"gap": phi_gap, "range": phi_range, "stuck": phi_stuck}

    meta: dict[str, Any] = {"range_notes": range_notes}
    if lo is not None and hi is not None:
        meta["expected_range"] = {"min": lo, "max": hi}
    if eps_range > 0.0:
        meta["stuck_eps_range"] = eps_range
        meta["stuck_min_points"] = min_points

    return {
        "score": score,
        "severity": severity,
        "components": components,
        "weights": weights,
        "meta": meta,
    }
