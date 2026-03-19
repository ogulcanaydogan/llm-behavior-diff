"""Tests for schema definitions."""


from llm_behavior_diff.schema import (
    BehaviorCategory,
    BehaviorReport,
    DiffResult,
    ModelResponse,
)
from llm_behavior_diff.schema import (
    TestCase as SchemaTestCase,
)
from llm_behavior_diff.schema import (
    TestSuite as SchemaTestSuite,
)


class TestTestCase:
    """Test TestCase schema."""

    def test_test_case_creation(self):
        """Test creating a TestCase."""
        tc = SchemaTestCase(
            id="test_001",
            prompt="What is 2+2?",
            category="math",
            expected_behavior="Should respond with 4",
        )
        assert tc.id == "test_001"
        assert tc.prompt == "What is 2+2?"
        assert tc.category == "math"

    def test_test_case_with_tags(self):
        """Test TestCase with tags."""
        tc = SchemaTestCase(
            id="test_002",
            prompt="Hello",
            category="greeting",
            expected_behavior="Friendly response",
            tags=["casual", "english"],
        )
        assert len(tc.tags) == 2
        assert "casual" in tc.tags


class TestTestSuite:
    """Test TestSuite schema."""

    def test_suite_creation(self):
        """Test creating a TestSuite."""
        suite = SchemaTestSuite(
            name="math_basics",
            description="Basic arithmetic tests",
            test_cases=[
                SchemaTestCase(
                    id="q1",
                    prompt="2+2=?",
                    category="arithmetic",
                    expected_behavior="4",
                )
            ],
        )
        assert suite.name == "math_basics"
        assert len(suite) == 1

    def test_suite_length(self):
        """Test suite length method."""
        suite = SchemaTestSuite(
            name="test",
            description="Test suite",
            test_cases=[
                SchemaTestCase(
                    id=f"test_{i}",
                    prompt=f"Prompt {i}",
                    category="test",
                    expected_behavior=f"Response {i}",
                )
                for i in range(5)
            ],
        )
        assert len(suite) == 5


class TestModelResponse:
    """Test ModelResponse schema."""

    def test_response_creation(self):
        """Test creating a ModelResponse."""
        response = ModelResponse(
            test_id="test_001",
            model="gpt-4o",
            response="This is the response.",
        )
        assert response.test_id == "test_001"
        assert response.model == "gpt-4o"
        assert response.timestamp is not None

    def test_response_with_metrics(self):
        """Test response with performance metrics."""
        response = ModelResponse(
            test_id="test_001",
            model="claude-3-opus",
            response="Response text",
            tokens_used=150,
            latency_ms=234.5,
        )
        assert response.tokens_used == 150
        assert response.latency_ms == 234.5


class TestDiffResult:
    """Test DiffResult schema."""

    def test_diff_result_creation(self):
        """Test creating a DiffResult."""
        diff = DiffResult(
            test_id="test_001",
            model_a="gpt-4o",
            model_b="gpt-4.5",
            response_a="Response A",
            response_b="Response B",
            is_semantically_same=True,
            semantic_similarity=0.92,
        )
        assert diff.test_id == "test_001"
        assert diff.model_a == "gpt-4o"
        assert diff.semantic_similarity == 0.92

    def test_diff_result_regression(self):
        """Test DiffResult with regression flag."""
        diff = DiffResult(
            test_id="test_001",
            model_a="gpt-4o",
            model_b="gpt-4.5",
            response_a="Correct response",
            response_b="Incorrect response",
            is_semantically_same=False,
            is_regression=True,
            behavior_category=BehaviorCategory.KNOWLEDGE_CHANGE,
            confidence=0.95,
            explanation="Model lost knowledge about topic X",
        )
        assert diff.is_regression is True
        assert diff.behavior_category == BehaviorCategory.KNOWLEDGE_CHANGE
        assert diff.confidence == 0.95


class TestBehaviorReport:
    """Test BehaviorReport schema."""

    def test_report_creation(self):
        """Test creating a BehaviorReport."""
        report = BehaviorReport(
            model_a="gpt-4o",
            model_b="gpt-4.5",
            suite_name="general_knowledge",
            total_tests=50,
            regressions=2,
            improvements=4,
        )
        assert report.model_a == "gpt-4o"
        assert report.total_tests == 50
        assert report.regressions == 2

    def test_report_regression_rate(self):
        """Test regression rate calculation."""
        report = BehaviorReport(
            model_a="model_a",
            model_b="model_b",
            suite_name="test_suite",
            total_tests=100,
            regressions=5,
        )
        assert report.regression_rate() == 5.0

    def test_report_improvement_rate(self):
        """Test improvement rate calculation."""
        report = BehaviorReport(
            model_a="model_a",
            model_b="model_b",
            suite_name="test_suite",
            total_tests=100,
            improvements=10,
        )
        assert report.improvement_rate() == 10.0

    def test_report_zero_tests(self):
        """Test rates with zero tests."""
        report = BehaviorReport(
            model_a="model_a",
            model_b="model_b",
            suite_name="test_suite",
            total_tests=0,
            regressions=0,
        )
        assert report.regression_rate() == 0.0
        assert report.improvement_rate() == 0.0

    def test_report_top_categories(self):
        """Test top categories methods."""
        report = BehaviorReport(
            model_a="model_a",
            model_b="model_b",
            suite_name="test_suite",
            total_tests=50,
            regression_by_category={
                BehaviorCategory.KNOWLEDGE_CHANGE: 3,
                BehaviorCategory.REASONING_CHANGE: 1,
                BehaviorCategory.INSTRUCTION_FOLLOWING: 2,
            },
            improvement_by_category={
                BehaviorCategory.HALLUCINATION_FIXED: 4,
                BehaviorCategory.TONE_SHIFT: 2,
            },
        )

        top_regressions = report.top_regression_categories(2)
        assert len(top_regressions) == 2
        assert top_regressions[0][1] == 3  # KNOWLEDGE_CHANGE

        top_improvements = report.top_improvement_categories(2)
        assert len(top_improvements) == 2
        assert top_improvements[0][1] == 4  # HALLUCINATION_FIXED


class TestBehaviorCategory:
    """Test BehaviorCategory enum."""

    def test_category_values(self):
        """Test all category values."""
        assert BehaviorCategory.SEMANTIC.value == "semantic"
        assert BehaviorCategory.TONE_SHIFT.value == "tone_shift"
        assert BehaviorCategory.KNOWLEDGE_CHANGE.value == "knowledge_change"
        assert BehaviorCategory.SAFETY_BOUNDARY.value == "safety_boundary"
        assert BehaviorCategory.REASONING_CHANGE.value == "reasoning_change"
        assert BehaviorCategory.HALLUCINATION_NEW.value == "hallucination_new"
        assert BehaviorCategory.HALLUCINATION_FIXED.value == "hallucination_fixed"
