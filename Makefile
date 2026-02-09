PHONY: setup lint test run

setup:
	python -m pip install -U pip
	pip install -e ".[dev]"
	pre-commit install

lint:
	pre-commit run --all-files

test:
	pytest -q

run:
	meteovoid --help
