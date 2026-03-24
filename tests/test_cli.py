"""CLI command tests for run/report/compare paths."""

from __future__ import annotations

import csv
import io
import json
import xml.etree.ElementTree as ET
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
            factual_connector: str = "none",
            factual_connector_timeout: float = 8.0,
            factual_connector_max_results: int = 3,
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
            captured["factual_connector"] = factual_connector
            captured["factual_connector_timeout"] = factual_connector_timeout
            captured["factual_connector_max_results"] = factual_connector_max_results

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
            "--factual-connector",
            "wikipedia",
            "--factual-connector-timeout",
            "9.5",
            "--factual-connector-max-results",
            "5",
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
    assert captured["factual_connector"] == "wikipedia"
    assert captured["factual_connector_timeout"] == 9.5
    assert captured["factual_connector_max_results"] == 5


def test_run_accepts_prefixed_model_ids(tmp_path: Path, monkeypatch) -> None:
    suite_path = _write(
        tmp_path / "suite.yaml",
        """
name: prefixed_suite
description: prefixed model ids
test_cases:
  - id: test_1
    prompt: "hello"
    category: factual_knowledge
    expected_behavior: Should answer hello
""".strip(),
    )
    output_path = tmp_path / "report_prefixed.json"
    captured: dict[str, object] = {}

    class FakeRunner:
        def __init__(
            self,
            model_a: str,
            model_b: str,
            judge_model: str | None = None,
            factual_connector: str = "none",
            factual_connector_timeout: float = 8.0,
            factual_connector_max_results: int = 3,
            max_workers: int = 4,
            continue_on_error: bool = False,
            max_retries: int = 3,
            rate_limit_rps: float = 0.0,
            pricing_file: str | None = None,
        ) -> None:
            captured["model_a"] = model_a
            captured["model_b"] = model_b
            captured["judge_model"] = judge_model
            captured["factual_connector"] = factual_connector
            captured["factual_connector_timeout"] = factual_connector_timeout
            captured["factual_connector_max_results"] = factual_connector_max_results
            del max_workers, continue_on_error, max_retries, rate_limit_rps, pricing_file

        async def run_suite(self, suite_obj):
            return BehaviorReport(
                model_a=captured["model_a"],
                model_b=captured["model_b"],
                suite_name=suite_obj.name,
                total_tests=len(suite_obj.test_cases),
                total_diffs=0,
                regressions=0,
                improvements=0,
                duration_seconds=0.1,
            )

    monkeypatch.setattr("llm_behavior_diff.cli.BehaviorDiffRunner", FakeRunner)

    result = CliRunner().invoke(
        main,
        [
            "run",
            "--model-a",
            "litellm:openai/gpt-4o-mini",
            "--model-b",
            "local:llama3.1",
            "--judge-model",
            "litellm:openai/gpt-4o-nano",
            "--suite",
            str(suite_path),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0
    assert captured["model_a"] == "litellm:openai/gpt-4o-mini"
    assert captured["model_b"] == "local:llama3.1"
    assert captured["judge_model"] == "litellm:openai/gpt-4o-nano"
    assert captured["factual_connector"] == "none"


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


def test_gate_strict_pass_returns_zero(tmp_path: Path) -> None:
    report_path = tmp_path / "gate_pass.json"
    report = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite",
        total_tests=10,
        total_diffs=0,
        regressions=0,
        improvements=0,
        duration_seconds=1.0,
    )
    report_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    result = CliRunner().invoke(main, ["gate", str(report_path), "--policy", "strict"])
    assert result.exit_code == 0
    assert "Gate passed" in result.output


def test_gate_strict_fail_returns_two(tmp_path: Path) -> None:
    report_path = tmp_path / "gate_fail.json"
    report = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite",
        total_tests=10,
        total_diffs=1,
        regressions=1,
        improvements=0,
        duration_seconds=1.0,
    )
    report_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    result = CliRunner().invoke(main, ["gate", str(report_path), "--policy", "strict"])
    assert result.exit_code == 2
    assert "Gate failed" in result.output


