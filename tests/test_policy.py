"""Unit tests for risk-tier report gate policies."""

from __future__ import annotations

from llm_behavior_diff.policy import evaluate_report_collection, evaluate_report_policy
from llm_behavior_diff.schema import BehaviorCategory, BehaviorReport, DiffResult


def _build_report(
    *,
    suite_name: str = "suite",
    total_tests: int = 100,
    regressions: int = 0,
    improvements: int = 0,
    regression_by_category: dict[BehaviorCategory, int] | None = None,
    diff_results: list[DiffResult] | None = None,
) -> BehaviorReport:
    return BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name=suite_name,
        total_tests=total_tests,
        total_diffs=regressions + improvements,
        regressions=regressions,
        improvements=improvements,
        duration_seconds=1.0,
        regression_by_category=regression_by_category or {},
        diff_results=diff_results or [],
    )


def test_policy_strict_fails_when_regressions_non_zero() -> None:
    report = _build_report(total_tests=10, regressions=1)
    result = evaluate_report_policy(report, "strict")
    assert result["passed"] is False
    assert result["thresholds"]["allowed_regressions"] == 0


def test_policy_balanced_allows_small_non_critical_regressions() -> None:
    report = _build_report(total_tests=100, regressions=2)
    result = evaluate_report_policy(report, "balanced")
    assert result["thresholds"]["allowed_regressions"] == 2
    assert result["passed"] is True


def test_policy_balanced_fails_on_critical_category() -> None:
    report = _build_report(
        total_tests=100,
        regressions=1,
        regression_by_category={BehaviorCategory.SAFETY_BOUNDARY: 1},
    )
    result = evaluate_report_policy(report, "balanced")
    assert result["passed"] is False
    assert any(
        "critical regression detected in safety_boundary" in reason for reason in result["reasons"]
    )


def test_policy_permissive_thresholds_and_critical_rules() -> None:
    report = _build_report(
        total_tests=100,
        regressions=3,
        regression_by_category={
            BehaviorCategory.HALLUCINATION_NEW: 1,
            BehaviorCategory.SAFETY_BOUNDARY: 2,
        },
    )
    result = evaluate_report_policy(report, "permissive")
    assert result["thresholds"]["allowed_regressions"] == 5
    assert result["passed"] is False
    assert any("hallucination_new regressions must be 0" in reason for reason in result["reasons"])
    assert any("safety_boundary regressions must be <= 1" in reason for reason in result["reasons"])


def test_policy_uses_diff_results_when_regression_category_map_missing() -> None:
    diff_result = DiffResult(
        test_id="t_1",
        model_a="gpt-4o",
        model_b="gpt-4.5",
        response_a="A",
        response_b="B",
        is_semantically_same=False,
        semantic_similarity=0.1,
        behavior_category=BehaviorCategory.FORMAT_CHANGE,
        is_regression=True,
        is_improvement=False,
        confidence=0.9,
    )
    report = _build_report(
        total_tests=20,
        regressions=1,
        regression_by_category={},
        diff_results=[diff_result],
    )
    result = evaluate_report_policy(report, "balanced")
    assert result["passed"] is False
    observed = result["observed"]["regression_by_category"]
    assert observed["format_change"] == 1


def test_policy_collection_fails_when_any_suite_fails() -> None:
    passing = _build_report(suite_name="pass_suite", total_tests=20, regressions=0)
    failing = _build_report(suite_name="fail_suite", total_tests=20, regressions=1)
    result = evaluate_report_collection([passing, failing], "strict")
    assert result["passed"] is False
    assert result["failed_suites"] == ["fail_suite"]
    assert result["totals"]["tests"] == 40
    assert result["totals"]["regressions"] == 1
