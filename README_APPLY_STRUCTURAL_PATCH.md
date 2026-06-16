# Apply patch

Copy the contents of this zip at the root of the MeteoVoid repository, preserving paths.

Then run:

```bash
python -m pip install -e ".[dev,live]"
python -m compileall src tools tests
ruff check .
black --check tools tests src
pytest tests/test_belgium_contracts_and_cli.py tests/test_belgium_external_confirmation.py tests/test_belgium_operational_layer.py tests/test_belgium_extended_outputs.py --no-cov
```

Generate a local demo report and validate contracts:

```bash
python tools/generate_belgium_alert_report.py \
  --stations config/stations_belgium.yaml \
  --target-date 2026-06-19 \
  --offline-demo \
  --official-forecast-signal severe_thunderstorms \
  --heat-warning-active \
  --out-dir _ci_out/belgium_alert

python tools/validate_belgium_contracts.py _ci_out/belgium_alert
```