def test_gate_json_output_writes_file(tmp_path: Path) -> None:
    report_path = tmp_path / "gate_json.json"
    output_path = tmp_path / "gate_result.json"
    report = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite",
        total_tests=100,
        total_diffs=2,
        regressions=2,
        improvements=0,
        duration_seconds=1.0,
    )
    report_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    result = CliRunner().invoke(
        main,
        [
            "gate",
            str(report_path),
            "--policy",
            "balanced",
            "--format",
            "json",
            "--output",
            str(output_path),
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["policy"] == "balanced"
    assert payload["policy_pack"] == "core"
    assert payload["policy_source"] == "builtin:core"
    assert payload["passed"] is True
    assert payload["thresholds"]["allowed_regressions"] == 2


def test_gate_with_policy_pack_affects_decision(tmp_path: Path) -> None:
    report_path = tmp_path / "gate_pack.json"
    output_path = tmp_path / "gate_pack_result.json"
    report = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite",
        total_tests=100,
        total_diffs=2,
        regressions=2,
        improvements=0,
        duration_seconds=1.0,
    )
    report_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    result = CliRunner().invoke(
        main,
        [
            "gate",
            str(report_path),
            "--policy",
            "balanced",
            "--policy-pack",
            "risk_averse",
            "--format",
            "json",
            "--output",
            str(output_path),
        ],
    )
    assert result.exit_code == 2
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["policy_pack"] == "risk_averse"
    assert payload["thresholds"]["allowed_regressions"] == 1


def test_gate_with_policy_file_takes_precedence(tmp_path: Path) -> None:
    report_path = tmp_path / "gate_custom_file.json"
    policy_path = tmp_path / "custom_policy.yaml"
    output_path = tmp_path / "gate_custom_result.json"
    report = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite",
        total_tests=10,
        total_diffs=3,
        regressions=3,
        improvements=0,
        duration_seconds=1.0,
    )
    policy_path.write_text(
        """
version: v1
name: custom_relaxed
tiers:
  strict:
    allowed_regressions:
      type: absolute
      value: 5
    critical_category_max: {}
  balanced:
    allowed_regressions:
      type: percent_floor
      percent: 0.10
      floor: 1
    critical_category_max: {}
  permissive:
    allowed_regressions:
      type: percent_floor
      percent: 0.20
      floor: 2
    critical_category_max: {}
""".strip() + "\n",
        encoding="utf-8",
    )
    report_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    result = CliRunner().invoke(
        main,
        [
            "gate",
            str(report_path),
            "--policy",
            "strict",
            "--policy-pack",
            "risk_averse",
            "--policy-file",
            str(policy_path),
            "--format",
            "json",
            "--output",
            str(output_path),
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["passed"] is True
    assert payload["policy_pack"] == "custom_relaxed"
    assert str(payload["policy_source"]).startswith("file:")


def test_gate_invalid_policy_file_returns_usage_error_code_one(tmp_path: Path) -> None:
    report_path = tmp_path / "gate_invalid_policy.json"
    policy_path = tmp_path / "invalid_policy.yaml"
    report = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite",
        total_tests=10,
        total_diffs=0,
        regressions=0,
        improvements=0,
        duration_seconds=1.0,
    )
    policy_path.write_text(
        """
version: v1
tiers:
  strict:
    allowed_regressions:
      type: absolute
      value: 0
    critical_category_max: {}
""".strip() + "\n",
        encoding="utf-8",
    )
    report_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    result = CliRunner().invoke(
        main,
        [
            "gate",
            str(report_path),
            "--policy-file",
            str(policy_path),
        ],
    )
    assert result.exit_code == 1
    assert "Error evaluating policy" in result.output


def test_gate_invalid_report_fails_with_usage_error_code_one(tmp_path: Path) -> None:
    report_path = tmp_path / "invalid_report.json"
    report_path.write_text("{invalid json", encoding="utf-8")

    result = CliRunner().invoke(main, ["gate", str(report_path)])
    assert result.exit_code == 1
    assert "Error loading report" in result.output


def test_benchmark_table_json_markdown_outputs_and_advisory_exit_code_zero(tmp_path: Path) -> None:
    report_a_path = tmp_path / "benchmark_a.json"
    report_b_path = tmp_path / "benchmark_b.json"
    summary_json_path = tmp_path / "benchmark_summary.json"
    summary_md_path = tmp_path / "benchmark_summary.md"

    report_a = BehaviorReport(
        id="report-a",
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite_a",
        total_tests=10,
        total_diffs=2,
        regressions=0,
        improvements=0,
        semantic_only_diffs=0,
        duration_seconds=10.0,
        metadata={"processed_tests": 10, "failed_tests": 0},
    )
    report_b = BehaviorReport(
        id="report-b",
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite_b",
        total_tests=8,
        total_diffs=2,
        regressions=1,
        improvements=0,
        semantic_only_diffs=0,
        duration_seconds=80.0,
        regression_by_category={
            BehaviorCategory.SAFETY_BOUNDARY: 1,
            BehaviorCategory.HALLUCINATION_NEW: 1,
        },
        metadata={"processed_tests": 7, "failed_tests": 1},
    )
    report_a_path.write_text(
        json.dumps(report_a.model_dump(mode="json"), indent=2), encoding="utf-8"
    )
    report_b_path.write_text(
        json.dumps(report_b.model_dump(mode="json"), indent=2), encoding="utf-8"
    )

    table_result = CliRunner().invoke(main, ["benchmark", str(report_a_path), str(report_b_path)])
    assert table_result.exit_code == 0
    assert "Benchmark Summary (Advisory-Only)" in table_result.output
    assert "Quality Pack Advisories" in table_result.output

    json_result = CliRunner().invoke(
        main,
        [
            "benchmark",
            str(report_a_path),
            str(report_b_path),
            "--format",
            "json",
            "--output",
            str(summary_json_path),
        ],
    )
    assert json_result.exit_code == 0
    summary_payload = json.loads(summary_json_path.read_text(encoding="utf-8"))
    assert summary_payload["quality_pack"]["advisory_only"] is True
    assert summary_payload["total_reports"] == 2
    assert summary_payload["total_failed_tests"] == 1
    assert summary_payload["source_reports"] == [str(report_a_path), str(report_b_path)]

    markdown_result = CliRunner().invoke(
        main,
        [
            "benchmark",
            str(report_a_path),
            str(report_b_path),
            "--format",
            "markdown",
            "--output",
            str(summary_md_path),
        ],
    )
    assert markdown_result.exit_code == 0
    markdown_content = summary_md_path.read_text(encoding="utf-8")
    assert "# Benchmark Summary" in markdown_content
    assert "Mode: advisory-only" in markdown_content
    assert "| Suite | Tests | Processed | Failed |" in markdown_content
    assert "high_unknown_rate" in markdown_content


def test_benchmark_requires_at_least_one_report_path() -> None:
    result = CliRunner().invoke(main, ["benchmark"])
    assert result.exit_code == 1
    assert "At least one report JSON file is required." in result.output


def test_benchmark_invalid_report_fails_with_usage_error_code_one(tmp_path: Path) -> None:
    report_path = tmp_path / "invalid_benchmark_report.json"
    report_path.write_text("{invalid json", encoding="utf-8")

    result = CliRunner().invoke(main, ["benchmark", str(report_path)])
    assert result.exit_code == 1
    assert "Error loading report" in result.output


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
                "rate_interval_methods": ["bootstrap", "wilson"],
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
                "regression_rate_wilson": {
                    "point": 0.1,
                    "ci_low": 0.02,
                    "ci_high": 0.32,
                },
                "improvement_rate_wilson": {
                    "point": 0.1,
                    "ci_low": 0.02,
                    "ci_high": 0.32,
                },
            }
        },
    )
    report_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    table_result = CliRunner().invoke(main, ["report", str(report_path), "--format", "table"])
    assert table_result.exit_code == 0
    assert "Regression Rate CI (95%)" in table_result.output
    assert "Improvement Rate CI (95%)" in table_result.output
    assert "Regression Rate Wilson CI (95%)" in table_result.output
    assert "Improvement Rate Wilson CI (95%)" in table_result.output

    md_result = CliRunner().invoke(
        main,
        ["report", str(report_path), "--format", "markdown", "--output", str(markdown_path)],
    )
    assert md_result.exit_code == 0
    markdown_content = markdown_path.read_text(encoding="utf-8")
    assert "Regression Rate CI (95%)" in markdown_content
    assert "Improvement Rate CI (95%)" in markdown_content
    assert "Regression Rate Wilson CI (95%)" in markdown_content
    assert "Improvement Rate Wilson CI (95%)" in markdown_content


def test_report_html_contains_interactive_explorer_markers(tmp_path: Path) -> None:
    report_path = tmp_path / "interactive_report.json"
    html_path = tmp_path / "interactive_report.html"
    diff_results = [
        DiffResult(
            test_id="t_1",
            model_a="gpt-4o",
            model_b="gpt-4.5",
            response_a="A",
            response_b="B",
            is_semantically_same=False,
            semantic_similarity=0.12,
            behavior_category=BehaviorCategory.INSTRUCTION_FOLLOWING,
            is_regression=True,
            is_improvement=False,
            confidence=0.87,
            explanation="B fails formatting constraints.",
            metadata={"comparators": {"semantic": {"decision": "semantic_diff"}}},
        )
    ]
    report = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite",
        total_tests=1,
        total_diffs=1,
        regressions=1,
        improvements=0,
        duration_seconds=1.5,
        diff_results=diff_results,
        regression_by_category={BehaviorCategory.INSTRUCTION_FOLLOWING: 1},
        metadata={
            "estimated_cost_usd": {"total": 0.12345678},
            "pricing_source": "builtin",
            "processed_tests": 1,
            "failed_tests": 0,
            "significance": {
                "method": "bootstrap",
                "confidence_level": 0.95,
                "resamples": 5000,
                "seed": 42,
                "sample_size": 1,
                "regression_rate": {
                    "point": 1.0,
                    "ci_low": 1.0,
                    "ci_high": 1.0,
                    "p_value_two_sided": 0.0,
                },
                "improvement_rate": {
                    "point": 0.0,
                    "ci_low": 0.0,
                    "ci_high": 0.0,
                    "p_value_two_sided": 1.0,
                },
            },
        },
    )
    report_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    result = CliRunner().invoke(
        main,
        ["report", str(report_path), "--format", "html", "--output", str(html_path)],
    )

    assert result.exit_code == 0
    html_content = html_path.read_text(encoding="utf-8")
    assert 'data-test="kpi-cards"' in html_content
    assert 'data-test="explorer-filters"' in html_content
    assert 'data-test="diff-explorer-table"' in html_content
    assert 'data-test="details-panel"' in html_content
    assert "const diffData = [" in html_content
    assert "Estimated Cost (USD)" in html_content
    assert "bootstrap (CL=0.95, B=5000, seed=42)" in html_content


def test_report_html_handles_empty_diff_rows_and_missing_metadata(tmp_path: Path) -> None:
    report_path = tmp_path / "empty_report.json"
    html_path = tmp_path / "empty_report.html"
    report = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite",
        total_tests=0,
        total_diffs=0,
        regressions=0,
        improvements=0,
        duration_seconds=0.0,
        diff_results=[],
        metadata={},
    )
    report_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    result = CliRunner().invoke(
        main,
        ["report", str(report_path), "--format", "html", "--output", str(html_path)],
    )

    assert result.exit_code == 0
    html_content = html_path.read_text(encoding="utf-8")
    assert "No diff rows for this report." in html_content
    assert ">N/A<" in html_content
    assert 'data-test="diff-explorer-table"' in html_content


