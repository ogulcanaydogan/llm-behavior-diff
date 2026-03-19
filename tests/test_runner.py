"""Tests for suite loading, resiliency, pricing, and aggregation behavior."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from llm_behavior_diff.runner import (
    AsyncRateLimiter,
    BehaviorDiffRunner,
    PriceSpec,
    build_behavior_report,
    compute_backoff_seconds,
    compute_estimated_cost_usd,
    infer_behavior_category,
    is_retryable_error,
    load_pricing_overrides,
    load_test_suite,
    resolve_provider,
    score_expected_behavior_coverage,
)
from llm_behavior_diff.schema import BehaviorCategory, DiffResult
from llm_behavior_diff.schema import TestCase as SuiteCase
from llm_behavior_diff.schema import TestSuite as SuiteDefinition


class StubAdapter:
    """Minimal async adapter stub for runner tests."""

    def __init__(
        self,
        responses: dict[str, str],
        metadata: dict[str, dict[str, Any]] | None = None,
        fail_on: set[str] | None = None,
        failure_message: str = "upstream API error",
        transient_failures: dict[str, int] | None = None,
    ) -> None:
        self.responses = responses
        self.metadata = metadata or {}
        self.fail_on = fail_on or set()
        self.failure_message = failure_message
        self.transient_failures = transient_failures or {}
        self.call_count: dict[str, int] = {}

    async def generate(
        self, prompt: str, max_tokens: int = 2048, temperature: float = 0.7, **kwargs: Any
    ) -> tuple[str, dict[str, Any]]:
        del max_tokens, temperature, kwargs
        self.call_count[prompt] = self.call_count.get(prompt, 0) + 1

        remaining_transient_failures = self.transient_failures.get(prompt, 0)
        if remaining_transient_failures > 0:
            self.transient_failures[prompt] = remaining_transient_failures - 1
            raise RuntimeError("429 rate limit")

        if prompt in self.fail_on:
            raise RuntimeError(self.failure_message)

        return self.responses[prompt], self.metadata.get(prompt, {})


class StubComparator:
    """Deterministic semantic comparator that avoids external model dependencies."""

    def compare(self, text_a: str, text_b: str) -> tuple[float, bool]:
        if text_a == text_b:
            return 1.0, True
        return 0.30, False


class PromptAgnosticAdapter:
    """Adapter stub that returns one fixed response regardless of prompt."""

    def __init__(
        self,
        response_text: str = '{"winner":"TIE","confidence":0.5,"reason":"No change"}',
        metadata: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        self.response_text = response_text
        self.metadata = metadata or {}
        self.error_message = error_message
        self.calls: list[str] = []

    async def generate(
        self, prompt: str, max_tokens: int = 2048, temperature: float = 0.7, **kwargs: Any
    ) -> tuple[str, dict[str, Any]]:
        del max_tokens, temperature, kwargs
        self.calls.append(prompt)
        if self.error_message:
            raise RuntimeError(self.error_message)
        return self.response_text, dict(self.metadata)


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_load_test_suite_valid(tmp_path: Path) -> None:
    suite_path = _write(
        tmp_path / "suite.yaml",
        """
name: valid_suite
description: test suite
test_cases:
  - id: t1
    prompt: "What is 2+2?"
    category: arithmetic
    expected_behavior: Should answer 4
""".strip(),
    )

    suite = load_test_suite(suite_path)
    assert suite.name == "valid_suite"
    assert len(suite.test_cases) == 1


def test_load_test_suite_invalid_yaml(tmp_path: Path) -> None:
    suite_path = _write(tmp_path / "broken.yaml", "name: [broken")
    with pytest.raises(ValueError, match="Invalid YAML"):
        load_test_suite(suite_path)


def test_load_test_suite_validation_error(tmp_path: Path) -> None:
    suite_path = _write(
        tmp_path / "invalid_schema.yaml",
        """
name: invalid_suite
description: missing required fields in test case
test_cases:
  - id: t1
    prompt: "hello"
