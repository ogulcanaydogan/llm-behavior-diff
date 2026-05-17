"""Guard tests for the v1.1.0 quantization-int8 example suite.

Ensures the documented example under examples/quantization-int8/ remains
loadable, semantically consistent with the int8 profile, and exercises the
comparator categories described in the README.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from llm_behavior_diff.comparators.factual import is_factual_applicable
from llm_behavior_diff.profiles.quantization import QuantizationProfile
from llm_behavior_diff.schema import TestSuite

_EXAMPLE_PATH = (
    Path(__file__).resolve().parents[1] / "examples" / "quantization-int8" / "suite.yaml"
)


def _load_suite() -> TestSuite:
    with _EXAMPLE_PATH.open() as f:
        data = yaml.safe_load(f)
    return TestSuite(**data)


def test_example_suite_loads_against_schema() -> None:
    suite = _load_suite()
    assert suite.name == "quantization_int8_example"
    assert len(suite.test_cases) >= 6


def test_example_suite_targets_int8_profile() -> None:
    with _EXAMPLE_PATH.open() as f:
        raw = yaml.safe_load(f)
    assert raw["metadata"]["intended_profile"] == "int8"
    profile = QuantizationProfile.for_format(raw["metadata"]["intended_profile"])
    assert profile.format == "int8"


def test_example_suite_has_factual_cases() -> None:
    suite = _load_suite()
    factual_cases = [tc for tc in suite.test_cases if is_factual_applicable(tc)]
    assert factual_cases, "example must include factual-applicable cases for int8 profile demo"


def test_example_suite_has_format_and_reasoning_cases() -> None:
    suite = _load_suite()
    categories = {tc.category for tc in suite.test_cases}
    assert "structured_output" in categories or "instruction_following" in categories
    assert "reasoning" in categories