def test_report_csv_ndjson_and_junit_exports(tmp_path: Path) -> None:
    report_path = tmp_path / "export_report.json"
    csv_path = tmp_path / "report.csv"
    ndjson_path = tmp_path / "report.ndjson"
    junit_path = tmp_path / "report.junit.xml"

    diff_result = DiffResult(
        test_id="export_001",
        model_a="gpt-4o",
        model_b="gpt-4.5",
        response_a="Response A body should only appear in ndjson.",
        response_b="Response B body should only appear in ndjson.",
        is_semantically_same=False,
        semantic_similarity=0.22,
        behavior_category=BehaviorCategory.FORMAT_CHANGE,
        is_regression=True,
        is_improvement=False,
        confidence=0.91,
        explanation="Candidate failed strict formatting output.",
        metadata={"comparators": {"format": {"decision": "format_regression"}}},
    )
    report = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite_exports",
        total_tests=1,
        total_diffs=1,
        regressions=1,
        improvements=0,
        duration_seconds=0.7,
        diff_results=[diff_result],
    )
    report_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    csv_result = CliRunner().invoke(
        main,
        ["report", str(report_path), "--format", "csv", "--output", str(csv_path)],
    )
    assert csv_result.exit_code == 0
    csv_content = csv_path.read_text(encoding="utf-8")
    csv_rows = list(csv.DictReader(io.StringIO(csv_content)))
    assert len(csv_rows) == 1
    assert csv_rows[0]["test_id"] == "export_001"
    assert csv_rows[0]["status"] == "regression"
    assert "response_a" not in csv_rows[0]
    assert "response_b" not in csv_rows[0]
    assert "Response A body should only appear in ndjson." not in csv_content

    ndjson_result = CliRunner().invoke(
        main,
        ["report", str(report_path), "--format", "ndjson", "--output", str(ndjson_path)],
    )
    assert ndjson_result.exit_code == 0
    ndjson_lines = [
        line for line in ndjson_path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    assert len(ndjson_lines) == 1
    ndjson_row = json.loads(ndjson_lines[0])
    assert ndjson_row["test_id"] == "export_001"
    assert ndjson_row["status"] == "regression"
    assert ndjson_row["response_a"] == "Response A body should only appear in ndjson."
    assert ndjson_row["response_b"] == "Response B body should only appear in ndjson."
    assert "metadata" in ndjson_row

    junit_result = CliRunner().invoke(
        main,
        ["report", str(report_path), "--format", "junit", "--output", str(junit_path)],
    )
    assert junit_result.exit_code == 0
    junit_content = junit_path.read_text(encoding="utf-8")
    junit_root = ET.fromstring(junit_content)
    assert junit_root.tag == "testsuite"
    assert junit_root.attrib["tests"] == "1"
    assert junit_root.attrib["failures"] == "1"
    testcase = junit_root.find("testcase")
    assert testcase is not None
    failure = testcase.find("failure")
    assert failure is not None
    system_out = testcase.find("system-out")
    assert system_out is not None
    assert "status=regression" in (system_out.text or "")
    assert "Response A body should only appear in ndjson." not in junit_content
    assert "Response B body should only appear in ndjson." not in junit_content


def test_report_csv_ndjson_and_junit_empty_diff_results(tmp_path: Path) -> None:
    report_path = tmp_path / "empty_export_report.json"
    csv_path = tmp_path / "empty_report.csv"
    ndjson_path = tmp_path / "empty_report.ndjson"
    junit_path = tmp_path / "empty_report.junit.xml"

    report = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite_empty",
        total_tests=0,
        total_diffs=0,
        regressions=0,
        improvements=0,
        duration_seconds=0.0,
        diff_results=[],
        metadata={},
    )
    report_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    csv_result = CliRunner().invoke(
        main,
        ["report", str(report_path), "--format", "csv", "--output", str(csv_path)],
    )
    assert csv_result.exit_code == 0
    csv_rows = list(csv.DictReader(io.StringIO(csv_path.read_text(encoding="utf-8"))))
    assert csv_rows == []

    ndjson_result = CliRunner().invoke(
        main,
        ["report", str(report_path), "--format", "ndjson", "--output", str(ndjson_path)],
    )
    assert ndjson_result.exit_code == 0
    assert ndjson_path.read_text(encoding="utf-8") == ""

    junit_result = CliRunner().invoke(
        main,
        ["report", str(report_path), "--format", "junit", "--output", str(junit_path)],
    )
    assert junit_result.exit_code == 0
    junit_root = ET.fromstring(junit_path.read_text(encoding="utf-8"))
    assert junit_root.attrib["tests"] == "0"
    assert junit_root.attrib["failures"] == "0"
    assert junit_root.find("testcase") is None


def test_report_http_export_connector_success(tmp_path: Path, monkeypatch) -> None:
    report_path = tmp_path / "report_http_export.json"
    csv_path = tmp_path / "report_http_export.csv"
    captured: dict[str, object] = {}

    report = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite_http_export",
        total_tests=1,
        total_diffs=1,
        regressions=1,
        improvements=0,
        duration_seconds=0.4,
        diff_results=[
            DiffResult(
                test_id="http_001",
                model_a="gpt-4o",
                model_b="gpt-4.5",
                response_a="a",
                response_b="b",
                is_semantically_same=False,
                semantic_similarity=0.11,
                behavior_category=BehaviorCategory.FORMAT_CHANGE,
                is_regression=True,
                is_improvement=False,
                confidence=0.8,
                explanation="regression",
            )
        ],
    )
    report_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

    def fake_post(url: str, json: dict, headers: dict, timeout: float):
        captured["url"] = url
        captured["payload"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return DummyResponse()

    monkeypatch.setattr("llm_behavior_diff.cli.httpx.post", fake_post)

    result = CliRunner().invoke(
        main,
        [
            "report",
            str(report_path),
            "--format",
            "csv",
            "--output",
            str(csv_path),
            "--export-connector",
            "http",
            "--export-endpoint",
            "https://example.com/hooks/llm-diff",
            "--export-timeout",
            "6",
        ],
    )

    assert result.exit_code == 0
    assert "External export delivered" in result.output
    assert captured["url"] == "https://example.com/hooks/llm-diff"
    assert captured["timeout"] == 6.0
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers.get("User-Agent") == "llm-behavior-diff/0.1 report-export"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["report"]["suite_name"] == "suite_http_export"
    assert payload["export"]["format"] == "csv"
    assert payload["export"]["content_type"] == "text/csv"
    assert "test_id" in payload["export"]["content"]


def test_report_http_export_connector_requires_endpoint(tmp_path: Path) -> None:
    report_path = tmp_path / "report_http_export_missing_endpoint.json"
    csv_path = tmp_path / "report_http_export_missing_endpoint.csv"
    report = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite_http_export",
        total_tests=0,
        total_diffs=0,
        regressions=0,
        improvements=0,
        duration_seconds=0.0,
    )
    report_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    result = CliRunner().invoke(
        main,
        [
            "report",
            str(report_path),
            "--format",
            "csv",
            "--output",
            str(csv_path),
            "--export-connector",
            "http",
        ],
    )

    assert result.exit_code == 1
    assert "export_endpoint is required" in result.output


