"""Tests for the v1.1.0 quantization-diff profile."""

import pytest

from llm_behavior_diff.profiles import QuantizationProfile
from llm_behavior_diff.profiles.quantization import SUPPORTED_FORMATS


def test_int8_profile_thresholds():
    profile = QuantizationProfile.for_format("int8")
    assert profile.format == "int8"
    assert profile.semantic_threshold == 0.92
    assert profile.behavioral_regression_threshold == -0.10
    assert profile.factual_regression_threshold == -0.05
    assert profile.format_strict is False


def test_fp8_is_strictest_factual():
    profile = QuantizationProfile.for_format("fp8")
    assert profile.factual_regression_threshold == -0.03


def test_int4_is_loosest_semantic():
    profile = QuantizationProfile.for_format("int4")
    assert profile.semantic_threshold == 0.85
    assert profile.behavioral_regression_threshold == -0.15


def test_unknown_format_raises():
    with pytest.raises(ValueError, match="Unknown quantization format"):
        QuantizationProfile.for_format("bf16-extreme")


def test_supported_formats_listed():
    for fmt in SUPPORTED_FORMATS:
        profile = QuantizationProfile.for_format(fmt)
        assert profile.format == fmt


def test_format_case_insensitive():
    profile = QuantizationProfile.for_format("INT8")
    assert profile.format == "int8"


def test_weight_overrides_present():
    profile = QuantizationProfile.for_format("int8")
    assert "semantic" in profile.weight_overrides
    assert "factual" in profile.weight_overrides
    assert profile.weight_overrides["factual"] > 1.0


def test_to_dict_roundtrip():
    profile = QuantizationProfile.for_format("awq")
    d = profile.to_dict()
    assert d["format"] == "awq"
    assert d["semantic_threshold"] == 0.90
    assert isinstance(d["weight_overrides"], dict)


def test_factual_stricter_than_default():
    """Quantization SHOULD NOT introduce hallucinations — factual threshold must
    be stricter than the project's -0.20 default."""
    for fmt in SUPPORTED_FORMATS:
        profile = QuantizationProfile.for_format(fmt)
        assert profile.factual_regression_threshold > -0.20, (
            f"{fmt}: factual threshold {profile.factual_regression_threshold} "
            f"is no stricter than the default"
        )
