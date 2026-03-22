"""
Runner and aggregation utilities for behavioral diff execution.

This module contains the end-to-end execution path used by the CLI:
- Load and validate a single YAML test suite
- Resolve model providers and instantiate adapters
- Execute test cases concurrently
- Run comparator-first deterministic classification
- Aggregate per-test results into a BehaviorReport
"""

from __future__ import annotations

import asyncio
import random
import re
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence, Tuple

import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from .adapters.anthropic_adapter import AnthropicAdapter
from .adapters.base import ModelAdapter
from .adapters.litellm_adapter import LiteLLMAdapter
from .adapters.local_adapter import LocalAdapter
from .adapters.openai_adapter import OpenAIAdapter
from .aggregator import (
    aggregate_comparator_results,
    summarize_comparator_breakdown,
)
from .aggregator import (
    infer_behavior_category as aggregate_infer_behavior_category,
)
from .comparators.base import (
    ComparatorResult,
)
from .comparators.base import (
    score_expected_behavior_coverage as comparator_behavior_coverage,
)
from .comparators.behavioral import BehavioralComparator
from .comparators.factual import FactualComparator
from .comparators.factual_external import ExternalFactualComparator
from .comparators.format import FormatComparator
from .comparators.judge import JudgeComparator
from .comparators.semantic import SemanticComparator
from .connectors.base import FactualConnector
from .connectors.wikipedia import WikipediaConnector
from .schema import BehaviorCategory, BehaviorReport, DiffResult, TestCase, TestSuite
from .statistics import (
    DEFAULT_BOOTSTRAP_RESAMPLES,
    DEFAULT_BOOTSTRAP_SEED,
    DEFAULT_CONFIDENCE_LEVEL,
    bootstrap_rate_interval,
    wilson_rate_interval,
)

_RETRYABLE_STATUS_PATTERN = re.compile(r"\b(429|5\d\d)\b")
_EXPLICIT_PROVIDER_PREFIXES = {"litellm", "local", "openai", "anthropic"}
_RETRYABLE_ERROR_HINTS = (
    "rate limit",
    "timeout",
    "temporarily unavailable",
    "connection reset",
    "connection aborted",
    "service unavailable",
    "bad gateway",
    "gateway timeout",
    "too many requests",
    "try again",
)
_BUILTIN_MODEL_PRICING_USD_PER_1M: dict[str, dict[str, float]] = {
    "gpt-4o": {"input_per_1m": 5.0, "output_per_1m": 15.0},
    "gpt-4.5": {"input_per_1m": 75.0, "output_per_1m": 150.0},
    "gpt-4-turbo": {"input_per_1m": 10.0, "output_per_1m": 30.0},
    "gpt-4": {"input_per_1m": 30.0, "output_per_1m": 60.0},
    "gpt-3.5-turbo": {"input_per_1m": 0.5, "output_per_1m": 1.5},
    "claude-3-opus": {"input_per_1m": 15.0, "output_per_1m": 75.0},
    "claude-3-sonnet": {"input_per_1m": 3.0, "output_per_1m": 15.0},
    "claude-3-haiku": {"input_per_1m": 0.25, "output_per_1m": 1.25},
    "o1": {"input_per_1m": 15.0, "output_per_1m": 60.0},
    "o3": {"input_per_1m": 10.0, "output_per_1m": 40.0},
}
_SUPPORTED_FACTUAL_CONNECTORS = {"none", "wikipedia"}


@dataclass(frozen=True)
class PriceSpec:
    """Price specification for a model in USD per 1M tokens."""

    input_per_1m: float
    output_per_1m: float
    source: str


@dataclass
class TestExecutionError(Exception):
    """Error wrapper that carries test/model context and retry details."""

    test_id: str
    model: str
    attempts: int
    retryable: bool
    original_error: Exception

    def __str__(self) -> str:
        return (
            f"Test '{self.test_id}' failed for model '{self.model}' after "
            f"{self.attempts} attempt(s): {self.original_error}"
        )

    def to_metadata(self) -> dict[str, Any]:
        """Serialize exception details for report metadata."""
        return {
            "test_id": self.test_id,
            "model": self.model,
            "attempts": self.attempts,
            "retryable": self.retryable,
            "error": str(self.original_error),
        }