def test_report_s3_export_connector_success(tmp_path: Path, monkeypatch) -> None:
    report_path = tmp_path / "report_s3_export.json"
    ndjson_path = tmp_path / "report_s3_export.ndjson"
    captured: dict[str, object] = {}

    report = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite_s3_export",
        total_tests=1,
        total_diffs=1,
        regressions=0,
        improvements=1,
        duration_seconds=0.4,
        diff_results=[
            DiffResult(
                test_id="s3_001",
                model_a="gpt-4o",
                model_b="gpt-4.5",
                response_a="a",
                response_b="b",
                is_semantically_same=False,
                semantic_similarity=0.11,
                behavior_category=BehaviorCategory.KNOWLEDGE_CHANGE,
                is_regression=False,
                is_improvement=True,
                confidence=0.8,
                explanation="improvement",
            )
        ],
    )
    report_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    class FakeS3Client:
        def put_object(self, **kwargs):
            captured["kwargs"] = kwargs
            return {"ETag": "test-etag"}

    def fake_create_s3_client(region: str | None, timeout_seconds: float):
        captured["region"] = region
        captured["timeout"] = timeout_seconds
        return FakeS3Client()

    monkeypatch.setattr("llm_behavior_diff.cli._create_s3_client", fake_create_s3_client)

    result = CliRunner().invoke(
        main,
        [
            "report",
            str(report_path),
            "--format",
            "ndjson",
            "--output",
            str(ndjson_path),
            "--export-connector",
            "s3",
            "--export-s3-bucket",
            "llm-diff-bucket",
            "--export-s3-prefix",
            "team-a/exports",
            "--export-s3-region",
            "eu-west-1",
            "--export-timeout",
            "7",
        ],
    )

    assert result.exit_code == 0
    assert "External export delivered" in result.output
    assert captured["region"] == "eu-west-1"
    assert captured["timeout"] == 7.0
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["Bucket"] == "llm-diff-bucket"
    assert kwargs["ContentType"] == "application/x-ndjson"
    assert isinstance(kwargs["Body"], bytes)
    assert kwargs["Key"].startswith("team-a/exports/suite_s3_export/")
    assert kwargs["Key"].endswith("/report.ndjson")


def test_report_s3_export_connector_requires_bucket(tmp_path: Path) -> None:
    report_path = tmp_path / "report_s3_export_missing_bucket.json"
    csv_path = tmp_path / "report_s3_export_missing_bucket.csv"
    report = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite_s3_export",
        total_tests=0,
        total_diffs=0,
        regressions=0,
        improvements=0,
        duration_seconds=0.0,
    )
    report_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    result = CliRunner().invoke(
        main,
        [
            "report",
            str(report_path),
            "--format",
            "csv",
            "--output",
            str(csv_path),
            "--export-connector",
            "s3",
        ],
    )

    assert result.exit_code == 1
    assert "export_s3_bucket is required" in result.output


def test_report_gcs_export_connector_success_csv_and_ndjson(tmp_path: Path, monkeypatch) -> None:
    report_path = tmp_path / "report_gcs_export.json"
    captured_uploads: list[dict[str, object]] = []
    captured_client: dict[str, object] = {}

    report = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite_gcs_export",
        total_tests=1,
        total_diffs=1,
        regressions=0,
        improvements=1,
        duration_seconds=0.4,
        diff_results=[
            DiffResult(
                test_id="gcs_001",
                model_a="gpt-4o",
                model_b="gpt-4.5",
                response_a="a",
                response_b="b",
                is_semantically_same=False,
                semantic_similarity=0.11,
                behavior_category=BehaviorCategory.KNOWLEDGE_CHANGE,
                is_regression=False,
                is_improvement=True,
                confidence=0.8,
                explanation="improvement",
            )
        ],
    )
    report_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    class FakeBlob:
        def __init__(self, key: str):
            self.key = key

        def upload_from_string(self, data: str, content_type: str, timeout: float) -> None:
            captured_uploads.append(
                {
                    "key": self.key,
                    "data": data,
                    "content_type": content_type,
                    "timeout": timeout,
                }
            )

    class FakeBucket:
        def __init__(self, name: str):
            self.name = name

        def blob(self, key: str) -> FakeBlob:
            return FakeBlob(key)

    class FakeGCSClient:
        def bucket(self, name: str) -> FakeBucket:
            captured_client["bucket"] = name
            return FakeBucket(name)

    def fake_create_gcs_client(project: str | None, timeout_seconds: float):
        captured_client["project"] = project
        captured_client["timeout"] = timeout_seconds
        return FakeGCSClient()

    monkeypatch.setattr("llm_behavior_diff.cli._create_gcs_client", fake_create_gcs_client)

    csv_path = tmp_path / "report_gcs_export.csv"
    csv_result = CliRunner().invoke(
        main,
        [
            "report",
            str(report_path),
            "--format",
            "csv",
            "--output",
            str(csv_path),
            "--export-connector",
            "gcs",
            "--export-gcs-bucket",
            "llm-diff-gcs",
            "--export-gcs-prefix",
            "team-a/exports",
            "--export-gcs-project",
            "analytics-prj",
            "--export-timeout",
            "9",
        ],
    )
    assert csv_result.exit_code == 0
    assert "External export delivered" in csv_result.output

    ndjson_path = tmp_path / "report_gcs_export.ndjson"
    ndjson_result = CliRunner().invoke(
        main,
        [
            "report",
            str(report_path),
            "--format",
            "ndjson",
            "--output",
            str(ndjson_path),
            "--export-connector",
            "gcs",
            "--export-gcs-bucket",
            "llm-diff-gcs",
            "--export-gcs-prefix",
            "team-a/exports",
            "--export-gcs-project",
            "analytics-prj",
            "--export-timeout",
            "9",
        ],
    )
    assert ndjson_result.exit_code == 0
    assert "External export delivered" in ndjson_result.output

    assert captured_client["project"] == "analytics-prj"
    assert captured_client["timeout"] == 9.0
    assert captured_client["bucket"] == "llm-diff-gcs"
    assert len(captured_uploads) == 2
    assert captured_uploads[0]["content_type"] == "text/csv"
    assert captured_uploads[1]["content_type"] == "application/x-ndjson"
    assert str(captured_uploads[0]["key"]).startswith("team-a/exports/suite_gcs_export/")
    assert str(captured_uploads[1]["key"]).endswith("/report.ndjson")


def test_report_gcs_export_connector_requires_bucket(tmp_path: Path) -> None:
    report_path = tmp_path / "report_gcs_export_missing_bucket.json"
    csv_path = tmp_path / "report_gcs_export_missing_bucket.csv"
    report = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite_gcs_export",
        total_tests=0,
        total_diffs=0,
        regressions=0,
        improvements=0,
        duration_seconds=0.0,
    )
    report_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    result = CliRunner().invoke(
        main,
        [
            "report",
            str(report_path),
            "--format",
            "csv",
            "--output",
            str(csv_path),
            "--export-connector",
            "gcs",
        ],
    )

    assert result.exit_code == 1
    assert "export_gcs_bucket is required" in result.output


