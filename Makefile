.PHONY: help install dev test lint format check clean docs docs-serve docs-check

help:
	@echo "llm-behavior-diff development commands"
	@echo ""
	@echo "  make install   - Install package"
	@echo "  make dev       - Install with dev dependencies"
	@echo "  make test      - Run tests"
	@echo "  make test-cov  - Run tests with coverage"
	@echo "  make lint      - Run linters (ruff, mypy)"
	@echo "  make format    - Format code with black"
	@echo "  make check     - Run all checks (lint, format, test)"
	@echo "  make clean     - Remove build artifacts"
	@echo "  make docs      - Build docs with mkdocs --strict"
	@echo "  make docs-serve - Serve docs locally via mkdocs"
	@echo "  make docs-check - Validate docs build in strict mode"

install:
	pip install -e .

dev:
	pip install -e ".[dev]"

test:
	pytest tests/ -v

test-cov:
	pytest tests/ -v --cov=src/llm_behavior_diff --cov-report=html --cov-report=term

lint:
	ruff check src/ tests/
	mypy src/

format:
	black src/ tests/

check: format lint test
	@echo "All checks passed!"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name ".coverage*" -delete
	rm -rf build/ dist/ *.egg-info htmlcov/ .mypy_cache/ .pytest_cache/

docs:
	mkdocs build --strict

docs-serve:
	mkdocs serve

docs-check:
	mkdocs build --strict

.DEFAULT_GOAL := help
