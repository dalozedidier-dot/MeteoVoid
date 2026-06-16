from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from meteovoid.belgium.contracts import ContractError, validate_output_directory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate MeteoVoid Belgium output contracts.")
    parser.add_argument("out_dir", nargs="?", default="_ci_out/belgium_alert")
    parser.add_argument("--json", action="store_true", help="Emit a machine-readable summary")
    args = parser.parse_args(argv)

    try:
        results = validate_output_directory(Path(args.out_dir))
    except ContractError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        else:
            print(f"contract validation failed: {exc}", file=sys.stderr)
        return 1

    summary = {name: True for name in results}
    if args.json:
        print(json.dumps({"ok": True, "checks": summary}, ensure_ascii=False, indent=2))
    else:
        for name in sorted(summary):
            print(f"ok: {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