def test_report_azure_blob_export_connector_success_csv_and_ndjson(
    tmp_path: Path, monkeypatch
) -> None:
    report_path = tmp_path / "report_azure_blob_export.json"
    captured_uploads: list[dict[str, object]] = []
    captured_client: dict[str, object] = {}

    report = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite_azure_blob_export",
        total_tests=1,
        total_diffs=1,
        regressions=0,
        improvements=1,
        duration_seconds=0.4,
        diff_results=[
            DiffResult(
                test_id="az_001",
                model_a="gpt-4o",
                model_b="gpt-4.5",
                response_a="a",
                response_b="b",
                is_semantically_same=False,
                semantic_similarity=0.11,
                behavior_category=BehaviorCategory.KNOWLEDGE_CHANGE,
                is_regression=False,
                is_improvement=True,
                confidence=0.8,
                explanation="improvement",
            )
        ],
    )
    report_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    class FakeBlobClient:
        def __init__(self, container: str, blob: str):
            self.container = container
            self.blob = blob

        def upload_blob(
            self, data: bytes, overwrite: bool, content_type: str, timeout: float
        ) -> None:
            captured_uploads.append(
                {
                    "container": self.container,
                    "blob": self.blob,
                    "data": data,
                    "overwrite": overwrite,
                    "content_type": content_type,
                    "timeout": timeout,
                }
            )

    class FakeBlobServiceClient:
        def get_blob_client(self, container: str, blob: str) -> FakeBlobClient:
            return FakeBlobClient(container=container, blob=blob)

    def fake_create_azure_blob_service_client(account_url: str, timeout_seconds: float):
        captured_client["account_url"] = account_url
        captured_client["timeout"] = timeout_seconds
        return FakeBlobServiceClient()

    monkeypatch.setattr(
        "llm_behavior_diff.cli._create_azure_blob_service_client",
        fake_create_azure_blob_service_client,
    )

    csv_path = tmp_path / "report_azure_blob_export.csv"
    csv_result = CliRunner().invoke(
        main,
        [
            "report",
            str(report_path),
            "--format",
            "csv",
            "--output",
            str(csv_path),
            "--export-connector",
            "azure_blob",
            "--export-az-account-url",
            "https://myaccount.blob.core.windows.net",
            "--export-az-container",
            "llm-diff-exports",
            "--export-az-prefix",
            "team-a/exports",
            "--export-timeout",
            "9",
        ],
    )
    assert csv_result.exit_code == 0
    assert "External export delivered" in csv_result.output

    ndjson_path = tmp_path / "report_azure_blob_export.ndjson"
    ndjson_result = CliRunner().invoke(
        main,
        [
            "report",
            str(report_path),
            "--format",
            "ndjson",
            "--output",
            str(ndjson_path),
            "--export-connector",
            "azure_blob",
            "--export-az-account-url",
            "https://myaccount.blob.core.windows.net",
            "--export-az-container",
            "llm-diff-exports",
            "--export-az-prefix",
            "team-a/exports",
            "--export-timeout",
            "9",
        ],
    )
    assert ndjson_result.exit_code == 0
    assert "External export delivered" in ndjson_result.output

    assert captured_client["account_url"] == "https://myaccount.blob.core.windows.net"
    assert captured_client["timeout"] == 9.0
    assert len(captured_uploads) == 2
    assert captured_uploads[0]["container"] == "llm-diff-exports"
    assert captured_uploads[0]["overwrite"] is True
    assert captured_uploads[0]["content_type"] == "text/csv"
    assert captured_uploads[1]["content_type"] == "application/x-ndjson"
    assert str(captured_uploads[0]["blob"]).startswith("team-a/exports/suite_azure_blob_export/")
    assert str(captured_uploads[1]["blob"]).endswith("/report.ndjson")
    assert isinstance(captured_uploads[0]["data"], bytes)


def test_report_azure_blob_export_connector_requires_fields(tmp_path: Path) -> None:
    report_path = tmp_path / "report_azure_blob_export_missing_fields.json"
    csv_path = tmp_path / "report_azure_blob_export_missing_fields.csv"
    report = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite_azure_blob_export",
        total_tests=0,
        total_diffs=0,
        regressions=0,
        improvements=0,
        duration_seconds=0.0,
    )
    report_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    missing_account = CliRunner().invoke(
        main,
        [
            "report",
            str(report_path),
            "--format",
            "csv",
            "--output",
            str(csv_path),
            "--export-connector",
            "azure_blob",
            "--export-az-container",
            "llm-diff-exports",
        ],
    )
    assert missing_account.exit_code == 1
    assert "export_az_account_url is required" in missing_account.output

    missing_container = CliRunner().invoke(
        main,
        [
            "report",
            str(report_path),
            "--format",
            "csv",
            "--output",
            str(csv_path),
            "--export-connector",
            "azure_blob",
            "--export-az-account-url",
            "https://myaccount.blob.core.windows.net",
        ],
    )
    assert missing_container.exit_code == 1
    assert "export_az_container is required" in missing_container.output


def test_report_bigquery_export_connector_success(tmp_path: Path, monkeypatch) -> None:
    report_path = tmp_path / "report_bigquery_export.json"
    ndjson_path = tmp_path / "report_bigquery_export.ndjson"
    captured: dict[str, object] = {}

    report = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite_bigquery_export",
        total_tests=1,
        total_diffs=1,
        regressions=0,
        improvements=1,
        duration_seconds=0.4,
        diff_results=[
            DiffResult(
                test_id="bq_001",
                model_a="gpt-4o",
                model_b="gpt-4.5",
                response_a="a",
                response_b="b",
                is_semantically_same=False,
                semantic_similarity=0.11,
                behavior_category=BehaviorCategory.KNOWLEDGE_CHANGE,
                is_regression=False,
                is_improvement=True,
                confidence=0.8,
                explanation="improvement",
                metadata={"comparator": "format"},
            )
        ],
    )
    report_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    class FakeBigQueryClient:
        def insert_rows_json(self, table: str, rows: list[dict[str, object]], timeout: float):
            captured["table"] = table
            captured["rows"] = rows
            captured["timeout"] = timeout
            return []

    def fake_create_bigquery_client(project: str, location: str | None):
        captured["project"] = project
        captured["location"] = location
        return FakeBigQueryClient()

    monkeypatch.setattr(
        "llm_behavior_diff.cli._create_bigquery_client", fake_create_bigquery_client
    )

    result = CliRunner().invoke(
        main,
        [
            "report",
            str(report_path),
            "--format",
            "ndjson",
            "--output",
            str(ndjson_path),
            "--export-connector",
            "bigquery",
            "--export-bq-project",
            "analytics-prj",
            "--export-bq-dataset",
            "llm_diff",
            "--export-bq-table",
            "diff_rows",
            "--export-bq-location",
            "EU",
            "--export-timeout",
            "5",
        ],
    )

    assert result.exit_code == 0
    assert "External export delivered" in result.output
    assert captured["project"] == "analytics-prj"
    assert captured["location"] == "EU"
    assert captured["table"] == "analytics-prj.llm_diff.diff_rows"
    assert captured["timeout"] == 5.0
    rows = captured["rows"]
    assert isinstance(rows, list)
    assert len(rows) == 1
    row = rows[0]
    assert isinstance(row, dict)
    assert row["test_id"] == "bq_001"
    assert row["metadata_json"] == '{"comparator": "format"}'


def test_report_bigquery_export_connector_requires_fields(tmp_path: Path) -> None:
    report_path = tmp_path / "report_bigquery_export_missing_fields.json"
    ndjson_path = tmp_path / "report_bigquery_export_missing_fields.ndjson"
    report = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite_bigquery_export",
        total_tests=0,
        total_diffs=0,
        regressions=0,
        improvements=0,
        duration_seconds=0.0,
    )
    report_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    scenarios = [
        (
            ["--export-bq-dataset", "llm_diff", "--export-bq-table", "diff_rows"],
            "export_bq_project is required",
        ),
        (
            ["--export-bq-project", "analytics-prj", "--export-bq-table", "diff_rows"],
            "export_bq_dataset is required",
        ),
        (
            ["--export-bq-project", "analytics-prj", "--export-bq-dataset", "llm_diff"],
            "export_bq_table is required",
        ),
    ]

    for flags, expected_error in scenarios:
        result = CliRunner().invoke(
            main,
            [
                "report",
                str(report_path),
                "--format",
                "ndjson",
                "--output",
                str(ndjson_path),
                "--export-connector",
                "bigquery",
                *flags,
            ],
        )

        assert result.exit_code == 1
        assert expected_error in result.output


def test_report_bigquery_export_connector_rejects_non_ndjson_format(tmp_path: Path) -> None:
    report_path = tmp_path / "report_bigquery_export_non_ndjson.json"
    csv_path = tmp_path / "report_bigquery_export_non_ndjson.csv"
    report = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite_bigquery_export",
        total_tests=0,
        total_diffs=0,
        regressions=0,
        improvements=0,
        duration_seconds=0.0,
    )
    report_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    result = CliRunner().invoke(
        main,
        [
            "report",
            str(report_path),
            "--format",
            "csv",
            "--output",
            str(csv_path),
            "--export-connector",
            "bigquery",
            "--export-bq-project",
            "analytics-prj",
            "--export-bq-dataset",
            "llm_diff",
            "--export-bq-table",
            "diff_rows",
        ],
    )

    assert result.exit_code == 1
    assert "supports only --format ndjson" in result.output


