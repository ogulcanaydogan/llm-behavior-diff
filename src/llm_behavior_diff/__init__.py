"""
llm-behavior-diff: Behavioral regression testing for LLM model upgrades.

Compare two model versions on the same test suite and detect semantic,
behavioral, and factual differences. Essential for enterprise MLOps.
"""

__version__ = "0.1.0"
__author__ = "LLM Behavior Diff Contributors"

from .runner import BehaviorDiffRunner, load_test_suite
from .schema import (
    BehaviorCategory,
    BehaviorReport,
    DiffResult,
    ModelResponse,
    TestCase,
    TestSuite,
)

__all__ = [
    "TestCase",
    "TestSuite",
    "ModelResponse",
    "DiffResult",
    "BehaviorCategory",
    "BehaviorReport",
    "BehaviorDiffRunner",
    "load_test_suite",
]
