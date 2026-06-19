.PHONY: setup lint test test-fast clean run belgium-geodata-offline belgium-5days-offline belgium-alert-offline belgium-site-demo

setup:
	python -m pip install -U pip
	pip install -e ".[dev,live,viz]"
	pre-commit install

lint:
	pre-commit run --all-files

test:
	pytest -q

test-fast:
	pytest --no-cov -q

clean:
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	find . -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage htmlcov _ci_out _site _site_test _sample_out

run:
	meteovoid --help

belgium-geodata-offline:
	python tools/prepare_belgium_geodata.py --out-dir _ci_out/belgium_alert --offline

belgium-5days-offline:
	python tools/generate_belgium_5day_bulletin.py --out-dir _ci_out/belgium_alert --offline-demo --days 5

belgium-alert-offline: belgium-geodata-offline
	python tools/generate_belgium_alert_report.py \
		--stations config/stations_belgium.yaml \
		--target-date auto \
		--out-dir _ci_out/belgium_alert \
		--history-dir _ci_out/belgium_alert/history \
		--offline-demo \
		--province-geojson _ci_out/belgium_alert/belgium_boundaries_provinces.geojson
	python tools/generate_belgium_5day_bulletin.py --out-dir _ci_out/belgium_alert --offline-demo --days 5
	python tools/update_belgium_validation_history.py \
		--report _ci_out/belgium_alert/belgium_alert_report.json \
		--history-dir _ci_out/belgium_alert/validation \
		--verified-events config/belgium_verified_storm_events.csv \
		--out-dir _ci_out/belgium_alert

belgium-site-demo: belgium-alert-offline
	python tools/build_belgium_public_site.py --report-dir _ci_out/belgium_alert --site-dir _site
