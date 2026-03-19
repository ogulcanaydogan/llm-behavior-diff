"""Validation and smoke tests for built-in suite YAML files."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from llm_behavior_diff.cli import main
from llm_behavior_diff.runner import load_test_suite

SUITES_DIR = Path(__file__).resolve().parents[1] / "suites"
ALL_SUITE_FILES = sorted(SUITES_DIR.glob("*.yaml"))
NEW_SUITE_FILES = [
    SUITES_DIR / "safety_boundaries.yaml",
    SUITES_DIR / "coding_tasks.yaml",
    SUITES_DIR / "reasoning.yaml",
]



def test_expected_suite_files_present() -> None:
    expected = {
        "general_knowledge.yaml",
        "instruction_following.yaml",
        "safety_boundaries.yaml",
        "coding_tasks.yaml",
        "reasoning.yaml",
    }
    found = {path.name for path in ALL_SUITE_FILES}
    assert expected.issubset(found)


@pytest.mark.parametrize("suite_path", ALL_SUITE_FILES, ids=lambda path: path.name)
def test_suite_yaml_validates_and_has_sane_cases(suite_path: Path) -> None:
    suite = load_test_suite(suite_path)

    assert len(suite.test_cases) >= 10

    test_ids = [test_case.id for test_case in suite.test_cases]
    assert len(test_ids) == len(set(test_ids))

    for test_case in suite.test_cases:
        assert test_case.prompt.strip()
        assert test_case.expected_behavior.strip()
        assert test_case.max_tokens > 0
        assert 0.0 <= test_case.temperature <= 1.0


@pytest.mark.parametrize("suite_path", NEW_SUITE_FILES, ids=lambda path: path.name)
def test_new_suite_has_exactly_ten_cases(suite_path: Path) -> None:
    suite = load_test_suite(suite_path)
    assert len(suite.test_cases) == 10


@pytest.mark.parametrize("suite_path", NEW_SUITE_FILES, ids=lambda path: path.name)
def test_cli_dry_run_smoke_for_new_suites(suite_path: Path) -> None:
    result = CliRunner().invoke(
        main,
        [
            "run",
            "--model-a",
            "gpt-4o",
            "--model-b",
            "gpt-4.5",
            "--suite",
            str(suite_path),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "Suite is valid" in result.output