class AsyncRateLimiter:
    """Simple per-adapter async rate limiter using minimum request intervals."""

    def __init__(self, rate_limit_rps: float = 0.0):
        self.rate_limit_rps = max(0.0, rate_limit_rps)
        self.min_interval = 0.0 if self.rate_limit_rps == 0 else 1.0 / self.rate_limit_rps
        self._next_allowed = 0.0
        self._lock = asyncio.Lock()

    async def wait_turn(self) -> None:
        """Wait until the next request slot is available."""
        if self.min_interval <= 0:
            return

        async with self._lock:
            now = time.monotonic()
            sleep_for = self._next_allowed - now
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)
                now = time.monotonic()
            self._next_allowed = max(self._next_allowed, now) + self.min_interval


def load_test_suite(path: str | Path) -> TestSuite:
    """Load and validate a single YAML test suite file."""
    suite_path = Path(path)
    try:
        raw_text = suite_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Unable to read suite file '{suite_path}': {exc}") from exc

    try:
        payload = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in suite file '{suite_path}': {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"Suite file '{suite_path}' must contain a YAML object at the top level.")

    try:
        return TestSuite.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"Suite validation failed for '{suite_path}': {exc}") from exc


def resolve_provider(model: str) -> str:
    """Resolve provider name from model identifier."""
    explicit_provider, normalized_model = parse_model_reference(model)
    if explicit_provider is not None:
        return explicit_provider

    normalized = normalized_model.lower()
    if normalized.startswith(("gpt-", "o1-", "o3-")):
        return "openai"
    if normalized.startswith("claude-"):
        return "anthropic"
    raise ValueError(
        f"Unsupported model '{model}'. Supported formats include gpt-*, o1-*, o3-*, "
        "claude-*, litellm:<model_ref>, local:<model_ref>. "
        "Examples: gpt-4o, claude-3-5-sonnet, litellm:openai/gpt-4o-mini, local:llama3.1"
    )


def create_adapter(model: str) -> ModelAdapter:
    """Create provider-specific adapter from a model identifier."""
    explicit_provider, model_ref = parse_model_reference(model)
    provider = explicit_provider or resolve_provider(model_ref)

    if provider == "openai":
        return OpenAIAdapter(model=model_ref)
    if provider == "anthropic":
        return AnthropicAdapter(model=model_ref)
    if provider == "litellm":
        return LiteLLMAdapter(model=model_ref)
    if provider == "local":
        return LocalAdapter(model=model_ref)
    raise ValueError(f"Unsupported provider '{provider}' for model '{model}'")


def create_factual_connector(connector_name: str) -> FactualConnector | None:
    """Create optional external factual connector from CLI/workflow value."""
    normalized = connector_name.strip().lower()
    if normalized not in _SUPPORTED_FACTUAL_CONNECTORS:
        supported = ", ".join(sorted(_SUPPORTED_FACTUAL_CONNECTORS))
        raise ValueError(
            f"Unsupported factual connector '{connector_name}'. Supported values: {supported}."
        )

    if normalized == "none":
        return None
    if normalized == "wikipedia":
        return WikipediaConnector()
    return None


def parse_model_reference(model: str) -> tuple[str | None, str]:
    """
    Parse ``provider:model_ref`` format and return (provider, model_ref).

    Returns (None, original_model) when the model id is not explicitly prefixed.
    """
    raw = model.strip()
    if not raw:
        raise ValueError("Model identifier cannot be empty.")

    if ":" not in raw:
        return None, raw

    provider_candidate, model_ref = raw.split(":", 1)
    provider = provider_candidate.strip().lower()
    if provider not in _EXPLICIT_PROVIDER_PREFIXES:
        return None, raw

    normalized_model_ref = model_ref.strip()
    if not normalized_model_ref:
        raise ValueError(
            f"Invalid model identifier '{model}'. Expected format '<provider>:<model_ref>'."
        )
    return provider, normalized_model_ref