""".strip(),
    )
    with pytest.raises(ValueError, match="Suite validation failed"):
        load_test_suite(suite_path)


def test_provider_resolution() -> None:
    assert resolve_provider("gpt-4o") == "openai"
    assert resolve_provider("o1-preview") == "openai"
    assert resolve_provider("o3-mini") == "openai"
    assert resolve_provider("claude-3-5-sonnet") == "anthropic"
    with pytest.raises(ValueError, match="Unsupported model"):
        resolve_provider("gemini-1.5-pro")


def test_expected_behavior_coverage_and_category_mapping() -> None:
    score = score_expected_behavior_coverage(
        "Should include Paris as the capital of France",
        "Paris is the capital city of France.",
    )
    assert score == pytest.approx(0.625, abs=0.01)

    assert infer_behavior_category("formatting") == BehaviorCategory.INSTRUCTION_FOLLOWING
    assert infer_behavior_category("constraint_compliance") == BehaviorCategory.INSTRUCTION_FOLLOWING
    assert infer_behavior_category("factual_knowledge") == BehaviorCategory.KNOWLEDGE_CHANGE


def test_retry_error_classification_and_backoff(monkeypatch) -> None:
    assert is_retryable_error(RuntimeError("429 too many requests")) is True
    assert is_retryable_error(RuntimeError("503 service unavailable")) is True
    assert is_retryable_error(RuntimeError("invalid request format")) is False

    monkeypatch.setattr("llm_behavior_diff.runner.random.uniform", lambda _a, _b: 0.0)
    assert compute_backoff_seconds(retry_index=0) == pytest.approx(0.5)
    assert compute_backoff_seconds(retry_index=1) == pytest.approx(1.0)
    assert compute_backoff_seconds(retry_index=2) == pytest.approx(2.0)


@pytest.mark.asyncio
async def test_rate_limiter_respects_min_interval(monkeypatch) -> None:
    clock = {"now": 0.0}
    sleeps: list[float] = []

    def fake_monotonic() -> float:
        return clock["now"]

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr("llm_behavior_diff.runner.time.monotonic", fake_monotonic)
    monkeypatch.setattr("llm_behavior_diff.runner.asyncio.sleep", fake_sleep)

    limiter = AsyncRateLimiter(rate_limit_rps=2.0)  # 0.5 second minimum interval
    await limiter.wait_turn()
    await limiter.wait_turn()
    await limiter.wait_turn()

    assert sleeps == [0.5, 0.5]


@pytest.mark.asyncio
async def test_runner_heuristics_and_aggregation() -> None:
    suite = SuiteDefinition(
        name="heuristic_suite",
        description="Runner behavior tests",
        test_cases=[
            SuiteCase(
                id="t_improve",
                prompt="prompt_improve",
                category="formatting",
                expected_behavior="alpha beta",
            ),
            SuiteCase(
                id="t_regress",
                prompt="prompt_regress",
                category="factual_knowledge",
                expected_behavior="delta epsilon",
            ),
            SuiteCase(
                id="t_same",
                prompt="prompt_same",
                category="reasoning",
                expected_behavior="shared text",
            ),
        ],
    )

    adapter_a = StubAdapter(
        {
            "prompt_improve": "alpha",
            "prompt_regress": "delta epsilon",
            "prompt_same": "shared answer",
        }
    )
    adapter_b = StubAdapter(
        {
            "prompt_improve": "alpha beta gamma",
            "prompt_regress": "delta",
            "prompt_same": "shared answer",
        }
    )

    runner = BehaviorDiffRunner(
        model_a="gpt-4o",
        model_b="claude-3-sonnet",
        max_workers=2,
        adapter_a=adapter_a,
        adapter_b=adapter_b,
        semantic_comparator=StubComparator(),
    )

    report = await runner.run_suite(suite)

    assert report.total_tests == 3
    assert report.improvements == 1
    assert report.regressions == 1
    assert report.semantic_only_diffs == 0
    assert report.total_diffs == 2

    assert report.improvement_by_category[BehaviorCategory.INSTRUCTION_FOLLOWING] == 1
    assert report.regression_by_category[BehaviorCategory.KNOWLEDGE_CHANGE] == 1
    assert report.metadata["processed_tests"] == 3
    assert report.metadata["failed_tests"] == 0
    assert report.metadata["pricing_source"] in {"builtin", "none"}
    assert "comparator_summary" in report.metadata
    assert report.metadata["comparator_summary"]["semantic"]["semantic_same"] == 1
    assert report.metadata["comparator_summary"]["semantic"]["semantic_diff"] == 2
    assert "significance" in report.metadata
    significance = report.metadata["significance"]
    assert significance["method"] == "bootstrap"
    assert significance["confidence_level"] == 0.95
    assert significance["resamples"] == 5000
    assert significance["seed"] == 42
    assert significance["sample_size"] == 3
    assert 0.0 <= significance["regression_rate"]["point"] <= 1.0
    assert 0.0 <= significance["improvement_rate"]["point"] <= 1.0

    by_id = {diff.test_id: diff for diff in report.diff_results}
    assert by_id["t_improve"].is_improvement is True
    assert by_id["t_improve"].behavior_category == BehaviorCategory.INSTRUCTION_FOLLOWING
    assert set(by_id["t_improve"].metadata["comparators"].keys()) == {
        "semantic",
        "behavioral",
        "factual",
        "format",
    }
    assert by_id["t_regress"].is_regression is True
    assert by_id["t_regress"].behavior_category == BehaviorCategory.KNOWLEDGE_CHANGE
    assert by_id["t_same"].is_semantically_same is True
    assert by_id["t_same"].behavior_category == BehaviorCategory.SEMANTIC


@pytest.mark.asyncio
async def test_runner_retry_flow_for_transient_errors(monkeypatch) -> None:
    suite = SuiteDefinition(
        name="retry_suite",
        description="Retry behavior",
        test_cases=[
            SuiteCase(
                id="t_retry",
                prompt="prompt_retry",
                category="reasoning",
                expected_behavior="ok",
            )
        ],
    )

    adapter_a = StubAdapter(
        responses={"prompt_retry": "ok"},
        metadata={"prompt_retry": {"input_tokens": 100, "output_tokens": 50}},
        transient_failures={"prompt_retry": 2},
    )
    adapter_b = StubAdapter(
        responses={"prompt_retry": "ok"},
        metadata={"prompt_retry": {"input_tokens": 80, "output_tokens": 40}},
    )

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("llm_behavior_diff.runner.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("llm_behavior_diff.runner.random.uniform", lambda _a, _b: 0.0)

    runner = BehaviorDiffRunner(
        model_a="gpt-4o",
        model_b="claude-3-sonnet",
        max_retries=3,
        adapter_a=adapter_a,
        adapter_b=adapter_b,
        semantic_comparator=StubComparator(),
    )

    report = await runner.run_suite(suite)
    assert report.metadata["failed_tests"] == 0
    assert adapter_a.call_count["prompt_retry"] == 3
    assert sleeps[:2] == [0.5, 1.0]
    assert report.diff_results[0].metadata["model_a"]["retry_attempts"] == 2


@pytest.mark.asyncio
async def test_runner_continue_on_error_keeps_processing() -> None:
    suite = SuiteDefinition(
        name="continue_suite",
        description="Continue on error behavior",
        test_cases=[
            SuiteCase(
                id="t_ok",
                prompt="prompt_ok",
                category="reasoning",
                expected_behavior="ok",
            ),
            SuiteCase(
                id="t_fail",
                prompt="prompt_fail",
                category="reasoning",
                expected_behavior="ok",
            ),
        ],
    )

    adapter_a = StubAdapter(
        responses={"prompt_ok": "same", "prompt_fail": "same"},
        metadata={"prompt_ok": {"input_tokens": 10, "output_tokens": 5}},
    )
    adapter_b = StubAdapter(
        responses={"prompt_ok": "same", "prompt_fail": "different"},
        fail_on={"prompt_fail"},
        failure_message="validation error",
    )

    runner = BehaviorDiffRunner(
        model_a="gpt-4o",
        model_b="claude-3-sonnet",
        continue_on_error=True,
        max_retries=2,
        adapter_a=adapter_a,
        adapter_b=adapter_b,
        semantic_comparator=StubComparator(),
    )

    report = await runner.run_suite(suite)
    assert report.metadata["processed_tests"] == 1
    assert report.metadata["failed_tests"] == 1
    assert len(report.metadata["errors"]) == 1
    assert report.metadata["errors"][0]["test_id"] == "t_fail"
    assert len(report.diff_results) == 1
    assert report.diff_results[0].test_id == "t_ok"


@pytest.mark.asyncio
async def test_runner_fail_fast_error_message_contains_test_and_model() -> None:
    suite = SuiteDefinition(
        name="fail_fast_suite",
        description="Failure handling",
        test_cases=[
            SuiteCase(
                id="t_fail",
                prompt="prompt_fail",
                category="formatting",
                expected_behavior="ok",
            )
        ],
    )

    adapter_a = StubAdapter({"prompt_fail": "ok"})
    adapter_b = StubAdapter({"prompt_fail": "nope"}, fail_on={"prompt_fail"})

    runner = BehaviorDiffRunner(
        model_a="gpt-4o",
        model_b="claude-3-sonnet",
        adapter_a=adapter_a,
        adapter_b=adapter_b,
        semantic_comparator=StubComparator(),
    )

    with pytest.raises(RuntimeError, match="t_fail.*claude-3-sonnet"):
        await runner.run_suite(suite)


def test_pricing_loader_and_cost_estimation(tmp_path: Path) -> None:
    pricing_path = _write(
        tmp_path / "pricing.yaml",
        """
