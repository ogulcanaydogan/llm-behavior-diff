"""Unit tests for artifact-first benchmark summary aggregation."""

from __future__ import annotations

import pytest

from llm_behavior_diff.benchmark import build_benchmark_summary
from llm_behavior_diff.schema import BehaviorCategory, BehaviorReport


def test_build_benchmark_summary_aggregates_core_metrics() -> None:
    report_a = BehaviorReport(
        id="rpt-a",
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite_a",
        total_tests=10,
        total_diffs=4,
        regressions=1,
        improvements=1,
        semantic_only_diffs=1,
        duration_seconds=20.0,
        regression_by_category={BehaviorCategory.FORMAT_CHANGE: 1},
        metadata={"processed_tests": 9, "failed_tests": 1},
    )
    report_b = BehaviorReport(
        id="rpt-b",
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite_b",
        total_tests=10,
        total_diffs=3,
        regressions=2,
        improvements=0,
        semantic_only_diffs=0,
        duration_seconds=40.0,
        regression_by_category={
            BehaviorCategory.SAFETY_BOUNDARY: 1,
            BehaviorCategory.HALLUCINATION_NEW: 1,
        },
        metadata={"processed_tests": 10, "failed_tests": 0},
    )

    summary = build_benchmark_summary([report_a, report_b])

    assert summary["total_reports"] == 2
    assert summary["total_tests"] == 20
    assert summary["total_processed_tests"] == 19
    assert summary["total_failed_tests"] == 1
    assert summary["total_duration_seconds"] == pytest.approx(60.0)
    assert summary["avg_duration_seconds"] == pytest.approx(30.0)
    assert summary["throughput_tests_per_min"] == pytest.approx(19.0, rel=1e-4)
    assert summary["regression_rate_pct"] == pytest.approx(15.0)
    assert summary["improvement_rate_pct"] == pytest.approx(5.0)
    assert summary["semantic_only_rate_pct"] == pytest.approx(5.0)
    assert summary["unknown_rate_pct"] == pytest.approx(10.0)
    assert summary["critical_regressions"] == {
        "safety_boundary": 1,
        "hallucination_new": 1,
        "format_change": 1,
    }
    assert summary["extended_significance"]["effect_size_method"] == "cohens_h"
    assert summary["extended_significance"]["fdr_method"] == "benjamini_hochberg"
    assert summary["extended_significance"]["regression"]["tested_suites"] == 0
    assert summary["extended_significance"]["improvement"]["tested_suites"] == 0
    assert len(summary["suites"]) == 2


def test_build_benchmark_summary_triggers_fixed_quality_pack_advisories() -> None:
    report_a = BehaviorReport(
        id="rpt-a",
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
        id="rpt-b",
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite_b",
        total_tests=8,
        total_diffs=1,
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

    summary = build_benchmark_summary([report_a, report_b])
    pack = summary["quality_pack"]
    codes = {entry["code"] for entry in pack["advisories"]}

    assert pack["advisory_only"] is True
    assert pack["has_advisories"] is True
    assert "failed_tests_present" in codes
    assert "hallucination_new_regressions_present" in codes
    assert "safety_boundary_regressions_present" in codes
    assert "high_unknown_rate" in codes
    assert "runtime_outlier_suites" in codes


def test_build_benchmark_summary_requires_at_least_one_report() -> None:
    with pytest.raises(ValueError):
        build_benchmark_summary([])


def test_build_benchmark_summary_adds_extended_significance_and_effect_advisory() -> None:
    report_a = BehaviorReport(
        id="rpt-a",
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite_a",
        total_tests=10,
        total_diffs=4,
        regressions=4,
        improvements=0,
        semantic_only_diffs=0,
        duration_seconds=10.0,
        metadata={
            "processed_tests": 10,
            "failed_tests": 0,
            "significance": {
                "regression_rate": {"point": 0.4, "p_value_two_sided": 0.01},
                "improvement_rate": {"point": 0.0, "p_value_two_sided": 1.0},
            },
        },
    )
    report_b = BehaviorReport(
        id="rpt-b",
        model_a="gpt-4o",
        model_b="gpt-4.5",
        suite_name="suite_b",
        total_tests=10,
        total_diffs=3,
        regressions=3,
        improvements=0,
        semantic_only_diffs=0,
        duration_seconds=12.0,
        metadata={
            "processed_tests": 10,
            "failed_tests": 0,
            "significance": {
                "regression_rate": {"point": 0.3, "p_value_two_sided": 0.04},
                "improvement_rate": {"point": 0.0, "p_value_two_sided": 1.0},
            },
        },
    )

    summary = build_benchmark_summary([report_a, report_b])
    extended = summary["extended_significance"]
    assert extended["regression"]["tested_suites"] == 2
    assert extended["regression"]["fdr_significant_count"] == 2
    assert extended["improvement"]["tested_suites"] == 2
    advisory_codes = {entry["code"] for entry in summary["quality_pack"]["advisories"]}
    assert "regression_fdr_effect_signal" in advisory_codes

    suite_rows = summary["suites"]
    assert suite_rows[0]["extended_significance"]["regression"]["effect_size_magnitude"] == "large"
    assert suite_rows[0]["extended_significance"]["regression"]["fdr_significant"] is True
