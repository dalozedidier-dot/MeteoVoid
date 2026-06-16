#!/usr/bin/env bash
set -euo pipefail

# MeteoVoid final CI/pre-commit fix.
# This removes patch delivery artifacts that must not be committed,
# then installs the Black/Ruff formatted Belgium contract validator.

ROOT="$(pwd)"

# The structural patch diff was a delivery artifact. If it is tracked, remove it.
if [ -f "MeteoVoid_belgium_structural_hardening.diff" ]; then
  git rm -f "MeteoVoid_belgium_structural_hardening.diff" 2>/dev/null || rm -f "MeteoVoid_belgium_structural_hardening.diff"
fi

# Remove any older patch diff artifacts that were accidentally extracted.
find . -maxdepth 2 -type f \( \
  -name "MeteoVoid_*structural*.diff" -o \
  -name "MeteoVoid_*patch*.diff" -o \
  -name "*_structural_hardening.diff" \
\) -print -delete

mkdir -p tools
cat > tools/validate_belgium_contracts.py <<'PY'
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path


def _load_contract_validator() -> (
    tuple[type[Exception], Callable[[Path], dict[str, object]]]
):
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    from meteovoid.belgium.contracts import ContractError, validate_output_directory

    return ContractError, validate_output_directory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate MeteoVoid Belgium output contracts."
    )
    parser.add_argument("out_dir", nargs="?", default="_ci_out/belgium_alert")
    parser.add_argument(
        "--json", action="store_true", help="Emit a machine-readable summary"
    )
    args = parser.parse_args(argv)

    contract_error, validate_output_directory = _load_contract_validator()
    try:
        results = validate_output_directory(Path(args.out_dir))
    except contract_error as exc:
        if args.json:
            print(
                json.dumps(
                    {"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2
                )
            )
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

PY

python -m compileall tools/validate_belgium_contracts.py >/dev/null

if command -v ruff >/dev/null 2>&1; then
  ruff check tools/validate_belgium_contracts.py
fi

if command -v black >/dev/null 2>&1; then
  black --check tools/validate_belgium_contracts.py
fi

if command -v pre-commit >/dev/null 2>&1; then
  pre-commit run trailing-whitespace --all-files
  pre-commit run ruff --all-files
  pre-commit run ruff-format --all-files
  pre-commit run black --all-files
fi

echo "Final CI pre-commit fix applied. Review with: git status && pre-commit run --all-files"
