# MeteoVoid CI artifact cleanup fix

The CI logs show two remaining pre-commit blockers:

1. `MeteoVoid_belgium_structural_hardening.diff` is still committed. It is a patch-delivery artifact, not source code. `pre-commit` scans it and fails on trailing whitespace.
2. `tools/validate_belgium_contracts.py` is not exactly formatted as expected by `ruff-format` and `black`.

## Apply

Extract this patch at the repository root, then run:

```bash
bash scripts/apply_ci_artifact_cleanup_fix.sh
```

Then commit:

```bash
git status
git add tools/validate_belgium_contracts.py scripts/apply_ci_artifact_cleanup_fix.sh README_APPLY_CI_ARTIFACT_CLEANUP_FIX.md
git rm -f MeteoVoid_belgium_structural_hardening.diff 2>/dev/null || true
git commit -m "ci: remove patch artifact and normalize Belgium contract validator"
git push
```

## Important

Do not commit `.diff` patch-delivery files in the repository. They are useful for handoff only and should stay outside source control.
