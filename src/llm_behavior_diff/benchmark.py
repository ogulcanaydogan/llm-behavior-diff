"""Benchmark summary and advisory-quality helpers for report artifacts."""

from __future__ import annotations

from statistics import median
from typing import Any, Iterable, Sequence

from .schema import BehaviorReport, DiffResult

CRITICAL_REGRESSION_CATEGORIES = ("safety_boundary", "hallucination_new", "format_change")
UNKNOWN_RATE_ADVISORY_THRESHOLD_PCT = 10.0
RUNTIME_OUTLIER_MULTIPLIER = 1.75


def _category_value(raw_category: Any) -> str:
    if hasattr(raw_category, "value"):
        return str(raw_category.value)
    return str(raw_category)


def _rate_pct(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100.0, 4)


def _to_non_negative_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float) and value.is_integer():
        return max(int(value), 0)
    return default


def _is_unknown_diff(result: DiffResult) -> bool:
    if (
        not bool(result.is_semantically_same)
        and not bool(result.is_regression)
        and not bool(result.is_improvement)
    ):
        return True
    return _category_value(result.behavior_category) == "unknown"


def _count_unknown_diffs(report: BehaviorReport) -> int:
    if report.diff_results:
        return sum(1 for result in report.diff_results if _is_unknown_diff(result))

    derived = int(report.total_diffs) - int(report.regressions) - int(report.improvements)
    derived -= int(report.semantic_only_diffs)
    return max(derived, 0)


def _count_critical_regressions_from_results(diff_results: Iterable[DiffResult]) -> dict[str, int]:
    counts = dict.fromkeys(CRITICAL_REGRESSION_CATEGORIES, 0)
    for result in diff_results:
        if not bool(result.is_regression):
            continue
        category = _category_value(result.behavior_category)
        if category in counts:
            counts[category] += 1
    return counts


def _count_critical_regressions(report: BehaviorReport) -> dict[str, int]:
    from_map = dict.fromkeys(CRITICAL_REGRESSION_CATEGORIES, 0)
    for raw_key, raw_value in report.regression_by_category.items():
        category = _category_value(raw_key)
        if category in from_map:
            from_map[category] += _to_non_negative_int(raw_value)

    if any(from_map.values()):
        return from_map

    return _count_critical_regressions_from_results(report.diff_results)


def _suite_metrics(report: BehaviorReport) -> dict[str, Any]:
    processed_from_meta = _to_non_negative_int(report.metadata.get("processed_tests"), default=-1)
    processed_tests = processed_from_meta if processed_from_meta >= 0 else len(report.diff_results)

    failed_from_meta = _to_non_negative_int(report.metadata.get("failed_tests"), default=-1)
    failed_tests = (
        failed_from_meta
        if failed_from_meta >= 0
        else max(int(report.total_tests) - processed_tests, 0)
    )

    total_tests = max(int(report.total_tests), 0)
    regressions = max(int(report.regressions), 0)
    improvements = max(int(report.improvements), 0)
    semantic_only = max(int(report.semantic_only_diffs), 0)
    unknown = _count_unknown_diffs(report)
    duration_seconds = max(float(report.duration_seconds), 0.0)
    throughput_tests_per_min = (
        round((processed_tests / duration_seconds) * 60.0, 4) if duration_seconds > 0 else 0.0
    )

    critical = _count_critical_regressions(report)

    return {
        "report_id": str(report.id),
        "suite_name": report.suite_name,
        "total_tests": total_tests,
        "processed_tests": processed_tests,
        "failed_tests": failed_tests,
        "duration_seconds": round(duration_seconds, 4),
        "throughput_tests_per_min": throughput_tests_per_min,
        "regressions": regressions,
        "improvements": improvements,
        "semantic_only_diffs": semantic_only,
        "unknown_diffs": unknown,
        "regression_rate_pct": _rate_pct(regressions, total_tests),
        "improvement_rate_pct": _rate_pct(improvements, total_tests),
        "semantic_only_rate_pct": _rate_pct(semantic_only, total_tests),
        "unknown_rate_pct": _rate_pct(unknown, total_tests),
        "critical_regressions": critical,
        "advisories": [],
    }


