# MeteoVoid final CI pre-commit fix

This patch fixes the CI failure visible in `logs_74254147277.zip`.

## What it fixes

- Removes `MeteoVoid_belgium_structural_hardening.diff`, which was a patch delivery artifact accidentally committed to the repo.
- Rewrites `tools/validate_belgium_contracts.py` in Black/Ruff-compliant format.
- Runs local compile, Ruff, Black and, when available, selected pre-commit hooks.

## Apply

From the repository root:

```bash
bash scripts/apply_final_ci_precommit_fix.sh
```

Then commit:

```bash
git status
git add tools/validate_belgium_contracts.py scripts/apply_final_ci_precommit_fix.sh README_APPLY_FINAL_CI_PRECOMMIT_FIX.md
git rm -f MeteoVoid_belgium_structural_hardening.diff 2>/dev/null || true
git commit -m "ci: remove patch artifact and format Belgium validator"
git push
```

Do not commit `.diff` patch artifacts into the repository.
