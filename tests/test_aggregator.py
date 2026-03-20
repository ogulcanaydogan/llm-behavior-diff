"""Tests for comparator-first deterministic aggregator."""

from llm_behavior_diff.aggregator import (
    aggregate_comparator_results,
    summarize_comparator_breakdown,
)
from llm_behavior_diff.comparators.base import ComparatorResult
from llm_behavior_diff.schema import BehaviorCategory, DiffResult
from llm_behavior_diff.schema import TestCase as SuiteCase


def _case(category: str = "reasoning") -> SuiteCase:
    return SuiteCase(
        id="t1",
        prompt="prompt",
        category=category,
        expected_behavior="expected behavior",
    )


def _result(
    *, applies: bool, decision: str, delta: float, confidence: float = 0.8
) -> ComparatorResult:
    return ComparatorResult(
        score_a=0.0,
        score_b=0.0,
        delta=delta,
        applies=applies,
        decision=decision,
        confidence=confidence,
        reason=decision,
    )


def test_aggregator_semantic_priority() -> None:
    aggregated = aggregate_comparator_results(
        test_case=_case(),
        semantic_similarity=0.91,
        semantic_threshold=0.85,
        is_semantically_same=True,
        behavioral=_result(applies=True, decision="regression", delta=-0.6),
        factual=_result(applies=True, decision="hallucination_new", delta=-0.5),
        format_check=_result(applies=True, decision="format_change", delta=-1.0),
    )

    assert aggregated["behavior_category"] == BehaviorCategory.SEMANTIC
    assert aggregated["is_regression"] is False
    assert aggregated["is_improvement"] is False


def test_aggregator_factual_overrides_behavioral() -> None:
    aggregated = aggregate_comparator_results(
        test_case=_case(),
        semantic_similarity=0.2,
        semantic_threshold=0.85,
        is_semantically_same=False,
        behavioral=_result(applies=True, decision="improvement", delta=0.4),
        factual=_result(applies=True, decision="hallucination_new", delta=-0.4),
        format_check=_result(applies=True, decision="instruction_following", delta=0.8),
    )

    assert aggregated["behavior_category"] == BehaviorCategory.HALLUCINATION_NEW
    assert aggregated["is_regression"] is True
    assert aggregated["is_improvement"] is False


def test_aggregator_format_overrides_behavioral() -> None:
    aggregated = aggregate_comparator_results(
        test_case=_case("formatting"),
        semantic_similarity=0.2,
        semantic_threshold=0.85,
        is_semantically_same=False,
        behavioral=_result(applies=True, decision="improvement", delta=0.5),
        factual=_result(applies=False, decision="not_applied", delta=0.0, confidence=0.0),
        format_check=_result(applies=True, decision="format_change", delta=-1.0),
    )

    assert aggregated["behavior_category"] == BehaviorCategory.FORMAT_CHANGE
    assert aggregated["is_regression"] is True
    assert aggregated["is_improvement"] is False


def test_aggregator_behavioral_fallback_and_category_map() -> None:
    aggregated = aggregate_comparator_results(
        test_case=_case("structured_output"),
        semantic_similarity=0.2,
        semantic_threshold=0.85,
        is_semantically_same=False,
        behavioral=_result(applies=True, decision="improvement", delta=0.3),
        factual=_result(applies=False, decision="not_applied", delta=0.0, confidence=0.0),
        format_check=_result(applies=False, decision="not_applied", delta=0.0, confidence=0.0),
    )

    assert aggregated["behavior_category"] == BehaviorCategory.INSTRUCTION_FOLLOWING
    assert aggregated["is_regression"] is False
    assert aggregated["is_improvement"] is True


def test_aggregator_unknown_when_no_comparator_decides() -> None:
    aggregated = aggregate_comparator_results(
        test_case=_case(),
        semantic_similarity=0.2,
        semantic_threshold=0.85,
        is_semantically_same=False,
        behavioral=_result(applies=True, decision="neutral", delta=0.1),
        factual=_result(applies=True, decision="neutral", delta=0.1),
        format_check=_result(applies=True, decision="neutral", delta=0.1),
    )

    assert aggregated["behavior_category"] == BehaviorCategory.UNKNOWN
    assert aggregated["is_regression"] is False
    assert aggregated["is_improvement"] is False
    assert "no deterministic category matched" in aggregated["explanation"].lower()


def test_comparator_summary_counts_metadata_breakdown() -> None:
    diff_1 = DiffResult(
        test_id="t1",
        model_a="a",
        model_b="b",
        response_a="x",
        response_b="y",
        is_semantically_same=True,
        semantic_similarity=0.9,
        behavior_category=BehaviorCategory.SEMANTIC,
        metadata={
            "comparators": {
                "semantic": {"decision": "semantic_same"},
                "behavioral": {"decision": "neutral"},
            }
        },
    )
    diff_2 = DiffResult(
        test_id="t2",
        model_a="a",
        model_b="b",
        response_a="x",
        response_b="z",
        is_semantically_same=False,
        semantic_similarity=0.1,
        behavior_category=BehaviorCategory.KNOWLEDGE_CHANGE,
        metadata={
            "comparators": {
                "semantic": {"decision": "semantic_diff"},
                "behavioral": {"decision": "regression"},
                "factual": {"decision": "knowledge_change"},
                "judge": {"decision": "judge_regression"},
            }
        },
    )

    summary = summarize_comparator_breakdown([diff_1, diff_2])
    assert summary["semantic"]["semantic_same"] == 1
    assert summary["semantic"]["semantic_diff"] == 1
    assert summary["behavioral"]["neutral"] == 1
    assert summary["behavioral"]["regression"] == 1
    assert summary["factual"]["knowledge_change"] == 1
    assert summary["judge"]["judge_regression"] == 1