def load_pricing_overrides(path: str | Path) -> dict[str, dict[str, float]]:
    """Load user-provided pricing override file (YAML or JSON)."""
    pricing_path = Path(path)
    try:
        payload = yaml.safe_load(pricing_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Unable to read pricing file '{pricing_path}': {exc}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid pricing file '{pricing_path}': {exc}") from exc

    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError(f"Pricing file '{pricing_path}' must contain a top-level mapping.")

    normalized: dict[str, dict[str, float]] = {}
    for model_key, value in payload.items():
        if not isinstance(model_key, str):
            raise ValueError("Pricing file model keys must be strings.")
        if not isinstance(value, dict):
            raise ValueError(
                f"Pricing for model '{model_key}' must be an object with input_per_1m and output_per_1m."
            )

        input_price = value.get("input_per_1m")
        output_price = value.get("output_per_1m")
        if not isinstance(input_price, (int, float)) or not isinstance(output_price, (int, float)):
            raise ValueError(
                f"Pricing for model '{model_key}' must include numeric input_per_1m/output_per_1m."
            )
        if input_price < 0 or output_price < 0:
            raise ValueError(f"Pricing for model '{model_key}' cannot be negative.")

        normalized[model_key.lower()] = {
            "input_per_1m": float(input_price),
            "output_per_1m": float(output_price),
        }

    return normalized


def is_retryable_error(exc: Exception) -> bool:
    """Return True when an exception likely represents a transient upstream failure."""
    if isinstance(exc, (TimeoutError, ConnectionError, asyncio.TimeoutError)):
        return True

    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int) and (status_code == 429 or 500 <= status_code <= 599):
        return True

    lower_error = str(exc).lower()
    if _RETRYABLE_STATUS_PATTERN.search(lower_error):
        return True
    return any(hint in lower_error for hint in _RETRYABLE_ERROR_HINTS)


def compute_backoff_seconds(
    retry_index: int, base_delay: float = 0.5, jitter_seconds: float = 0.1
) -> float:
    """Compute exponential backoff delay with optional jitter."""
    delay = base_delay * (2**retry_index)
    jitter = float(random.uniform(0.0, max(0.0, jitter_seconds)))
    return float(delay + jitter)


def score_expected_behavior_coverage(expected_behavior: str, response: str) -> float:
    """
    Score how much expected behavior text is covered by a model response.

    The score is the fraction of expected-behavior tokens that appear in the response.
    """
    return float(comparator_behavior_coverage(expected_behavior, response))


def infer_behavior_category(test_category: str) -> BehaviorCategory:
    """Map a suite test category to a v1 behavior-diff category."""
    return aggregate_infer_behavior_category(test_category)


def _normalize_usage(metadata: dict[str, Any]) -> dict[str, int]:
    """Extract input/output/total token usage fields from adapter metadata."""
    input_tokens = int(metadata.get("input_tokens", 0) or 0)
    output_tokens = int(metadata.get("output_tokens", 0) or 0)
    tokens_used = int(metadata.get("tokens_used", 0) or 0)

    if tokens_used <= 0:
        tokens_used = input_tokens + output_tokens
    if input_tokens == 0 and output_tokens == 0 and tokens_used > 0:
        output_tokens = tokens_used

    return {
        "input_tokens": max(0, input_tokens),
        "output_tokens": max(0, output_tokens),
        "tokens_used": max(0, tokens_used),
    }


def _empty_usage() -> dict[str, int]:
    """Create an empty token usage record."""
    return {"input_tokens": 0, "output_tokens": 0, "tokens_used": 0}


def _resolve_price_for_model(model: str, catalog: dict[str, PriceSpec]) -> PriceSpec | None:
    """Resolve price spec by exact model key or longest matching prefix."""
    normalized = model.lower()
    if normalized in catalog:
        return catalog[normalized]

    matches = [key for key in catalog if normalized.startswith(key)]
    if not matches:
        return None
    best_key = max(matches, key=len)
    return catalog[best_key]


def _pricing_source_label(used_sources: set[str]) -> str:
    """Convert per-model source set into report-level source label."""
    if not used_sources:
        return "none"
    if used_sources == {"builtin"}:
        return "builtin"
    if used_sources == {"file"}:
        return "file"
    return "builtin+file"


