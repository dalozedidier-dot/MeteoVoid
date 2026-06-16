# MeteoVoid CI serious cleanup patch

Run this script once from the repository root:

```bash
python fix_meteovoid_ci_contract_cleanup.py
```

The script patches the real generator, removes old patch-delivery artifacts such as `apply_alert_state_contract_fields.py`, verifies the required `alert_state.json` fields, then deletes itself.

After it runs, commit only the actual repository changes:

```bash
git status
git add -A
git commit -m "ci: fix Belgium alert state contract cleanly"
git push
```

Do not commit this README or the script. They are deleted automatically after a successful run.
