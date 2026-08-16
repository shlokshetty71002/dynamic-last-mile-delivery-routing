PYTHON ?= python3
MPLCONFIGDIR ?= data/cache/matplotlib
export MPLCONFIGDIR

ifeq ($(OS),Windows_NT)
VENV_BIN := .venv/Scripts
else
VENV_BIN := .venv/bin
endif

.PHONY: help setup test lint format ci clean experiment figures app reproduce

help:
	@echo "setup       Create .venv and install the pinned current environment"
	@echo "test        Run the automated tests"
	@echo "lint        Check code quality and formatting"
	@echo "format      Apply safe lint fixes and formatting"
	@echo "ci          Run the local equivalent of GitHub Actions"
	@echo "clean       Remove disposable Python caches (keeps data/results)"
	@echo "experiment  Run the 204-case real-network batch experiment"
	@echo "figures     Regenerate report figures from the tidy batch CSV"
	@echo "app         Launch the Streamlit interface"
	@echo "reproduce   Regenerate instances, tests, experiments, and figures"

setup:
	$(PYTHON) -m venv .venv
	$(VENV_BIN)/python -m pip install -r requirements.txt
	$(VENV_BIN)/python -m pip install --no-deps -e .

test:
	$(VENV_BIN)/python -m pytest

lint:
	$(VENV_BIN)/python -m ruff check .
	$(VENV_BIN)/python -m ruff format --check .

format:
	$(VENV_BIN)/python -m ruff check --fix .
	$(VENV_BIN)/python -m ruff format .

ci: lint test
	$(VENV_BIN)/python -m pip check

clean:
	$(VENV_BIN)/python -c "import pathlib, shutil; [shutil.rmtree(p) for p in pathlib.Path('.').rglob('__pycache__')]"
	$(VENV_BIN)/python -c "import pathlib, shutil; [shutil.rmtree(pathlib.Path(p), ignore_errors=True) for p in ('.pytest_cache', '.ruff_cache')]"

experiment:
	$(VENV_BIN)/dlm batch --random-runs 64 --random-edges 3 --jobs 4

figures:
	$(VENV_BIN)/dlm figures

app:
	$(VENV_BIN)/streamlit run app/main.py

reproduce:
	$(VENV_BIN)/python scripts/generate_report_instances.py
	$(MAKE) ci
	$(MAKE) experiment
	$(MAKE) figures
