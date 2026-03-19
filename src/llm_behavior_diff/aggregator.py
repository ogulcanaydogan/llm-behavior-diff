"""Comparator result aggregation for deterministic Phase 2 pipeline."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable

from .comparators.base import ComparatorResult
from .schema import BehaviorCategory, DiffResult, TestCase

_INSTRUCTION_CATEGORY_HINTS = ("format", "constraint", "structured_output", "instruction")


def infer_behavior_category(test_category: str) -> BehaviorCategory:
    """Map a test category to deterministic behavioral category."""
    normalized = test_category.strip().lower()
    if any(hint in normalized for hint in _INSTRUCTION_CATEGORY_HINTS):
        return BehaviorCategory.INSTRUCTION_FOLLOWING
    return BehaviorCategory.KNOWLEDGE_CHANGE


def aggregate_comparator_results(
    *,
    test_case: TestCase,
    semantic_similarity: float,
    semantic_threshold: float,
    is_semantically_same: bool,
    behavioral: ComparatorResult,
    factual: ComparatorResult,
    format_check: ComparatorResult,
) -> dict[str, Any]:
    """Aggregate comparator outputs into final diff classification."""
    semantic_decision = "semantic_same" if is_semantically_same else "semantic_diff"
    semantic = ComparatorResult(
        score_a=semantic_similarity,
        score_b=semantic_threshold,
        delta=semantic_similarity - semantic_threshold,
        applies=True,
        decision=semantic_decision,
        confidence=max(0.8, semantic_similarity) if is_semantically_same else 0.5,
        reason=(
            "Responses are semantically equivalent."
            if is_semantically_same
            else "Responses are semantically different."
        ),
    )

    comparators = {
        "semantic": semantic.to_dict(),
        "behavioral": behavioral.to_dict(),
        "factual": factual.to_dict(),
        "format": format_check.to_dict(),
    }

    if is_semantically_same:
        return {
            "behavior_category": BehaviorCategory.SEMANTIC,
            "is_regression": False,
            "is_improvement": False,
            "confidence": semantic.confidence,
            "explanation": semantic.reason,
            "comparators": comparators,
        }

    if factual.applies and factual.decision in {
        "hallucination_new",
        "hallucination_fixed",
        "knowledge_change",
    }:
        if factual.decision == "hallucination_new":
            return {
                "behavior_category": BehaviorCategory.HALLUCINATION_NEW,
                "is_regression": True,
                "is_improvement": False,
                "confidence": factual.confidence,
                "explanation": factual.reason,
                "comparators": comparators,
            }

        if factual.decision == "hallucination_fixed":
            return {
                "behavior_category": BehaviorCategory.HALLUCINATION_FIXED,
                "is_regression": False,
                "is_improvement": True,
                "confidence": factual.confidence,
                "explanation": factual.reason,
                "comparators": comparators,
            }

        if factual.delta >= 0.20:
            return {
                "behavior_category": BehaviorCategory.KNOWLEDGE_CHANGE,
                "is_regression": False,
                "is_improvement": True,
                "confidence": factual.confidence,
                "explanation": factual.reason,
                "comparators": comparators,
            }
        if factual.delta <= -0.20:
            return {
                "behavior_category": BehaviorCategory.KNOWLEDGE_CHANGE,
                "is_regression": True,
                "is_improvement": False,
                "confidence": factual.confidence,
                "explanation": factual.reason,
                "comparators": comparators,
            }

        return {
            "behavior_category": BehaviorCategory.KNOWLEDGE_CHANGE,
            "is_regression": False,
            "is_improvement": False,
            "confidence": factual.confidence,
            "explanation": factual.reason,
            "comparators": comparators,
        }

    if format_check.applies and format_check.decision in {"format_change", "instruction_following"}:
        if format_check.decision == "format_change":
            return {
                "behavior_category": BehaviorCategory.FORMAT_CHANGE,
                "is_regression": True,
                "is_improvement": False,
                "confidence": format_check.confidence,
                "explanation": format_check.reason,
                "comparators": comparators,
            }
        return {
            "behavior_category": BehaviorCategory.INSTRUCTION_FOLLOWING,
            "is_regression": False,
            "is_improvement": True,
            "confidence": format_check.confidence,
            "explanation": format_check.reason,
            "comparators": comparators,
        }

    if behavioral.decision in {"improvement", "regression"}:
        return {
            "behavior_category": infer_behavior_category(test_case.category),
            "is_regression": behavioral.decision == "regression",
            "is_improvement": behavioral.decision == "improvement",
            "confidence": behavioral.confidence,
            "explanation": behavioral.reason,
            "comparators": comparators,
        }

    return {
        "behavior_category": BehaviorCategory.UNKNOWN,
        "is_regression": False,
        "is_improvement": False,
        "confidence": max(0.5, behavioral.confidence),
        "explanation": "Comparator pipeline detected differences but no deterministic category matched.",
        "comparators": comparators,
    }


def summarize_comparator_breakdown(diff_results: Iterable[DiffResult]) -> dict[str, dict[str, int]]:
    """Build comparator decision counts across a run."""
    summary: dict[str, Counter[str]] = defaultdict(Counter)

    for result in diff_results:
        comparators = result.metadata.get("comparators", {})
        if not isinstance(comparators, dict):
            continue
        for comparator_name, payload in comparators.items():
            if not isinstance(payload, dict):
                continue
            decision = payload.get("decision", "unknown")
            summary[comparator_name][str(decision)] += 1

    return {name: dict(counter) for name, counter in summary.items()}