def compute_estimated_cost_usd(
    token_usage: dict[str, dict[str, int]], pricing_catalog: dict[str, PriceSpec]
) -> tuple[dict[str, float], str, list[str]]:
    """Compute estimated USD cost per model and total."""
    estimated: dict[str, float] = {}
    total_cost = 0.0
    used_sources: set[str] = set()
    unpriced_models: list[str] = []

    for model, usage in token_usage.items():
        if model == "total":
            continue

        price = _resolve_price_for_model(model, pricing_catalog)
        if price is None:
            estimated[model] = 0.0
            unpriced_models.append(model)
            continue

        input_cost = (usage["input_tokens"] / 1_000_000) * price.input_per_1m
        output_cost = (usage["output_tokens"] / 1_000_000) * price.output_per_1m
        model_cost = input_cost + output_cost
        estimated[model] = round(model_cost, 8)
        total_cost += model_cost
        used_sources.add(price.source)

    estimated["total"] = round(total_cost, 8)
    return estimated, _pricing_source_label(used_sources), unpriced_models


def _build_pricing_catalog(pricing_file: str | Path | None) -> dict[str, PriceSpec]:
    """Build pricing catalog by layering optional file overrides over built-in values."""
    catalog: dict[str, PriceSpec] = {
        model: PriceSpec(
            input_per_1m=values["input_per_1m"],
            output_per_1m=values["output_per_1m"],
            source="builtin",
        )
        for model, values in _BUILTIN_MODEL_PRICING_USD_PER_1M.items()
    }

    if not pricing_file:
        return catalog

    overrides = load_pricing_overrides(pricing_file)
    for model, values in overrides.items():
        catalog[model] = PriceSpec(
            input_per_1m=values["input_per_1m"],
            output_per_1m=values["output_per_1m"],
            source="file",
        )
    return catalog


def build_behavior_report(
    model_a: str,
    model_b: str,
    suite_name: str,
    total_tests: int,
    diff_results: Iterable[DiffResult],
    duration_seconds: float,
) -> BehaviorReport:
    """Aggregate per-test diff results into a BehaviorReport."""
    results = list(diff_results)

    regressions = sum(1 for result in results if result.is_regression)
    improvements = sum(1 for result in results if result.is_improvement)
    semantic_only_diffs = sum(
        1
        for result in results
        if result.is_semantically_same and result.response_a.strip() != result.response_b.strip()
    )
    unknown_diffs = sum(
        1
        for result in results
        if not result.is_semantically_same
        and not result.is_regression
        and not result.is_improvement
    )
    total_diffs = regressions + improvements + semantic_only_diffs + unknown_diffs

    regression_by_category = Counter(
        result.behavior_category for result in results if result.is_regression
    )
    improvement_by_category = Counter(
        result.behavior_category for result in results if result.is_improvement
    )

    return BehaviorReport(
        model_a=model_a,
        model_b=model_b,
        suite_name=suite_name,
        total_tests=total_tests,
        total_diffs=total_diffs,
        regressions=regressions,
        improvements=improvements,
        semantic_only_diffs=semantic_only_diffs,
        diff_results=results,
        regression_by_category=dict(regression_by_category),
        improvement_by_category=dict(improvement_by_category),
        duration_seconds=duration_seconds,
        metadata={"unknown_diffs": unknown_diffs},
    )


