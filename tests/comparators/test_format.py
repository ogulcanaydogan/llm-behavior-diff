"""Tests for deterministic format comparator."""

from llm_behavior_diff.comparators.format import FormatComparator
from llm_behavior_diff.schema import TestCase as SuiteCase


def _case(prompt: str, expected_behavior: str = "") -> SuiteCase:
    return SuiteCase(
        id="t1",
        prompt=prompt,
        category="instruction_following",
        expected_behavior=expected_behavior,
    )


def test_format_not_applied_without_constraints() -> None:
    comparator = FormatComparator()
    result = comparator.compare(
        test_case=_case("Explain photosynthesis."),
        response_a="Plants convert light into energy.",
        response_b="Plants use sunlight for energy.",
    )

    assert result.applies is False
    assert result.decision == "not_applied"


def test_format_json_instruction_following() -> None:
    comparator = FormatComparator()
    result = comparator.compare(
        test_case=_case("Return valid JSON with keys name and age."),
        response_a="name: Alice, age: 30",
        response_b='{"name": "Alice", "age": 30}',
    )

    assert result.applies is True
    assert result.decision == "instruction_following"
    assert result.delta == 1.0


def test_format_markdown_table_regression() -> None:
    comparator = FormatComparator()
    result = comparator.compare(
        test_case=_case("Respond as a markdown table with columns Name and Score."),
        response_a="| Name | Score |\n| --- | --- |\n| A | 10 |",
        response_b="Name: A, Score: 10",
    )

    assert result.applies is True
    assert result.decision == "format_change"
    assert result.delta == -1.0


def test_format_exact_sentence_count() -> None:
    comparator = FormatComparator()
    result = comparator.compare(
        test_case=_case("Answer in exactly 2 sentences."),
        response_a="One sentence only.",
        response_b="Sentence one. Sentence two.",
    )

    assert result.applies is True
    assert result.decision == "instruction_following"


def test_format_yes_no_only() -> None:
    comparator = FormatComparator()
    result = comparator.compare(
        test_case=_case("Respond only with yes or no."),
        response_a="Maybe",
        response_b="Yes",
    )

    assert result.applies is True
    assert result.decision == "instruction_following"
