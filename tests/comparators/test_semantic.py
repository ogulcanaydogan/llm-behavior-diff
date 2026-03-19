"""Tests for semantic comparator."""

import numpy as np
import pytest

from llm_behavior_diff.comparators.semantic import SemanticComparator


class TestSemanticComparator:
    """Test semantic similarity comparator."""

    @pytest.fixture
    def comparator(self):
        """Create a SemanticComparator instance with an in-memory embedding model."""

        class DummyEmbeddingModel:
            def encode(self, texts):
                vectors = []
                for text in texts:
                    tokens = text.lower().split()
                    vectors.append(
                        np.array(
                            [
                                float(len(tokens)),
                                float(len(set(tokens))),
                                float(sum(ord(char) for char in text) % 997),
                                float(sum(char in "aeiou" for char in text.lower())),
                            ]
                        )
                    )
                return np.vstack(vectors)

        comp = SemanticComparator(threshold=0.8)
        comp.model = DummyEmbeddingModel()
        return comp

    def test_exact_match(self, comparator):
        """Test exact string match."""
        similarity, is_same = comparator.compare(
            "The sky is blue",
            "The sky is blue",
        )
        assert similarity == 1.0
        assert is_same is True

    def test_empty_strings(self, comparator):
        """Test with empty strings."""
        similarity, is_same = comparator.compare("", "")
        assert is_same is True

    def test_one_empty_string(self, comparator):
        """Test with one empty string."""
        similarity, is_same = comparator.compare("Hello", "")
        assert similarity == 0.0
        assert is_same is False

    def test_threshold_configuration(self):
        """Test threshold setter."""
        comparator = SemanticComparator(threshold=0.9)
        assert comparator.threshold == 0.9

    def test_threshold_bounds(self):
        """Test threshold bounds validation."""
        comparator = SemanticComparator()
        with pytest.raises(ValueError):
            comparator.set_threshold(-0.1)
        with pytest.raises(ValueError):
            comparator.set_threshold(1.1)

    def test_similarity_score_range(self, comparator):
        """Test that similarity scores are in [0, 1]."""
        text1 = "Hello world, this is a test."
        text2 = "Hi everyone, this is a demonstration."
        similarity, _ = comparator.compare(text1, text2)
        assert 0.0 <= similarity <= 1.0

    def test_symmetry(self, comparator):
        """Test that comparison is symmetric."""
        text1 = "The cat sat on the mat"
        text2 = "A cat was sitting on a mat"
        similarity1, _ = comparator.compare(text1, text2)
        similarity2, _ = comparator.compare(text2, text1)
        assert similarity1 == similarity2
