.PHONY: help venv install install-dev dev test test-cov lint format check ci-local release-local clean docs docs-serve docs-check

PYTHON ?= python3
VENV_DIR ?= .venv
VENV_BIN := $(VENV_DIR)/bin
VENV_PYTHON := $(VENV_BIN)/python
VENV_PIP := $(VENV_PYTHON) -m pip
SMOKE_VENV_DIR ?= .venv-smoke

help:
	@echo "llm-behavior-diff development commands"
	@echo ""
	@echo "  make venv       - Create/refresh .venv bootstrap"
	@echo "  make install    - Install package into .venv"
	@echo "  make install-dev - Install with dev dependencies into .venv"
	@echo "  make dev        - Alias for install-dev"
	@echo "  make test       - Run tests (pytest -q) in .venv"
	@echo "  make test-cov  - Run tests with coverage"
	@echo "  make lint       - Run linters (ruff, mypy) in .venv"
	@echo "  make format     - Format code with black in .venv"
	@echo "  make ci-local   - Local CI parity (ruff, black --check, mypy, pytest, mkdocs --strict)"
	@echo "  make release-local - Local release-check parity (build, twine check, wheel smoke)"
	@echo "  make check      - Alias for ci-local"
	@echo "  make clean      - Remove build artifacts"
	@echo "  make docs       - Build docs with mkdocs --strict in .venv"
	@echo "  make docs-serve - Serve docs locally via mkdocs"
	@echo "  make docs-check - Validate docs build in strict mode"

venv:
	@if [ ! -d "$(VENV_DIR)" ]; then $(PYTHON) -m venv $(VENV_DIR); fi
	$(VENV_PIP) install --upgrade pip

install: venv
	$(VENV_PIP) install -e .

install-dev: venv
	$(VENV_PIP) install -e ".[dev]"

dev: install-dev

test:
	$(VENV_BIN)/pytest -q

test-cov:
	$(VENV_BIN)/pytest tests/ -v --cov=src/llm_behavior_diff --cov-report=html --cov-report=term

lint:
	$(VENV_BIN)/ruff check src tests
	$(VENV_BIN)/mypy src

format:
	$(VENV_BIN)/black src tests

ci-local:
	$(VENV_BIN)/ruff check src tests
	$(VENV_BIN)/black --check src tests
	$(VENV_BIN)/mypy src
	$(VENV_BIN)/pytest -q
	$(VENV_BIN)/mkdocs build --strict

release-local:
	$(VENV_PIP) install --upgrade build twine
	$(VENV_PYTHON) -m build
	$(VENV_BIN)/twine check dist/*
	$(VENV_PYTHON) -m venv $(SMOKE_VENV_DIR)
	. $(SMOKE_VENV_DIR)/bin/activate && pip install --upgrade pip && pip install dist/*.whl && llm-diff --help

check: ci-local
	@echo "All checks passed!"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name ".coverage*" -delete
	rm -rf build/ dist/ *.egg-info htmlcov/ .mypy_cache/ .pytest_cache/ $(SMOKE_VENV_DIR)

docs:
	$(VENV_BIN)/mkdocs build --strict

docs-serve:
	$(VENV_BIN)/mkdocs serve

docs-check:
	$(VENV_BIN)/mkdocs build --strict

.DEFAULT_GOAL := help