class BehaviorDiffRunner:
    """Execute a suite against two models and build an aggregated report."""

    def __init__(
        self,
        model_a: str,
        model_b: str,
        judge_model: str | None = None,
        factual_connector: str = "none",
        factual_connector_timeout: float = 8.0,
        factual_connector_max_results: int = 3,
        max_workers: int = 4,
        semantic_threshold: float = 0.85,
        continue_on_error: bool = False,
        max_retries: int = 3,
        rate_limit_rps: float = 0.0,
        pricing_file: str | Path | None = None,
        retry_base_delay_seconds: float = 0.5,
        retry_jitter_seconds: float = 0.1,
        adapter_a: ModelAdapter | None = None,
        adapter_b: ModelAdapter | None = None,
        semantic_comparator: SemanticComparator | None = None,
        behavioral_comparator: BehavioralComparator | None = None,
        factual_comparator: FactualComparator | None = None,
        format_comparator: FormatComparator | None = None,
        external_factual_comparator: ExternalFactualComparator | None = None,
        judge_adapter: ModelAdapter | None = None,
        judge_comparator: JudgeComparator | None = None,
    ) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be >= 1")
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if rate_limit_rps < 0:
            raise ValueError("rate_limit_rps must be >= 0")
        if factual_connector_timeout <= 0:
            raise ValueError("factual_connector_timeout must be > 0")
        if factual_connector_max_results < 1:
            raise ValueError("factual_connector_max_results must be >= 1")

        self.model_a = model_a
        self.model_b = model_b
        self.judge_model = judge_model
        judge_model_ref = self.judge_model
        self.factual_connector_name = factual_connector.strip().lower()
        self.factual_connector_timeout = factual_connector_timeout
        self.factual_connector_max_results = factual_connector_max_results
        self.max_workers = max_workers
        self.continue_on_error = continue_on_error
        self.max_retries = max_retries
        self.rate_limit_rps = rate_limit_rps
        self.retry_base_delay_seconds = retry_base_delay_seconds
        self.retry_jitter_seconds = retry_jitter_seconds
        self.adapter_a = adapter_a or create_adapter(model_a)
        self.adapter_b = adapter_b or create_adapter(model_b)
        self.semantic_comparator = semantic_comparator or SemanticComparator(
            threshold=semantic_threshold
        )
        raw_threshold = getattr(self.semantic_comparator, "threshold", semantic_threshold)
        try:
            self.semantic_threshold = float(raw_threshold)
        except (TypeError, ValueError):
            self.semantic_threshold = float(semantic_threshold)
        self.behavioral_comparator = behavioral_comparator or BehavioralComparator()
        self.factual_comparator = factual_comparator or FactualComparator()
        connector = create_factual_connector(self.factual_connector_name)
        self.external_factual_enabled = connector is not None
        self.external_factual_comparator = external_factual_comparator
        if self.external_factual_enabled and self.external_factual_comparator is None:
            assert connector is not None
            self.external_factual_comparator = ExternalFactualComparator(
                connector=connector,
                max_results=self.factual_connector_max_results,
                timeout_seconds=self.factual_connector_timeout,
            )
        self.format_comparator = format_comparator or FormatComparator()
        self.rate_limiter_a = AsyncRateLimiter(rate_limit_rps=self.rate_limit_rps)
        self.rate_limiter_b = AsyncRateLimiter(rate_limit_rps=self.rate_limit_rps)
        self.judge_enabled = judge_model_ref is not None
        self.judge_adapter: ModelAdapter | None
        if judge_model_ref is not None:
            self.judge_adapter = (
                judge_adapter if judge_adapter is not None else create_adapter(judge_model_ref)
            )
        else:
            self.judge_adapter = None
        self.judge_comparator = judge_comparator or JudgeComparator()
        self.judge_rate_limiter = (
            AsyncRateLimiter(rate_limit_rps=self.rate_limit_rps) if self.judge_enabled else None
        )
        self.pricing_catalog = _build_pricing_catalog(pricing_file)

    async def run_suite(self, suite: TestSuite) -> BehaviorReport:
        """Run all test cases in a suite with bounded concurrency and fail-fast behavior."""
        started_at = time.perf_counter()
        semaphore = asyncio.Semaphore(self.max_workers)

        tasks = [
            asyncio.create_task(self._run_test_case(test_case, semaphore))
            for test_case in suite.test_cases
        ]

        diff_results: list[DiffResult] = []
        errors: list[dict[str, Any]] = []
        try:
            for completed in asyncio.as_completed(tasks):
                try:
                    diff_results.append(await completed)
                except TestExecutionError as exc:
                    errors.append(exc.to_metadata())
                    if not self.continue_on_error:
                        raise RuntimeError(str(exc)) from exc
                except Exception as exc:
                    errors.append(
                        {
                            "test_id": "unknown",
                            "model": "unknown",
                            "attempts": 0,
                            "retryable": False,
                            "error": str(exc),
                        }
                    )
                    if not self.continue_on_error:
                        raise RuntimeError(f"Unexpected runner error: {exc}") from exc
        except Exception:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

        # Keep report output deterministic by suite order.
        order_index = {test_case.id: index for index, test_case in enumerate(suite.test_cases)}
        diff_results.sort(key=lambda result: order_index.get(result.test_id, 0))

        duration = time.perf_counter() - started_at
        report = build_behavior_report(
            model_a=self.model_a,
            model_b=self.model_b,
            suite_name=suite.name,
            total_tests=len(suite),
            diff_results=diff_results,
            duration_seconds=duration,
        )

        token_usage = self._aggregate_token_usage(diff_results)
        estimated_cost_usd, pricing_source, unpriced_models = compute_estimated_cost_usd(
            token_usage, self.pricing_catalog
        )
        significance = self._build_significance_metadata(diff_results)

        report.metadata.update(
            {
                "processed_tests": len(diff_results),
                "failed_tests": len(errors),
                "errors": errors,
                "token_usage": token_usage,
                "estimated_cost_usd": estimated_cost_usd,
                "pricing_source": pricing_source,
                "judge_enabled": self.judge_enabled,
                "judge_model": self.judge_model,
                "factual_connector": self.factual_connector_name,
                "factual_external_summary": self._build_factual_external_summary(diff_results),
                "significance": significance,
                "comparator_summary": summarize_comparator_breakdown(report.diff_results),
            }
        )
        if unpriced_models:
            report.metadata["unpriced_models"] = sorted(unpriced_models)

        return report

    async def _run_test_case(self, test_case: TestCase, semaphore: asyncio.Semaphore) -> DiffResult:
        """Run one test case against both models and classify the behavioral diff."""
        async with semaphore:
            (response_a, metadata_a), (response_b, metadata_b) = await asyncio.gather(
                self._generate_with_retries(
                    adapter=self.adapter_a,
                    rate_limiter=self.rate_limiter_a,
                    model=self.model_a,
                    test_case=test_case,
                ),
                self._generate_with_retries(
                    adapter=self.adapter_b,
                    rate_limiter=self.rate_limiter_b,
                    model=self.model_b,
                    test_case=test_case,
                ),
            )

        similarity, is_semantically_same = self.semantic_comparator.compare(response_a, response_b)
        behavioral_result = self.behavioral_comparator.compare(
            test_case=test_case,
            response_a=response_a,
            response_b=response_b,
        )
        factual_result = self.factual_comparator.compare(
            test_case=test_case,
            response_a=response_a,
            response_b=response_b,
        )
        format_result = self.format_comparator.compare(
            test_case=test_case,
            response_a=response_a,
            response_b=response_b,
        )
        aggregation = aggregate_comparator_results(
            test_case=test_case,
            semantic_similarity=similarity,
            semantic_threshold=self.semantic_threshold,
            is_semantically_same=is_semantically_same,
            behavioral=behavioral_result,
            factual=factual_result,
            format_check=format_result,
        )
        diff_metadata: dict[str, Any] = {
            "model_a": metadata_a,
            "model_b": metadata_b,
            "comparators": aggregation["comparators"],
        }
        if self.external_factual_enabled and self.external_factual_comparator is not None:
            external_result, external_metadata = await self.external_factual_comparator.compare(
                test_case=test_case,
                response_a=response_a,
                response_b=response_b,
                is_semantically_same=is_semantically_same,
            )
            diff_metadata["comparators"]["factual_external"] = external_result.to_dict()
            diff_metadata["factual_external"] = external_metadata

        if self.judge_enabled and not is_semantically_same:
            judge_result, judge_metadata = await self._run_judge_for_test_case(
                test_case=test_case,
                response_a=response_a,
                response_b=response_b,
            )
            diff_metadata["comparators"]["judge"] = judge_result.to_dict()
            diff_metadata["judge"] = judge_metadata

        return DiffResult(
            test_id=test_case.id,
            model_a=self.model_a,
            model_b=self.model_b,
            response_a=response_a,
            response_b=response_b,
            is_semantically_same=is_semantically_same,
            semantic_similarity=similarity,
            behavior_category=aggregation["behavior_category"],
            is_regression=aggregation["is_regression"],
            is_improvement=aggregation["is_improvement"],
            confidence=aggregation["confidence"],
            explanation=aggregation["explanation"],
            metadata=diff_metadata,
        )

    async def _run_judge_for_test_case(
        self,
        test_case: TestCase,
        response_a: str,
        response_b: str,
    ) -> tuple[ComparatorResult, dict[str, Any]]:
        """Run optional judge comparator for semantic-diff tests only."""
        if not self.judge_enabled or self.judge_adapter is None or self.judge_rate_limiter is None:
            return self.judge_comparator.uncertain_result("Judge is disabled."), _empty_usage()

        judge_prompt = self.judge_comparator.build_prompt(test_case, response_a, response_b)
        try:
            judge_output, judge_metadata = await self._generate_prompt_with_retries(
                adapter=self.judge_adapter,
                rate_limiter=self.judge_rate_limiter,
                model=self.judge_model or "judge",
                prompt=judge_prompt,
                max_tokens=self.judge_comparator.max_tokens,
                temperature=self.judge_comparator.temperature,
                test_id=test_case.id,
            )
            judge_result = self.judge_comparator.compare_from_output(judge_output)
            return judge_result, judge_metadata
        except TestExecutionError as exc:
            result = self.judge_comparator.error_result(str(exc))
            metadata: dict[str, Any] = _empty_usage()
            metadata.update({"retry_attempts": exc.attempts, "error": str(exc)})
            return result, metadata
        except Exception as exc:
            result = self.judge_comparator.error_result(f"Judge error: {exc}")
            error_metadata: dict[str, Any] = _empty_usage()
            error_metadata.update({"retry_attempts": 0, "error": str(exc)})
            return result, error_metadata

    async def _generate_with_retries(
        self,
        adapter: ModelAdapter,
        rate_limiter: AsyncRateLimiter,
        model: str,
        test_case: TestCase,
    ) -> Tuple[str, dict[str, Any]]:
        """Generate a response with retry and rate-limit controls."""
        return await self._generate_prompt_with_retries(
            adapter=adapter,
            rate_limiter=rate_limiter,
            model=model,
            prompt=test_case.prompt,
            max_tokens=test_case.max_tokens,
            temperature=test_case.temperature,
            test_id=test_case.id,
        )

    async def _generate_prompt_with_retries(
        self,
        *,
        adapter: ModelAdapter,
        rate_limiter: AsyncRateLimiter,
        model: str,
        prompt: str,
        max_tokens: int,
        temperature: float,
        test_id: str,
    ) -> Tuple[str, dict[str, Any]]:
        """Generate a response for any prompt with retry and rate-limit controls."""
        attempts = 0

        while True:
            await rate_limiter.wait_turn()
            try:
                response_text, metadata = await adapter.generate(
                    prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                normalized_metadata = dict(metadata or {})
                normalized_metadata.update(_normalize_usage(normalized_metadata))
                normalized_metadata["retry_attempts"] = attempts
                return response_text, normalized_metadata
            except Exception as exc:
                retryable = is_retryable_error(exc)
                if attempts >= self.max_retries or not retryable:
                    raise TestExecutionError(
                        test_id=test_id,
                        model=model,
                        attempts=attempts + 1,
                        retryable=retryable,
                        original_error=exc,
                    ) from exc

                backoff_seconds = compute_backoff_seconds(
                    retry_index=attempts,
                    base_delay=self.retry_base_delay_seconds,
                    jitter_seconds=self.retry_jitter_seconds,
                )
                await asyncio.sleep(backoff_seconds)
                attempts += 1

    def _aggregate_token_usage(
        self, diff_results: Iterable[DiffResult]
    ) -> dict[str, dict[str, int]]:
        """Aggregate token usage from model metadata in diff results."""
        model_names = [self.model_a, self.model_b]
        if self.judge_enabled and self.judge_model:
            model_names.append(self.judge_model)

        usage: dict[str, dict[str, int]] = {"total": _empty_usage()}
        for model_name in model_names:
            usage.setdefault(model_name, _empty_usage())

        model_map = {"model_a": self.model_a, "model_b": self.model_b}
        if self.judge_enabled and self.judge_model:
            model_map["judge"] = self.judge_model

        for result in diff_results:
            for metadata_key, model_name in model_map.items():
                raw_metadata = result.metadata.get(metadata_key, {})
                if not isinstance(raw_metadata, dict):
                    continue

                model_usage = _normalize_usage(raw_metadata)
                usage[model_name]["input_tokens"] += model_usage["input_tokens"]
                usage[model_name]["output_tokens"] += model_usage["output_tokens"]
                usage[model_name]["tokens_used"] += model_usage["tokens_used"]
                usage["total"]["input_tokens"] += model_usage["input_tokens"]
                usage["total"]["output_tokens"] += model_usage["output_tokens"]
                usage["total"]["tokens_used"] += model_usage["tokens_used"]

        return usage

    def _build_factual_external_summary(self, diff_results: Sequence[DiffResult]) -> dict[str, Any]:
        """Summarize optional external factual comparator decisions across a run."""
        if not self.external_factual_enabled:
            return {
                "enabled": False,
                "connector": "none",
                "decision_counts": {},
                "applied_tests": 0,
            }

        decisions: Counter[str] = Counter()
        applied_tests = 0
        for result in diff_results:
            comparators = result.metadata.get("comparators", {})
            if not isinstance(comparators, dict):
                continue
            payload = comparators.get("factual_external")
            if not isinstance(payload, dict):
                continue
            decision = str(payload.get("decision", "unknown"))
            decisions[decision] += 1
            if bool(payload.get("applies")):
                applied_tests += 1

        return {
            "enabled": True,
            "connector": self.factual_connector_name,
            "decision_counts": dict(decisions),
            "applied_tests": applied_tests,
        }

    def _build_significance_metadata(self, diff_results: Sequence[DiffResult]) -> dict[str, Any]:
        """Build run-level significance metadata from regression/improvement outcomes."""
        regressions = [result.is_regression for result in diff_results]
        improvements = [result.is_improvement for result in diff_results]

        return {
            "method": "bootstrap",
            "confidence_level": DEFAULT_CONFIDENCE_LEVEL,
            "resamples": DEFAULT_BOOTSTRAP_RESAMPLES,
            "seed": DEFAULT_BOOTSTRAP_SEED,
            "sample_size": len(diff_results),
            "rate_interval_methods": ["bootstrap", "wilson"],
            "regression_rate": bootstrap_rate_interval(
                regressions,
                resamples=DEFAULT_BOOTSTRAP_RESAMPLES,
                confidence_level=DEFAULT_CONFIDENCE_LEVEL,
                seed=DEFAULT_BOOTSTRAP_SEED,
            ),
            "improvement_rate": bootstrap_rate_interval(
                improvements,
                resamples=DEFAULT_BOOTSTRAP_RESAMPLES,
                confidence_level=DEFAULT_CONFIDENCE_LEVEL,
                seed=DEFAULT_BOOTSTRAP_SEED,
            ),
            "regression_rate_wilson": wilson_rate_interval(
                regressions,
                confidence_level=DEFAULT_CONFIDENCE_LEVEL,
            ),
            "improvement_rate_wilson": wilson_rate_interval(
                improvements,
                confidence_level=DEFAULT_CONFIDENCE_LEVEL,
            ),
        }


__all__ = [
    "AsyncRateLimiter",
    "BehaviorDiffRunner",
    "compute_backoff_seconds",
    "compute_estimated_cost_usd",
    "build_behavior_report",
    "create_adapter",
    "create_factual_connector",
    "infer_behavior_category",
    "is_retryable_error",
    "load_test_suite",
    "load_pricing_overrides",
    "parse_model_reference",
    "resolve_provider",
    "score_expected_behavior_coverage",
]
