# MeteoVoid alert_state contract fields fix

Run from the repository root:

```bash
python apply_alert_state_contract_fields.py
```

Then commit only the modified source file:

```bash
git status
git add tools/generate_belgium_alert_report.py
git commit -m "ci: emit Belgium alert state contract fields"
git push
```

Do not commit this patch script or this README. They are delivery files only.

The patch adds these keys to `alert_state.json`:

- `notification_allowed`
- `public_wording`
- `official_alert`

It also enriches `notification_state.json` with the same wording fields and keeps `public_alert_allowed` for backward compatibility.
