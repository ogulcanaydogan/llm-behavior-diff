"""Unit tests for risk-tier report gate policies."""

from __future__ import annotations

from pathlib import Path

import pytest

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


def _write_policy_file(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_policy_strict_fails_when_regressions_non_zero() -> None:
    report = _build_report(total_tests=10, regressions=1)
    result = evaluate_report_policy(report, "strict")
    assert result["passed"] is False
    assert result["thresholds"]["allowed_regressions"] == 0
    assert result["policy_pack"] == "core"
    assert result["policy_source"] == "builtin:core"


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
    assert any("safety_boundary regressions must be 0" in reason for reason in result["reasons"])


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
    assert result["policy_pack"] == "core"
    assert result["policy_source"] == "builtin:core"


def test_risk_averse_pack_uses_tighter_budget_for_balanced() -> None:
    report = _build_report(total_tests=100, regressions=2)
    result = evaluate_report_policy(report, "balanced", policy_pack="risk_averse")
    assert result["thresholds"]["allowed_regressions"] == 1
    assert result["passed"] is False
    assert result["policy_pack"] == "risk_averse"


def test_velocity_pack_balanced_keeps_safety_and_factual_guardrails() -> None:
    report = _build_report(
        total_tests=100,
        regressions=2,
        regression_by_category={BehaviorCategory.FORMAT_CHANGE: 2},
    )
    result = evaluate_report_policy(report, "balanced", policy_pack="velocity")
    assert result["thresholds"]["allowed_regressions"] == 3
    assert result["passed"] is True


def test_custom_policy_file_takes_precedence_over_pack(tmp_path: Path) -> None:
    policy_file = _write_policy_file(
        tmp_path / "custom_policy.yaml",
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
      floor: 3
    critical_category_max: {}
  permissive:
    allowed_regressions:
      type: percent_floor
      percent: 0.20
      floor: 5
    critical_category_max: {}
""",
    )
    report = _build_report(total_tests=100, regressions=3)
    result = evaluate_report_policy(
        report,
        "strict",
        policy_pack="risk_averse",
        policy_file=policy_file,
    )
    assert result["passed"] is True
    assert result["policy_pack"] == "custom_relaxed"
    assert str(result["policy_source"]).startswith("file:")


def test_custom_policy_file_validation_fails_on_missing_tier(tmp_path: Path) -> None:
    policy_file = _write_policy_file(
        tmp_path / "invalid_policy.yaml",
        """
version: v1
tiers:
  strict:
    allowed_regressions:
      type: absolute
      value: 0
    critical_category_max: {}
  balanced:
    allowed_regressions:
      type: percent_floor
      percent: 0.02
      floor: 1
    critical_category_max: {}
""",
    )
    report = _build_report(total_tests=10, regressions=0)
    with pytest.raises(ValueError, match="tier 'permissive' mapping is required"):
        evaluate_report_policy(report, "strict", policy_file=policy_file)


def test_custom_policy_file_validation_fails_on_unknown_category(tmp_path: Path) -> None:
    policy_file = _write_policy_file(
        tmp_path / "invalid_category_policy.yaml",
        """
version: v1
tiers:
  strict:
    allowed_regressions:
      type: absolute
      value: 0
    critical_category_max: {}
  balanced:
    allowed_regressions:
      type: percent_floor
      percent: 0.02
      floor: 1
    critical_category_max:
      made_up_category: 0
  permissive:
    allowed_regressions:
      type: percent_floor
      percent: 0.05
      floor: 2
    critical_category_max: {}
""",
    )
    report = _build_report(total_tests=10, regressions=0)
    with pytest.raises(ValueError, match="unknown category 'made_up_category'"):
        evaluate_report_policy(report, "balanced", policy_file=policy_file)


def test_collection_uses_selected_policy_pack_and_source(tmp_path: Path) -> None:
    policy_file = _write_policy_file(
        tmp_path / "collection_policy.yaml",
        """
version: v1
name: collection_custom
tiers:
  strict:
    allowed_regressions:
      type: absolute
      value: 1
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
      percent: 0.10
      floor: 1
    critical_category_max: {}
""",
    )
    report_a = _build_report(suite_name="suite_a", total_tests=10, regressions=1)
    report_b = _build_report(suite_name="suite_b", total_tests=10, regressions=0)
    result = evaluate_report_collection(
        [report_a, report_b],
        "strict",
        policy_pack="risk_averse",
        policy_file=policy_file,
    )
    assert result["passed"] is True
    assert result["policy_pack"] == "collection_custom"
    assert str(result["policy_source"]).startswith("file:")
    assert all(
        suite_result["policy_pack"] == "collection_custom"
        for suite_result in result["suite_results"]
    )
