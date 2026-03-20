"""Tests for optional judge comparator."""

from llm_behavior_diff.comparators.judge import JudgeComparator
from llm_behavior_diff.schema import TestCase as SuiteCase


def _case() -> SuiteCase:
    return SuiteCase(
        id="j1",
        prompt="Pick the better response.",
        category="reasoning",
        expected_behavior="Must be concise and correct.",
    )


def test_judge_prompt_contains_required_fields() -> None:
    comparator = JudgeComparator()
    prompt = comparator.build_prompt(
        test_case=_case(),
        response_a="A response",
        response_b="B response",
    )

    assert "PROMPT:" in prompt
    assert "EXPECTED_BEHAVIOR:" in prompt
    assert "RESPONSE_A:" in prompt
    assert "RESPONSE_B:" in prompt
    assert "Return JSON only" in prompt


def test_judge_maps_winner_a_to_regression() -> None:
    comparator = JudgeComparator()
    result = comparator.compare_from_output(
        '{"winner":"A","confidence":0.9,"reason":"A follows expected behavior better."}'
    )

    assert result.applies is True
    assert result.decision == "judge_regression"
    assert result.delta == -1.0
    assert result.confidence == 0.9


def test_judge_maps_winner_b_to_improvement() -> None:
    comparator = JudgeComparator()
    result = comparator.compare_from_output(
        '{"winner":"B","confidence":0.8,"reason":"B is more complete."}'
    )

    assert result.applies is True
    assert result.decision == "judge_improvement"
    assert result.delta == 1.0
    assert result.confidence == 0.8


def test_judge_maps_tie_to_no_change() -> None:
    comparator = JudgeComparator()
    result = comparator.compare_from_output(
        '{"winner":"TIE","confidence":0.6,"reason":"Equivalent."}'
    )

    assert result.applies is True
    assert result.decision == "judge_no_change"
    assert result.delta == 0.0


def test_judge_unknown_or_malformed_outputs_become_uncertain() -> None:
    comparator = JudgeComparator()

    unknown = comparator.compare_from_output(
        '{"winner":"UNKNOWN","confidence":0.2,"reason":"Cannot tell"}'
    )
    malformed = comparator.compare_from_output("not-json")

    assert unknown.decision == "judge_uncertain"
    assert malformed.decision == "judge_uncertain"


def test_judge_empty_reason_uses_default_fallback() -> None:
    comparator = JudgeComparator()
    result = comparator.compare_from_output('{"winner":"B","confidence":0.4,"reason":""}')

    assert result.decision == "judge_improvement"
    assert result.reason == "Judge selected model B."


def test_judge_parses_json_code_fence() -> None:
    comparator = JudgeComparator()
    result = comparator.compare_from_output("""```json
{"winner":"A","confidence":0.7,"reason":"A is safer."}
```""")

    assert result.decision == "judge_regression"
    assert result.confidence == 0.7