def build_benchmark_summary(reports: Sequence[BehaviorReport]) -> dict[str, Any]:
    """Build deterministic benchmark summary and advisory checks from report artifacts."""
    if not reports:
        raise ValueError("At least one report is required to benchmark.")

    suite_rows = [_suite_metrics(report) for report in reports]
    durations = [float(row["duration_seconds"]) for row in suite_rows]
    median_duration_seconds = median(durations) if durations else 0.0

    runtime_outlier_suites: list[str] = []
    if len(suite_rows) >= 2 and median_duration_seconds > 0:
        threshold = RUNTIME_OUTLIER_MULTIPLIER * median_duration_seconds
        for row in suite_rows:
            if float(row["duration_seconds"]) > threshold:
                suite_name = str(row["suite_name"])
                runtime_outlier_suites.append(suite_name)
                row_advisories = row.get("advisories")
                if isinstance(row_advisories, list):
                    row_advisories.append("runtime_outlier")

    total_tests = sum(int(row["total_tests"]) for row in suite_rows)
    total_processed_tests = sum(int(row["processed_tests"]) for row in suite_rows)
    total_failed_tests = sum(int(row["failed_tests"]) for row in suite_rows)
    total_regressions = sum(int(row["regressions"]) for row in suite_rows)
    total_improvements = sum(int(row["improvements"]) for row in suite_rows)
    total_semantic_only = sum(int(row["semantic_only_diffs"]) for row in suite_rows)
    total_unknown = sum(int(row["unknown_diffs"]) for row in suite_rows)
    total_duration_seconds = round(sum(float(row["duration_seconds"]) for row in suite_rows), 4)
    avg_duration_seconds = round(total_duration_seconds / len(suite_rows), 4) if suite_rows else 0.0
    throughput_tests_per_min = (
        round((total_processed_tests / total_duration_seconds) * 60.0, 4)
        if total_duration_seconds > 0
        else 0.0
    )

    critical_totals = dict.fromkeys(CRITICAL_REGRESSION_CATEGORIES, 0)
    for row in suite_rows:
        critical = row.get("critical_regressions", {})
        if not isinstance(critical, dict):
            continue
        for category in CRITICAL_REGRESSION_CATEGORIES:
            critical_totals[category] += _to_non_negative_int(critical.get(category))

    advisories: list[dict[str, Any]] = []
    if total_failed_tests > 0:
        advisories.append(
            {
                "code": "failed_tests_present",
                "message": "One or more tests failed during suite execution.",
                "value": total_failed_tests,
            }
        )
    if critical_totals["hallucination_new"] > 0:
        advisories.append(
            {
                "code": "hallucination_new_regressions_present",
                "message": "New hallucination regressions detected.",
                "value": critical_totals["hallucination_new"],
            }
        )
    if critical_totals["safety_boundary"] > 0:
        advisories.append(
            {
                "code": "safety_boundary_regressions_present",
                "message": "Safety boundary regressions detected.",
                "value": critical_totals["safety_boundary"],
            }
        )

    unknown_rate_pct = _rate_pct(total_unknown, total_tests)
    if unknown_rate_pct > UNKNOWN_RATE_ADVISORY_THRESHOLD_PCT:
        advisories.append(
            {
                "code": "high_unknown_rate",
                "message": "Unknown diff rate exceeds advisory threshold.",
                "value": unknown_rate_pct,
                "threshold_pct": UNKNOWN_RATE_ADVISORY_THRESHOLD_PCT,
            }
        )

    if runtime_outlier_suites:
        advisories.append(
            {
                "code": "runtime_outlier_suites",
                "message": "One or more suites are runtime outliers vs median duration.",
                "suites": sorted(runtime_outlier_suites),
                "threshold_multiplier": RUNTIME_OUTLIER_MULTIPLIER,
                "median_duration_seconds": round(float(median_duration_seconds), 4),
            }
        )

    return {
        "quality_pack": {
            "name": "fixed_v1",
            "advisory_only": True,
            "advisory_count": len(advisories),
            "has_advisories": bool(advisories),
            "advisories": advisories,
        },
        "total_reports": len(suite_rows),
        "total_tests": total_tests,
        "total_processed_tests": total_processed_tests,
        "total_failed_tests": total_failed_tests,
        "total_duration_seconds": total_duration_seconds,
        "avg_duration_seconds": avg_duration_seconds,
        "median_suite_duration_seconds": round(float(median_duration_seconds), 4),
        "throughput_tests_per_min": throughput_tests_per_min,
        "regression_rate_pct": _rate_pct(total_regressions, total_tests),
        "improvement_rate_pct": _rate_pct(total_improvements, total_tests),
        "semantic_only_rate_pct": _rate_pct(total_semantic_only, total_tests),
        "unknown_rate_pct": unknown_rate_pct,
        "critical_regressions": critical_totals,
        "suites": suite_rows,
    }


__all__ = ["build_benchmark_summary"]
