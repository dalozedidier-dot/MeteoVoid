# MeteoVoid CI lint fix patch

This patch fixes the CI failure seen in `logs_74250602436.zip`.

## What failed

The CI failed during `pre-commit` because:

1. `MeteoVoid_belgium_structural_hardening.diff` was present in the repository and the trailing-whitespace hook modified it.
2. `tools/validate_belgium_contracts.py` triggered Ruff `E402` because it modified `sys.path` before importing the validator.
3. `tools/generate_belgium_alert_report.py` needed Black/Ruff formatting after the structural hardening patch.

## Apply

Copy the files from this patch into the repository root, then run:

```bash
bash scripts/apply_ci_lint_fix.sh
```

Then commit the result:

```bash
git add tools/validate_belgium_contracts.py tools/generate_belgium_alert_report.py scripts/apply_ci_lint_fix.sh README_APPLY_CI_LINT_FIX.md
git rm -f MeteoVoid_belgium_structural_hardening.diff 2>/dev/null || true
git commit -m "ci: fix Belgium structural patch lint"
git push
```

## Notes

The `.diff` file from the previous patch is a delivery artefact, not source code. It should not stay in the repository root because pre-commit scans it.