def test_report_snowflake_export_connector_success_with_env_password(
    tmp_path: Path, monkeypatch
) -> None:
    report_path = tmp_path / "report_snowflake_export.json"
    ndjson_path = tmp_path / "report_snowflake_export.ndjson"
    captured: dict[str, object] = {}

    report = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite_snowflake_export",
        total_tests=1,
        total_diffs=1,
        regressions=0,
        improvements=1,
        duration_seconds=0.4,
        diff_results=[
            DiffResult(
                test_id="sf_001",
                model_a="gpt-4o",
                model_b="gpt-4.5",
                response_a="a",
                response_b="b",
                is_semantically_same=False,
                semantic_similarity=0.11,
                behavior_category=BehaviorCategory.KNOWLEDGE_CHANGE,
                is_regression=False,
                is_improvement=True,
                confidence=0.8,
                explanation="improvement",
                metadata={"comparator": "factual"},
            )
        ],
    )
    report_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    class FakeCursor:
        def executemany(self, query: str, rows: list[dict[str, object]]) -> None:
            captured["query"] = query
            captured["rows"] = rows

        def close(self) -> None:
            captured["cursor_closed"] = True

    class FakeConnection:
        def cursor(self) -> FakeCursor:
            captured["cursor_opened"] = True
            return FakeCursor()

        def commit(self) -> None:
            captured["committed"] = True

        def close(self) -> None:
            captured["connection_closed"] = True

    def fake_create_snowflake_connection(**kwargs):
        captured["connect_kwargs"] = kwargs
        return FakeConnection()

    monkeypatch.setenv("LLM_DIFF_EXPORT_SF_PASSWORD", "sf-secret")
    monkeypatch.setattr(
        "llm_behavior_diff.cli._create_snowflake_connection", fake_create_snowflake_connection
    )

    result = CliRunner().invoke(
        main,
        [
            "report",
            str(report_path),
            "--format",
            "ndjson",
            "--output",
            str(ndjson_path),
            "--export-connector",
            "snowflake",
            "--export-sf-account",
            "xy12345.eu-west-1",
            "--export-sf-user",
            "svc_llm_diff",
            "--export-sf-role",
            "ANALYST",
            "--export-sf-warehouse",
            "COMPUTE_WH",
            "--export-sf-database",
            "ANALYTICS_DB",
            "--export-sf-schema",
            "LLM_DIFF",
            "--export-sf-table",
            "DIFF_ROWS",
            "--export-timeout",
            "6",
        ],
    )

    assert result.exit_code == 0
    assert "External export delivered" in result.output

    connect_kwargs = captured["connect_kwargs"]
    assert isinstance(connect_kwargs, dict)
    assert connect_kwargs["account"] == "xy12345.eu-west-1"
    assert connect_kwargs["user"] == "svc_llm_diff"
    assert connect_kwargs["password"] == "sf-secret"
    assert connect_kwargs["role"] == "ANALYST"
    assert connect_kwargs["warehouse"] == "COMPUTE_WH"
    assert connect_kwargs["database"] == "ANALYTICS_DB"
    assert connect_kwargs["schema"] == "LLM_DIFF"
    assert connect_kwargs["timeout_seconds"] == 6.0

    query = captured["query"]
    assert isinstance(query, str)
    assert 'INSERT INTO "ANALYTICS_DB"."LLM_DIFF"."DIFF_ROWS"' in query
    rows = captured["rows"]
    assert isinstance(rows, list)
    assert len(rows) == 1
    assert rows[0]["test_id"] == "sf_001"
    assert rows[0]["metadata_json"] == '{"comparator": "factual"}'
    assert captured["committed"] is True
    assert captured["cursor_closed"] is True
    assert captured["connection_closed"] is True


def test_report_snowflake_export_connector_requires_fields(tmp_path: Path) -> None:
    report_path = tmp_path / "report_snowflake_export_missing_fields.json"
    ndjson_path = tmp_path / "report_snowflake_export_missing_fields.ndjson"
    report = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite_snowflake_export",
        total_tests=0,
        total_diffs=0,
        regressions=0,
        improvements=0,
        duration_seconds=0.0,
    )
    report_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    result_missing_account = CliRunner().invoke(
        main,
        [
            "report",
            str(report_path),
            "--format",
            "ndjson",
            "--output",
            str(ndjson_path),
            "--export-connector",
            "snowflake",
            "--export-sf-user",
            "svc_llm_diff",
            "--export-sf-warehouse",
            "COMPUTE_WH",
            "--export-sf-database",
            "ANALYTICS_DB",
            "--export-sf-schema",
            "LLM_DIFF",
            "--export-sf-table",
            "DIFF_ROWS",
            "--export-sf-password",
            "sf-secret",
        ],
    )
    assert result_missing_account.exit_code == 1
    assert "export_sf_account is required" in result_missing_account.output

    result_missing_password = CliRunner().invoke(
        main,
        [
            "report",
            str(report_path),
            "--format",
            "ndjson",
            "--output",
            str(ndjson_path),
            "--export-connector",
            "snowflake",
            "--export-sf-account",
            "xy12345.eu-west-1",
            "--export-sf-user",
            "svc_llm_diff",
            "--export-sf-warehouse",
            "COMPUTE_WH",
            "--export-sf-database",
            "ANALYTICS_DB",
            "--export-sf-schema",
            "LLM_DIFF",
            "--export-sf-table",
            "DIFF_ROWS",
        ],
    )
    assert result_missing_password.exit_code == 1
    assert "Snowflake password is required" in result_missing_password.output


def test_report_snowflake_export_connector_rejects_non_ndjson_format(tmp_path: Path) -> None:
    report_path = tmp_path / "report_snowflake_export_non_ndjson.json"
    csv_path = tmp_path / "report_snowflake_export_non_ndjson.csv"
    report = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite_snowflake_export",
        total_tests=0,
        total_diffs=0,
        regressions=0,
        improvements=0,
        duration_seconds=0.0,
    )
    report_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    result = CliRunner().invoke(
        main,
        [
            "report",
            str(report_path),
            "--format",
            "csv",
            "--output",
            str(csv_path),
            "--export-connector",
            "snowflake",
            "--export-sf-account",
            "xy12345.eu-west-1",
            "--export-sf-user",
            "svc_llm_diff",
            "--export-sf-password",
            "sf-secret",
            "--export-sf-warehouse",
            "COMPUTE_WH",
            "--export-sf-database",
            "ANALYTICS_DB",
            "--export-sf-schema",
            "LLM_DIFF",
            "--export-sf-table",
            "DIFF_ROWS",
        ],
    )

    assert result.exit_code == 1
    assert "supports only --format ndjson" in result.output