gpt-4o:
  input_per_1m: 6
  output_per_1m: 16
custom-model:
  input_per_1m: 1.5
  output_per_1m: 2.5
""".strip(),
    )

    overrides = load_pricing_overrides(pricing_path)
    assert overrides["gpt-4o"]["input_per_1m"] == 6.0
    assert overrides["custom-model"]["output_per_1m"] == 2.5

    usage = {
        "gpt-4o": {"input_tokens": 1_000_000, "output_tokens": 500_000, "tokens_used": 1_500_000},
        "unknown-model": {"input_tokens": 50_000, "output_tokens": 50_000, "tokens_used": 100_000},
        "total": {"input_tokens": 1_050_000, "output_tokens": 550_000, "tokens_used": 1_600_000},
    }
    prices = {"gpt-4o": PriceSpec(input_per_1m=5.0, output_per_1m=15.0, source="builtin")}
    estimated_cost, pricing_source, unpriced_models = compute_estimated_cost_usd(usage, prices)

    assert estimated_cost["gpt-4o"] == pytest.approx(12.5)
    assert estimated_cost["unknown-model"] == 0.0
    assert estimated_cost["total"] == pytest.approx(12.5)
    assert pricing_source == "builtin"
    assert unpriced_models == ["unknown-model"]


@pytest.mark.asyncio
async def test_runner_cost_tracking_with_pricing_file(tmp_path: Path) -> None:
    suite = SuiteDefinition(
        name="cost_suite",
        description="Cost calculation",
        test_cases=[
            SuiteCase(
                id="t_cost",
                prompt="prompt_cost",
                category="reasoning",
                expected_behavior="same",
            )
        ],
    )

    pricing_path = _write(
        tmp_path / "pricing.json",
        """
{
  "gpt-4o": {"input_per_1m": 10, "output_per_1m": 20},
  "claude-3-sonnet": {"input_per_1m": 3, "output_per_1m": 12}
}
""".strip(),
    )

    adapter_a = StubAdapter(
        responses={"prompt_cost": "same"},
        metadata={"prompt_cost": {"input_tokens": 1000, "output_tokens": 500}},
    )
    adapter_b = StubAdapter(
        responses={"prompt_cost": "same"},
        metadata={"prompt_cost": {"input_tokens": 2000, "output_tokens": 1000}},
    )

    runner = BehaviorDiffRunner(
        model_a="gpt-4o",
        model_b="claude-3-sonnet",
        adapter_a=adapter_a,
        adapter_b=adapter_b,
        semantic_comparator=StubComparator(),
        pricing_file=pricing_path,
    )

    report = await runner.run_suite(suite)
    token_usage = report.metadata["token_usage"]
    assert token_usage["gpt-4o"]["tokens_used"] == 1500
    assert token_usage["claude-3-sonnet"]["tokens_used"] == 3000

    estimated_cost = report.metadata["estimated_cost_usd"]
    assert estimated_cost["gpt-4o"] == pytest.approx((1000 / 1_000_000) * 10 + (500 / 1_000_000) * 20)
    assert estimated_cost["claude-3-sonnet"] == pytest.approx(
        (2000 / 1_000_000) * 3 + (1000 / 1_000_000) * 12
    )
    assert estimated_cost["total"] == pytest.approx(
        estimated_cost["gpt-4o"] + estimated_cost["claude-3-sonnet"]
    )
    assert report.metadata["pricing_source"] == "file"


@pytest.mark.asyncio
async def test_runner_does_not_call_judge_when_flag_not_set() -> None:
    suite = SuiteDefinition(
        name="judge_disabled_suite",
        description="Judge is opt-in only",
        test_cases=[
            SuiteCase(
                id="t_diff",
                prompt="prompt_diff",
                category="reasoning",
                expected_behavior="expected",
            )
        ],
    )

    adapter_a = StubAdapter(responses={"prompt_diff": "response_a"})
    adapter_b = StubAdapter(responses={"prompt_diff": "response_b"})
    judge_adapter = PromptAgnosticAdapter(error_message="judge should not run")

    runner = BehaviorDiffRunner(
        model_a="gpt-4o",
        model_b="claude-3-sonnet",
        adapter_a=adapter_a,
        adapter_b=adapter_b,
        judge_adapter=judge_adapter,
        semantic_comparator=StubComparator(),
    )

    report = await runner.run_suite(suite)
    assert report.metadata["judge_enabled"] is False
    assert report.metadata["judge_model"] is None
    assert "judge" not in report.metadata["comparator_summary"]
    assert len(judge_adapter.calls) == 0


@pytest.mark.asyncio
async def test_runner_calls_judge_only_for_semantic_diffs() -> None:
    suite = SuiteDefinition(
        name="judge_diff_only_suite",
        description="Judge should run only for semantic diffs",
        test_cases=[
            SuiteCase(
                id="t_same",
                prompt="prompt_same",
                category="reasoning",
                expected_behavior="same",
            ),
            SuiteCase(
                id="t_diff",
                prompt="prompt_diff",
                category="reasoning",
                expected_behavior="better",
            ),
        ],
    )

    adapter_a = StubAdapter(responses={"prompt_same": "same", "prompt_diff": "response_a"})
    adapter_b = StubAdapter(responses={"prompt_same": "same", "prompt_diff": "response_b"})
    judge_adapter = PromptAgnosticAdapter(
        response_text='{"winner":"B","confidence":0.82,"reason":"B follows expected behavior better."}',
        metadata={"input_tokens": 120, "output_tokens": 60},
    )

    runner = BehaviorDiffRunner(
        model_a="gpt-4o",
        model_b="claude-3-sonnet",
        judge_model="gpt-4o",
        adapter_a=adapter_a,
        adapter_b=adapter_b,
        judge_adapter=judge_adapter,
        semantic_comparator=StubComparator(),
    )

    report = await runner.run_suite(suite)
    by_id = {diff.test_id: diff for diff in report.diff_results}

    assert report.metadata["judge_enabled"] is True
    assert report.metadata["judge_model"] == "gpt-4o"
    assert len(judge_adapter.calls) == 1
    assert "judge" not in by_id["t_same"].metadata["comparators"]
    assert by_id["t_diff"].metadata["comparators"]["judge"]["decision"] == "judge_improvement"
    assert by_id["t_diff"].metadata["judge"]["tokens_used"] == 180


@pytest.mark.asyncio
async def test_runner_judge_errors_are_non_fatal() -> None:
    suite = SuiteDefinition(
        name="judge_error_suite",
        description="Judge failures should not fail the run",
        test_cases=[
            SuiteCase(
                id="t_diff",
                prompt="prompt_diff",
                category="reasoning",
                expected_behavior="expected",
            )
        ],
    )

    adapter_a = StubAdapter(responses={"prompt_diff": "response_a"})
    adapter_b = StubAdapter(responses={"prompt_diff": "response_b"})
    judge_adapter = PromptAgnosticAdapter(error_message="timeout")

    runner = BehaviorDiffRunner(
        model_a="gpt-4o",
        model_b="claude-3-sonnet",
        judge_model="gpt-4o",
        max_retries=0,
        adapter_a=adapter_a,
        adapter_b=adapter_b,
        judge_adapter=judge_adapter,
        semantic_comparator=StubComparator(),
    )

    report = await runner.run_suite(suite)
    diff = report.diff_results[0]

    assert report.metadata["failed_tests"] == 0
    assert diff.metadata["comparators"]["judge"]["decision"] == "judge_error"
    assert "error" in diff.metadata["judge"]


@pytest.mark.asyncio
async def test_runner_cost_tracking_includes_judge_usage() -> None:
    suite = SuiteDefinition(
        name="judge_cost_suite",
        description="Judge token/cost should be included in totals",
        test_cases=[
            SuiteCase(
                id="t_diff",
                prompt="prompt_diff",
                category="reasoning",
                expected_behavior="expected behavior",
            )
        ],
    )

    adapter_a = StubAdapter(
        responses={"prompt_diff": "response_a"},
        metadata={"prompt_diff": {"input_tokens": 100, "output_tokens": 50}},
    )
    adapter_b = StubAdapter(
        responses={"prompt_diff": "response_b"},
        metadata={"prompt_diff": {"input_tokens": 200, "output_tokens": 100}},
    )
    judge_adapter = PromptAgnosticAdapter(
        response_text='{"winner":"TIE","confidence":0.5,"reason":"No change"}',
        metadata={"input_tokens": 300, "output_tokens": 150},
    )

    runner = BehaviorDiffRunner(
        model_a="gpt-3.5-turbo",
        model_b="claude-3-sonnet",
        judge_model="gpt-4o",
        adapter_a=adapter_a,
        adapter_b=adapter_b,
        judge_adapter=judge_adapter,
        semantic_comparator=StubComparator(),
    )

    report = await runner.run_suite(suite)
    token_usage = report.metadata["token_usage"]
    estimated_cost = report.metadata["estimated_cost_usd"]

    assert token_usage["gpt-3.5-turbo"]["tokens_used"] == 150
    assert token_usage["claude-3-sonnet"]["tokens_used"] == 300
    assert token_usage["gpt-4o"]["tokens_used"] == 450
    assert token_usage["total"]["tokens_used"] == 900

    assert estimated_cost["gpt-3.5-turbo"] == pytest.approx(0.000125)
    assert estimated_cost["claude-3-sonnet"] == pytest.approx(0.0021)
    assert estimated_cost["gpt-4o"] == pytest.approx(0.00375)
    assert estimated_cost["total"] == pytest.approx(0.005975)


def test_build_behavior_report_counts_unknown_and_semantic_only_diffs() -> None:
    results = [
        DiffResult(
            test_id="s1",
            model_a="a",
            model_b="b",
            response_a="one",
            response_b="two",
            is_semantically_same=True,
            semantic_similarity=0.9,
            behavior_category=BehaviorCategory.SEMANTIC,
        ),
        DiffResult(
            test_id="u1",
            model_a="a",
            model_b="b",
            response_a="x",
            response_b="y",
            is_semantically_same=False,
            semantic_similarity=0.2,
            behavior_category=BehaviorCategory.UNKNOWN,
        ),
    ]

    report = build_behavior_report(
        model_a="a",
        model_b="b",
        suite_name="suite",
        total_tests=2,
        diff_results=results,
        duration_seconds=1.0,
    )

    assert report.semantic_only_diffs == 1
    assert report.total_diffs == 2
    assert report.metadata["unknown_diffs"] == 1
