"""CLI command tests for run/report/compare paths."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from llm_behavior_diff.cli import main
from llm_behavior_diff.schema import BehaviorCategory, BehaviorReport, DiffResult


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_run_dry_run_success(tmp_path: Path) -> None:
    suite_path = _write(
        tmp_path / "suite.yaml",
        """
name: dry_run_suite
description: simple suite
test_cases:
  - id: test_1
    prompt: "hello"
    category: formatting
    expected_behavior: Should say hello
""".strip(),
    )

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


def test_run_dry_run_invalid_suite_fails(tmp_path: Path) -> None:
    suite_path = _write(tmp_path / "invalid.yaml", "name: [invalid")

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

    assert result.exit_code != 0
    assert "Invalid YAML" in result.output


def test_run_writes_json_report_with_mocked_runner(tmp_path: Path, monkeypatch) -> None:
    suite_path = _write(
        tmp_path / "suite.yaml",
        """
name: run_suite
description: run suite
test_cases:
  - id: test_1
    prompt: "hello"
    category: factual_knowledge
    expected_behavior: Should answer hello
""".strip(),
    )
    output_path = tmp_path / "report.json"
    captured: dict[str, object] = {}

    class FakeRunner:
        def __init__(
            self,
            model_a: str,
            model_b: str,
            judge_model: str | None = None,
            max_workers: int = 4,
            continue_on_error: bool = False,
            max_retries: int = 3,
            rate_limit_rps: float = 0.0,
            pricing_file: str | None = None,
        ) -> None:
            self.model_a = model_a
            self.model_b = model_b
            self.max_workers = max_workers
            captured["continue_on_error"] = continue_on_error
            captured["max_retries"] = max_retries
            captured["rate_limit_rps"] = rate_limit_rps
            captured["pricing_file"] = pricing_file
            captured["judge_model"] = judge_model

        async def run_suite(self, suite_obj):
            return BehaviorReport(
                model_a=self.model_a,
                model_b=self.model_b,
                suite_name=suite_obj.name,
                total_tests=len(suite_obj.test_cases),
                total_diffs=1,
                regressions=0,
                improvements=1,
                duration_seconds=0.1,
                metadata={"estimated_cost_usd": {"total": 0.00042}, "pricing_source": "builtin"},
            )

    monkeypatch.setattr("llm_behavior_diff.cli.BehaviorDiffRunner", FakeRunner)

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
            "--output",
            str(output_path),
            "--continue-on-error",
            "--max-retries",
            "5",
            "--rate-limit-rps",
            "2.5",
            "--judge-model",
            "gpt-4o-mini",
        ],
    )

    assert result.exit_code == 0
    assert output_path.exists()

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["model_a"] == "gpt-4o"
    assert payload["model_b"] == "gpt-4.5"
    assert payload["suite_name"] == "run_suite"
    assert payload["improvements"] == 1
    assert payload["metadata"]["estimated_cost_usd"]["total"] == 0.00042
    assert captured["continue_on_error"] is True
    assert captured["max_retries"] == 5
    assert captured["rate_limit_rps"] == 2.5
    assert captured["judge_model"] == "gpt-4o-mini"


def test_compare_prints_delta_and_writes_markdown(tmp_path: Path) -> None:
    report_a_path = tmp_path / "report_a.json"
    report_b_path = tmp_path / "report_b.json"
    compare_md_path = tmp_path / "compare.md"

    report_a = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite",
        total_tests=10,
        total_diffs=4,
        regressions=3,
        improvements=1,
        duration_seconds=10.0,
        metadata={"estimated_cost_usd": {"total": 0.12}},
    )
    report_b = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite",
        total_tests=10,
        total_diffs=2,
        regressions=1,
        improvements=2,
        duration_seconds=8.0,
        metadata={"estimated_cost_usd": {"total": 0.08}},
    )

    report_a_path.write_text(
        json.dumps(report_a.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    report_b_path.write_text(
        json.dumps(report_b.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        main,
        [
            "compare",
            str(report_a_path),
            str(report_b_path),
            "--output",
            str(compare_md_path),
        ],
    )

    assert result.exit_code == 0
    assert "Behavioral Diff Run Comparison" in result.output
    assert compare_md_path.exists()
    compare_content = compare_md_path.read_text(encoding="utf-8")
    assert "# Behavioral Diff Comparison" in compare_content
    assert "| Regressions | 3 | 1 | -2 |" in compare_content
    assert "Estimated Cost (USD)" in compare_content


def test_report_table_and_markdown_include_significance_when_available(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    markdown_path = tmp_path / "report.md"
    report = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite",
        total_tests=10,
        total_diffs=2,
        regressions=1,
        improvements=1,
        duration_seconds=3.2,
        metadata={
            "significance": {
                "method": "bootstrap",
                "confidence_level": 0.95,
                "resamples": 5000,
                "seed": 42,
                "sample_size": 10,
                "regression_rate": {
                    "point": 0.1,
                    "ci_low": 0.0,
                    "ci_high": 0.3,
                    "p_value_two_sided": 0.2,
                },
                "improvement_rate": {
                    "point": 0.1,
                    "ci_low": 0.0,
                    "ci_high": 0.3,
                    "p_value_two_sided": 0.2,
                },
            }
        },
    )
    report_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    table_result = CliRunner().invoke(main, ["report", str(report_path), "--format", "table"])
    assert table_result.exit_code == 0
    assert "Regression Rate CI (95%)" in table_result.output
    assert "Improvement Rate CI (95%)" in table_result.output

    md_result = CliRunner().invoke(
        main,
        ["report", str(report_path), "--format", "markdown", "--output", str(markdown_path)],
    )
    assert md_result.exit_code == 0
    markdown_content = markdown_path.read_text(encoding="utf-8")
    assert "Regression Rate CI (95%)" in markdown_content
    assert "Improvement Rate CI (95%)" in markdown_content


def test_compare_includes_significance_rows_when_diff_results_available(tmp_path: Path) -> None:
    report_a_path = tmp_path / "sig_a.json"
    report_b_path = tmp_path / "sig_b.json"
    compare_md_path = tmp_path / "sig_compare.md"

    diff_results_a = [
        DiffResult(
            test_id=f"a_{idx}",
            model_a="gpt-4o",
            model_b="gpt-4.5",
            response_a="a",
            response_b="b",
            is_semantically_same=False,
            semantic_similarity=0.2,
            behavior_category=BehaviorCategory.KNOWLEDGE_CHANGE,
            is_regression=False,
            is_improvement=False,
        )
        for idx in range(10)
    ]
    diff_results_b = [
        DiffResult(
            test_id=f"b_{idx}",
            model_a="gpt-4o",
            model_b="gpt-4.5",
            response_a="a",
            response_b="b",
            is_semantically_same=False,
            semantic_similarity=0.2,
            behavior_category=BehaviorCategory.KNOWLEDGE_CHANGE,
            is_regression=True,
            is_improvement=False,
        )
        for idx in range(10)
    ]

    report_a = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite",
        total_tests=10,
        total_diffs=0,
        regressions=0,
        improvements=0,
        duration_seconds=1.0,
        diff_results=diff_results_a,
    )
    report_b = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite",
        total_tests=10,
        total_diffs=10,
        regressions=10,
        improvements=0,
        duration_seconds=1.0,
        diff_results=diff_results_b,
    )

    report_a_path.write_text(
        json.dumps(report_a.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    report_b_path.write_text(
        json.dumps(report_b.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        main,
        ["compare", str(report_a_path), str(report_b_path), "--output", str(compare_md_path)],
    )
    assert result.exit_code == 0
    assert "Regression Delta CI (95%)" in result.output
    assert "Improvement Delta CI (95%)" in result.output
    compare_content = compare_md_path.read_text(encoding="utf-8")
    assert "Regression Delta Significant?" in compare_content
    assert "Improvement Delta Significant?" in compare_content