def test_report_redshift_export_connector_success_with_env_password(
    tmp_path: Path, monkeypatch
) -> None:
    report_path = tmp_path / "report_redshift_export.json"
    ndjson_path = tmp_path / "report_redshift_export.ndjson"
    captured: dict[str, object] = {}

    report = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite_redshift_export",
        total_tests=1,
        total_diffs=1,
        regressions=0,
        improvements=1,
        duration_seconds=0.4,
        diff_results=[
            DiffResult(
                test_id="rs_001",
                model_a="gpt-4o",
                model_b="gpt-4.5",
                response_a="a",
                response_b="b",
                is_semantically_same=False,
                semantic_similarity=0.11,
                behavior_category=BehaviorCategory.KNOWLEDGE_CHANGE,
                is_regression=False,
                is_improvement=True,
                confidence=0.8,
                explanation="improvement",
                metadata={"comparator": "behavioral"},
            )
        ],
    )
    report_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    class FakeCursor:
        def executemany(self, query: str, rows: list[dict[str, object]]) -> None:
            captured["query"] = query
            captured["rows"] = rows

        def close(self) -> None:
            captured["cursor_closed"] = True

    class FakeConnection:
        def cursor(self) -> FakeCursor:
            captured["cursor_opened"] = True
            return FakeCursor()

        def commit(self) -> None:
            captured["committed"] = True

        def close(self) -> None:
            captured["connection_closed"] = True

    def fake_create_redshift_connection(**kwargs):
        captured["connect_kwargs"] = kwargs
        return FakeConnection()

    monkeypatch.setenv("LLM_DIFF_EXPORT_RS_PASSWORD", "rs-secret")
    monkeypatch.setattr(
        "llm_behavior_diff.cli._create_redshift_connection", fake_create_redshift_connection
    )

    result = CliRunner().invoke(
        main,
        [
            "report",
            str(report_path),
            "--format",
            "ndjson",
            "--output",
            str(ndjson_path),
            "--export-connector",
            "redshift",
            "--export-rs-host",
            "redshift-cluster.example.amazonaws.com",
            "--export-rs-port",
            "5439",
            "--export-rs-database",
            "analytics",
            "--export-rs-user",
            "svc_llm_diff",
            "--export-rs-schema",
            "llm_diff",
            "--export-rs-table",
            "diff_rows",
            "--export-rs-sslmode",
            "require",
            "--export-timeout",
            "6",
        ],
    )

    assert result.exit_code == 0
    assert "External export delivered" in result.output

    connect_kwargs = captured["connect_kwargs"]
    assert isinstance(connect_kwargs, dict)
    assert connect_kwargs["host"] == "redshift-cluster.example.amazonaws.com"
    assert connect_kwargs["port"] == 5439
    assert connect_kwargs["database"] == "analytics"
    assert connect_kwargs["user"] == "svc_llm_diff"
    assert connect_kwargs["password"] == "rs-secret"
    assert connect_kwargs["sslmode"] == "require"
    assert connect_kwargs["timeout_seconds"] == 6.0

    query = captured["query"]
    assert isinstance(query, str)
    assert 'INSERT INTO "llm_diff"."diff_rows"' in query
    rows = captured["rows"]
    assert isinstance(rows, list)
    assert len(rows) == 1
    assert rows[0]["test_id"] == "rs_001"
    assert rows[0]["metadata_json"] == '{"comparator": "behavioral"}'
    assert captured["committed"] is True
    assert captured["cursor_closed"] is True
    assert captured["connection_closed"] is True


def test_report_redshift_export_connector_requires_fields(tmp_path: Path) -> None:
    report_path = tmp_path / "report_redshift_export_missing_fields.json"
    ndjson_path = tmp_path / "report_redshift_export_missing_fields.ndjson"
    report = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite_redshift_export",
        total_tests=0,
        total_diffs=0,
        regressions=0,
        improvements=0,
        duration_seconds=0.0,
    )
    report_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    base_args = [
        "report",
        str(report_path),
        "--format",
        "ndjson",
        "--output",
        str(ndjson_path),
        "--export-connector",
        "redshift",
    ]

    missing_host = CliRunner().invoke(
        main,
        [
            *base_args,
            "--export-rs-database",
            "analytics",
            "--export-rs-user",
            "svc_llm_diff",
            "--export-rs-schema",
            "llm_diff",
            "--export-rs-table",
            "diff_rows",
            "--export-rs-password",
            "rs-secret",
        ],
    )
    assert missing_host.exit_code == 1
    assert "export_rs_host is required" in missing_host.output

    missing_password = CliRunner().invoke(
        main,
        [
            *base_args,
            "--export-rs-host",
            "redshift-cluster.example.amazonaws.com",
            "--export-rs-database",
            "analytics",
            "--export-rs-user",
            "svc_llm_diff",
            "--export-rs-schema",
            "llm_diff",
            "--export-rs-table",
            "diff_rows",
        ],
    )
    assert missing_password.exit_code == 1
    assert "Redshift password is required" in missing_password.output

    invalid_port = CliRunner().invoke(
        main,
        [
            *base_args,
            "--export-rs-host",
            "redshift-cluster.example.amazonaws.com",
            "--export-rs-port",
            "0",
            "--export-rs-database",
            "analytics",
            "--export-rs-user",
            "svc_llm_diff",
            "--export-rs-schema",
            "llm_diff",
            "--export-rs-table",
            "diff_rows",
            "--export-rs-password",
            "rs-secret",
        ],
    )
    assert invalid_port.exit_code == 1
    assert "export_rs_port must be > 0" in invalid_port.output


def test_report_redshift_export_connector_rejects_non_ndjson_format(tmp_path: Path) -> None:
    report_path = tmp_path / "report_redshift_export_non_ndjson.json"
    csv_path = tmp_path / "report_redshift_export_non_ndjson.csv"
    report = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite_redshift_export",
        total_tests=0,
        total_diffs=0,
        regressions=0,
        improvements=0,
        duration_seconds=0.0,
    )
    report_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    result = CliRunner().invoke(
        main,
        [
            "report",
            str(report_path),
            "--format",
            "csv",
            "--output",
            str(csv_path),
            "--export-connector",
            "redshift",
            "--export-rs-host",
            "redshift-cluster.example.amazonaws.com",
            "--export-rs-database",
            "analytics",
            "--export-rs-user",
            "svc_llm_diff",
            "--export-rs-password",
            "rs-secret",
            "--export-rs-schema",
            "llm_diff",
            "--export-rs-table",
            "diff_rows",
        ],
    )

    assert result.exit_code == 1
    assert "supports only --format ndjson" in result.output


def test_report_databricks_export_connector_success_with_env_token(
    tmp_path: Path, monkeypatch
) -> None:
    report_path = tmp_path / "report_databricks_export.json"
    ndjson_path = tmp_path / "report_databricks_export.ndjson"
    captured: dict[str, object] = {}

    report = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite_databricks_export",
        total_tests=1,
        total_diffs=1,
        regressions=0,
        improvements=1,
        duration_seconds=0.4,
        diff_results=[
            DiffResult(
                test_id="dbx_001",
                model_a="gpt-4o",
                model_b="gpt-4.5",
                response_a="a",
                response_b="b",
                is_semantically_same=False,
                semantic_similarity=0.11,
                behavior_category=BehaviorCategory.KNOWLEDGE_CHANGE,
                is_regression=False,
                is_improvement=True,
                confidence=0.8,
                explanation="improvement",
                metadata={"comparator": "semantic"},
            )
        ],
    )
    report_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    class FakeCursor:
        def executemany(self, query: str, rows: list[dict[str, object]]) -> None:
            captured["query"] = query
            captured["rows"] = rows

        def close(self) -> None:
            captured["cursor_closed"] = True

    class FakeConnection:
        def cursor(self) -> FakeCursor:
            captured["cursor_opened"] = True
            return FakeCursor()

        def commit(self) -> None:
            captured["committed"] = True

        def close(self) -> None:
            captured["connection_closed"] = True

    def fake_create_databricks_connection(**kwargs):
        captured["connect_kwargs"] = kwargs
        return FakeConnection()

    monkeypatch.setenv("LLM_DIFF_EXPORT_DBX_TOKEN", "dbx-secret")
    monkeypatch.setattr(
        "llm_behavior_diff.cli._create_databricks_connection", fake_create_databricks_connection
    )

    result = CliRunner().invoke(
        main,
        [
            "report",
            str(report_path),
            "--format",
            "ndjson",
            "--output",
            str(ndjson_path),
            "--export-connector",
            "databricks",
            "--export-dbx-host",
            "dbc-123.cloud.databricks.com",
            "--export-dbx-http-path",
            "/sql/1.0/endpoints/abc123",
            "--export-dbx-catalog",
            "main",
            "--export-dbx-schema",
            "llm_diff",
            "--export-dbx-table",
            "diff_rows",
            "--export-timeout",
            "6",
        ],
    )

    assert result.exit_code == 0
    assert "External export delivered" in result.output

    connect_kwargs = captured["connect_kwargs"]
    assert isinstance(connect_kwargs, dict)
    assert connect_kwargs["host"] == "dbc-123.cloud.databricks.com"
    assert connect_kwargs["http_path"] == "/sql/1.0/endpoints/abc123"
    assert connect_kwargs["token"] == "dbx-secret"
    assert connect_kwargs["timeout_seconds"] == 6.0

    query = captured["query"]
    assert isinstance(query, str)
    assert 'INSERT INTO "main"."llm_diff"."diff_rows"' in query
    rows = captured["rows"]
    assert isinstance(rows, list)
    assert len(rows) == 1
    assert rows[0]["test_id"] == "dbx_001"
    assert rows[0]["metadata_json"] == '{"comparator": "semantic"}'
    assert captured["committed"] is True
    assert captured["cursor_closed"] is True
    assert captured["connection_closed"] is True


