from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _is_detected(row: dict[str, str]) -> bool:
    level = row.get("operational_level", "")
    try:
        score = float(row.get("national_score") or 0.0)
    except ValueError:
        score = 0.0
    return level in {"watch_reinforced", "pre_alert_confirmed", "alert_confirmed"} or score >= 0.65


def _event_positive(event: dict[str, str]) -> bool:
    return (event.get("expected") or "").strip().lower() in {
        "event",
        "alert",
        "severe",
        "positive",
    }


def _row_in_window(row: dict[str, str], event: dict[str, str]) -> bool:
    target_start = row.get("target_start") or row.get("generated_at") or ""
    target_end = row.get("target_end") or target_start
    start = event.get("start_date") or ""
    end = event.get("end_date") or start
    return bool(start and target_start <= end and target_end >= start)


def replay(history_csv: Path, events_csv: Path) -> dict[str, Any]:
    rows = _read_csv(history_csv)
    events = _read_csv(events_csv)
    comparisons: list[dict[str, Any]] = []
    counts = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for event in events:
        matched_rows = [row for row in rows if _row_in_window(row, event)]
        detected = any(_is_detected(row) for row in matched_rows)
        expected = _event_positive(event)
        if detected and expected:
            verdict = "true_positive"
            counts["tp"] += 1
        elif detected and not expected:
            verdict = "false_positive_candidate"
            counts["fp"] += 1
        elif not detected and expected:
            verdict = "false_negative_candidate"
            counts["fn"] += 1
        else:
            verdict = "true_negative"
            counts["tn"] += 1
        peak_score = 0.0
        if matched_rows:
            peak_score = max(float(row.get("national_score") or 0.0) for row in matched_rows)
        comparisons.append(
            {
                "event_id": event.get("event_id"),
                "start_date": event.get("start_date"),
                "end_date": event.get("end_date"),
                "expected": event.get("expected"),
                "phenomenon": event.get("phenomenon"),
                "matched_run_count": len(matched_rows),
                "detected": detected,
                "peak_score": round(peak_score, 6),
                "verdict": verdict,
            }
        )
    precision = (
        counts["tp"] / (counts["tp"] + counts["fp"]) if counts["tp"] + counts["fp"] else None
    )
    recall = counts["tp"] / (counts["tp"] + counts["fn"]) if counts["tp"] + counts["fn"] else None
    return {
        "history_csv": str(history_csv),
        "events_csv": str(events_csv),
        "history_rows": len(rows),
        "event_count": len(events),
        "counts": counts,
        "precision": precision,
        "recall": recall,
        "comparisons": comparisons,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replay MeteoVoid Belgium alert history against known events"
    )
    parser.add_argument("--history", default="_ci_out/belgium_alert/history.csv")
    parser.add_argument("--events", default="config/belgium_replay_events.example.csv")
    parser.add_argument("--out", default="_ci_out/belgium_alert/replay_history_summary.json")
    args = parser.parse_args()
    result = replay(Path(args.history), Path(args.events))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
