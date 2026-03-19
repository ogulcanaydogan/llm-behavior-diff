"""
Core schema definitions for behavioral regression testing.

Defines test cases, model responses, comparison results, and aggregated reports.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field


class BehaviorCategory(str, Enum):
    """Categories of behavioral differences between model versions."""

    SEMANTIC = "semantic"  # Different wording, same meaning
    TONE_SHIFT = "tone_shift"  # Change in tone/formality
    KNOWLEDGE_CHANGE = "knowledge_change"  # New or lost knowledge
    SAFETY_BOUNDARY = "safety_boundary"  # Changed refusal/safety behavior
    REASONING_CHANGE = "reasoning_change"  # Different reasoning patterns
    INSTRUCTION_FOLLOWING = "instruction_following"  # Changed compliance
    FORMAT_CHANGE = "format_change"  # Output structure changed
    HALLUCINATION_NEW = "hallucination_new"  # New factual errors
    HALLUCINATION_FIXED = "hallucination_fixed"  # Fixed factual errors
    UNKNOWN = "unknown"  # Undetermined difference


class TestCase(BaseModel):
    """Single test case in a behavior diff suite."""

    id: str = Field(..., description="Unique test case identifier")
    prompt: str = Field(..., description="Input prompt to send to model")
    category: str = Field(..., description="Test category (e.g., 'reasoning', 'safety')")
    tags: List[str] = Field(default_factory=list, description="Optional tags for filtering")
    expected_behavior: str = Field(
        ..., description="Description of expected behavior (not exact match)"
    )
    max_tokens: int = Field(default=2048, description="Max tokens for response")
    temperature: float = Field(default=0.7, description="Model temperature")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Custom metadata")

    model_config = ConfigDict(use_enum_values=False)


class TestSuite(BaseModel):
    """Collection of test cases for regression testing."""

    name: str = Field(..., description="Suite name (e.g., 'general_knowledge')")
    description: str = Field(..., description="Suite description")
    version: str = Field(default="1.0", description="Suite version")
    test_cases: List[TestCase] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.test_cases)


class ModelResponse(BaseModel):
    """Response from a model for a single test case."""

    test_id: str = Field(..., description="ID of corresponding test case")
    model: str = Field(..., description="Model name/version")
    response: str = Field(..., description="Raw model response")
    tokens_used: int = Field(default=0, description="Tokens consumed")
    latency_ms: float = Field(default=0.0, description="Response latency in milliseconds")
    stop_reason: str = Field(default="stop", description="Why model stopped")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DiffResult(BaseModel):
    """Comparison result for a single test case between two model versions."""

    test_id: str = Field(..., description="ID of the test case")
    model_a: str = Field(..., description="First model name/version")
    model_b: str = Field(..., description="Second model name/version")
    response_a: str = Field(..., description="Response from model A")
    response_b: str = Field(..., description="Response from model B")
    is_semantically_same: bool = Field(
        ..., description="Whether responses have same semantic meaning"
    )
    semantic_similarity: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Semantic similarity score (0-1)",
    )
    behavior_category: BehaviorCategory = Field(
        default=BehaviorCategory.UNKNOWN, description="Type of behavior change"
    )
    is_regression: bool = Field(
        default=False, description="Whether this is a behavioral regression"
    )
    is_improvement: bool = Field(
        default=False, description="Whether this is a behavioral improvement"
    )
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Confidence in the diff classification (0-1)",
    )
    explanation: str = Field(
        default="", description="Human-readable explanation of the difference"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BehaviorReport(BaseModel):
    """Aggregated behavioral regression report for a full test suite run."""

    id: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Report ID",
    )
    model_a: str = Field(..., description="First model version")
    model_b: str = Field(..., description="Second model version")
    suite_name: str = Field(..., description="Test suite name")
    total_tests: int = Field(..., description="Total test cases run")
    total_diffs: int = Field(
        default=0, description="Total differences detected (semantic or behavioral)"
    )
    regressions: int = Field(default=0, description="Count of regressions")
    improvements: int = Field(default=0, description="Count of improvements")
    semantic_only_diffs: int = Field(
        default=0, description="Differences that are semantic only (no behavior change)"
    )
    diff_results: List[DiffResult] = Field(
        default_factory=list, description="Individual diff results"
    )
    regression_by_category: Dict[BehaviorCategory, int] = Field(
        default_factory=dict, description="Regression counts by behavior category"
    )
    improvement_by_category: Dict[BehaviorCategory, int] = Field(
        default_factory=dict, description="Improvement counts by behavior category"
    )
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_seconds: float = Field(default=0.0, description="Total run duration")
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def regression_rate(self) -> float:
        """Calculate regression rate as percentage of total tests."""
        if self.total_tests == 0:
            return 0.0
        return (self.regressions / self.total_tests) * 100

    def improvement_rate(self) -> float:
        """Calculate improvement rate as percentage of total tests."""
        if self.total_tests == 0:
            return 0.0
        return (self.improvements / self.total_tests) * 100

    def top_regression_categories(self, limit: int = 5) -> List[tuple[BehaviorCategory, int]]:
        """Get top regression categories by count."""
        return sorted(
            self.regression_by_category.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:limit]

    def top_improvement_categories(self, limit: int = 5) -> List[tuple[BehaviorCategory, int]]:
        """Get top improvement categories by count."""
        return sorted(
            self.improvement_by_category.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:limit]
