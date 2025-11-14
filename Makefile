.PHONY: golden-files test test-local venv helm-lint

PYTHON ?= python3.14
VENV ?= .venv
PYTEST_ARGS ?=
GOLDEN_SCRIPT ?= scripts/regenerate_golden_files.py

$(VENV)/bin/python: requirements-dev.txt
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/python -m pip install --upgrade pip
	$(VENV)/bin/python -m pip install -r requirements-dev.txt

## venv: Create the local virtual environment with all dev dependencies.
venv: $(VENV)/bin/python

## test: Run the pytest suite (Helm must be available in PATH).
test: venv
	$(VENV)/bin/python -m pytest $(PYTEST_ARGS)

## golden-files: Re-render the golden manifests for every fixture values file.
golden-files:
	$(PYTHON) $(GOLDEN_SCRIPT)

## test-local: Run pytest without Helm network operations (no repo add/update or dependency build).
test-local: venv
	$(VENV)/bin/python -m pytest --skip-helm-network $(PYTEST_ARGS)

## helm-lint: Run helm lint across all charts, including lint_values files.
helm-lint:
	pre-commit run helmlint --all-files
