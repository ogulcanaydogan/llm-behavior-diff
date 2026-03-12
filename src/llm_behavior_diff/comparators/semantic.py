"""
Semantic similarity comparator for model responses.

Uses sentence embeddings to detect semantically equivalent but differently worded outputs.
"""

from typing import Optional, Tuple

import numpy as np


class SemanticComparator:
    """
    Compares semantic similarity between two text responses.

    Uses sentence transformers to compute embeddings and similarity scores.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", threshold: float = 0.85):
        """
        Initialize semantic comparator.

        Args:
            model_name: Sentence transformer model to use
            threshold: Similarity threshold for considering responses "same" (0-1)
        """
        self.model_name = model_name
        self.threshold = threshold
        self.model: Optional[object] = None

    def _load_model(self) -> None:
        """Lazy load sentence transformer model."""
        if self.model is None:
            try:
                from sentence_transformers import SentenceTransformer

                self.model = SentenceTransformer(self.model_name)
            except ImportError:
                raise ImportError(
                    "sentence-transformers required. Install with: pip install sentence-transformers"
                )

    def compare(self, text_a: str, text_b: str) -> Tuple[float, bool]:
        """
        Compare semantic similarity between two texts.

        Args:
            text_a: First text
            text_b: Second text

        Returns:
            Tuple of (similarity_score, are_semantically_same)
            Similarity score is 0-1, are_semantically_same is True if >= threshold
        """
        if not text_a or not text_b:
            return 0.0, text_a == text_b

        self._load_model()

        # Compute embeddings
        embeddings = self.model.encode([text_a, text_b])
        embedding_a = embeddings[0]
        embedding_b = embeddings[1]

        # Cosine similarity
        similarity = float(np.dot(embedding_a, embedding_b) /
                          (np.linalg.norm(embedding_a) * np.linalg.norm(embedding_b)))

        # Clamp to [0, 1]
        similarity = max(0.0, min(1.0, similarity))

        is_same = similarity >= self.threshold

        return similarity, is_same

    def set_threshold(self, threshold: float) -> None:
        """
        Update similarity threshold.

        Args:
            threshold: New threshold (0-1)
        """
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("Threshold must be between 0 and 1")
        self.threshold = threshold