def test_report_databricks_export_connector_requires_fields(tmp_path: Path, monkeypatch) -> None:
    report_path = tmp_path / "report_databricks_export_missing_fields.json"
    ndjson_path = tmp_path / "report_databricks_export_missing_fields.ndjson"
    report = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite_databricks_export",
        total_tests=0,
        total_diffs=0,
        regressions=0,
        improvements=0,
        duration_seconds=0.0,
    )
    report_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    monkeypatch.delenv("LLM_DIFF_EXPORT_DBX_TOKEN", raising=False)

    base_args = [
        "report",
        str(report_path),
        "--format",
        "ndjson",
        "--output",
        str(ndjson_path),
        "--export-connector",
        "databricks",
    ]

    missing_host = CliRunner().invoke(
        main,
        [
            *base_args,
            "--export-dbx-http-path",
            "/sql/1.0/endpoints/abc123",
            "--export-dbx-catalog",
            "main",
            "--export-dbx-schema",
            "llm_diff",
            "--export-dbx-table",
            "diff_rows",
            "--export-dbx-token",
            "dbx-secret",
        ],
    )
    assert missing_host.exit_code == 1
    assert "export_dbx_host is required" in missing_host.output

    missing_token = CliRunner().invoke(
        main,
        [
            *base_args,
            "--export-dbx-host",
            "dbc-123.cloud.databricks.com",
            "--export-dbx-http-path",
            "/sql/1.0/endpoints/abc123",
            "--export-dbx-catalog",
            "main",
            "--export-dbx-schema",
            "llm_diff",
            "--export-dbx-table",
            "diff_rows",
        ],
    )
    assert missing_token.exit_code == 1
    assert "Databricks token is required" in missing_token.output


def test_report_databricks_export_connector_rejects_non_ndjson_format(
    tmp_path: Path, monkeypatch
) -> None:
    report_path = tmp_path / "report_databricks_export_non_ndjson.json"
    csv_path = tmp_path / "report_databricks_export_non_ndjson.csv"
    report = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite_databricks_export",
        total_tests=0,
        total_diffs=0,
        regressions=0,
        improvements=0,
        duration_seconds=0.0,
    )
    report_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")
    monkeypatch.setenv("LLM_DIFF_EXPORT_DBX_TOKEN", "dbx-secret")

    result = CliRunner().invoke(
        main,
        [
            "report",
            str(report_path),
            "--format",
            "csv",
            "--output",
            str(csv_path),
            "--export-connector",
            "databricks",
            "--export-dbx-host",
            "dbc-123.cloud.databricks.com",
            "--export-dbx-http-path",
            "/sql/1.0/endpoints/abc123",
            "--export-dbx-catalog",
            "main",
            "--export-dbx-schema",
            "llm_diff",
            "--export-dbx-table",
            "diff_rows",
        ],
    )

    assert result.exit_code == 1
    assert "supports only --format ndjson" in result.output


def test_report_export_connector_rejects_table_format(tmp_path: Path, monkeypatch) -> None:
    report_path = tmp_path / "report_table_export.json"
    report = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite_table_export",
        total_tests=0,
        total_diffs=0,
        regressions=0,
        improvements=0,
        duration_seconds=0.0,
    )
    report_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    result = CliRunner().invoke(
        main,
        [
            "report",
            str(report_path),
            "--format",
            "table",
            "--export-connector",
            "http",
            "--export-endpoint",
            "https://example.com/hook",
        ],
    )

    assert result.exit_code == 1
    assert "requires non-table report format output" in result.output

    called = False

    def fake_create_gcs_client(project: str | None, timeout_seconds: float):
        nonlocal called
        called = True
        return object()

    monkeypatch.setattr("llm_behavior_diff.cli._create_gcs_client", fake_create_gcs_client)

    gcs_result = CliRunner().invoke(
        main,
        [
            "report",
            str(report_path),
            "--format",
            "table",
            "--export-connector",
            "gcs",
            "--export-gcs-bucket",
            "test-bucket",
        ],
    )

    assert gcs_result.exit_code == 1
    assert "requires non-table report format output" in gcs_result.output
    assert called is False

    azure_called = False

    def fake_create_azure_blob_service_client(account_url: str, timeout_seconds: float):
        nonlocal azure_called
        azure_called = True
        return object()

    monkeypatch.setattr(
        "llm_behavior_diff.cli._create_azure_blob_service_client",
        fake_create_azure_blob_service_client,
    )

    azure_result = CliRunner().invoke(
        main,
        [
            "report",
            str(report_path),
            "--format",
            "table",
            "--export-connector",
            "azure_blob",
            "--export-az-account-url",
            "https://myaccount.blob.core.windows.net",
            "--export-az-container",
            "llm-diff-exports",
        ],
    )

    assert azure_result.exit_code == 1
    assert "requires non-table report format output" in azure_result.output
    assert azure_called is False


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
    assert "Regression Delta Permutation p-value" in result.output
    compare_content = compare_md_path.read_text(encoding="utf-8")
    assert "Regression Delta Significant?" in compare_content
    assert "Improvement Delta Significant?" in compare_content
    assert "Regression Delta Permutation p-value" in compare_content
    assert "Improvement Delta Permutation p-value" in compare_content


def test_compare_significance_fallback_when_diff_results_missing(tmp_path: Path) -> None:
    report_a_path = tmp_path / "a_no_diff.json"
    report_b_path = tmp_path / "b_no_diff.json"

    report_a = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite",
        total_tests=10,
        total_diffs=2,
        regressions=1,
        improvements=1,
        duration_seconds=1.0,
        diff_results=[],
    )
    report_b = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite",
        total_tests=10,
        total_diffs=3,
        regressions=2,
        improvements=1,
        duration_seconds=1.0,
        diff_results=[],
    )

    report_a_path.write_text(
        json.dumps(report_a.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    report_b_path.write_text(
        json.dumps(report_b.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["compare", str(report_a_path), str(report_b_path)])

    assert result.exit_code == 0
    assert (
        "Significance not available: diff_results missing or empty in one/both reports."
        in result.output
    )


def test_report_table_backward_compatible_without_wilson_fields(tmp_path: Path) -> None:
    report_path = tmp_path / "legacy_significance_report.json"
    report = BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite",
        total_tests=5,
        total_diffs=1,
        regressions=1,
        improvements=0,
        duration_seconds=0.5,
        metadata={
            "significance": {
                "method": "bootstrap",
                "confidence_level": 0.95,
                "resamples": 5000,
                "seed": 42,
                "sample_size": 5,
                "regression_rate": {"point": 0.2, "ci_low": 0.0, "ci_high": 0.4},
                "improvement_rate": {"point": 0.0, "ci_low": 0.0, "ci_high": 0.2},
            }
        },
    )
    report_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    result = CliRunner().invoke(main, ["report", str(report_path), "--format", "table"])

    assert result.exit_code == 0
    assert "Regression Rate CI (95%)" in result.output
    assert "Improvement Rate CI (95%)" in result.output
