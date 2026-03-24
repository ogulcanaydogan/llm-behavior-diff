"""Tests for significance utilities."""

import pytest

from llm_behavior_diff.statistics import (
    benjamini_hochberg_adjust,
    bootstrap_rate_delta_interval,
    bootstrap_rate_interval,
    cohens_h_magnitude,
    cohens_h_rate_delta,
    permutation_rate_delta_test,
    wilson_rate_interval,
)


def test_bootstrap_rate_interval_is_deterministic_with_fixed_seed() -> None:
    values = [1, 0, 1, 1, 0, 0, 1]
    first = bootstrap_rate_interval(values, resamples=2000, confidence_level=0.95, seed=42)
    second = bootstrap_rate_interval(values, resamples=2000, confidence_level=0.95, seed=42)
    assert first == second


def test_bootstrap_rate_interval_edge_cases() -> None:
    empty = bootstrap_rate_interval([], seed=42)
    one_zero = bootstrap_rate_interval([0], seed=42)
    one_one = bootstrap_rate_interval([1], seed=42)
    all_zero = bootstrap_rate_interval([0, 0, 0, 0], seed=42)
    all_one = bootstrap_rate_interval([1, 1, 1, 1], seed=42)

    assert empty["point"] == 0.0
    assert empty["ci_low"] == 0.0
    assert empty["ci_high"] == 0.0
    assert empty["p_value_two_sided"] == 1.0

    assert one_zero["point"] == 0.0
    assert one_zero["ci_low"] == 0.0
    assert one_zero["ci_high"] == 0.0

    assert one_one["point"] == 1.0
    assert one_one["ci_low"] == 1.0
    assert one_one["ci_high"] == 1.0

    assert all_zero["point"] == 0.0
    assert all_one["point"] == 1.0


def test_bootstrap_rate_interval_ci_bounds_are_valid() -> None:
    payload = bootstrap_rate_interval([1, 0, 1, 0, 1, 1, 0, 0], seed=42)
    assert 0.0 <= payload["point"] <= 1.0
    assert 0.0 <= payload["ci_low"] <= 1.0
    assert 0.0 <= payload["ci_high"] <= 1.0
    assert payload["ci_low"] <= payload["point"] <= payload["ci_high"]


def test_bootstrap_rate_delta_interval_detects_strong_significance() -> None:
    delta = bootstrap_rate_delta_interval(
        [0] * 40,
        [1] * 40,
        resamples=3000,
        seed=42,
    )
    assert delta is not None
    assert delta["significant"] is True
    assert delta["ci_low"] > 0.0


def test_bootstrap_rate_delta_interval_non_significant_when_distributions_match() -> None:
    delta = bootstrap_rate_delta_interval(
        [1, 0] * 30,
        [1, 0] * 30,
        resamples=3000,
        seed=42,
    )
    assert delta is not None
    assert delta["significant"] is False
    assert delta["ci_low"] <= 0.0 <= delta["ci_high"]


def test_bootstrap_rate_delta_interval_returns_none_when_inputs_empty() -> None:
    assert bootstrap_rate_delta_interval([], [1, 0, 1], seed=42) is None
    assert bootstrap_rate_delta_interval([1, 0, 1], [], seed=42) is None


def test_wilson_rate_interval_bounds_are_valid() -> None:
    payload = wilson_rate_interval([1, 0, 1, 0, 1, 1, 0, 0], confidence_level=0.95)
    assert 0.0 <= payload["point"] <= 1.0
    assert 0.0 <= payload["ci_low"] <= 1.0
    assert 0.0 <= payload["ci_high"] <= 1.0
    assert payload["ci_low"] <= payload["point"] <= payload["ci_high"]


def test_wilson_rate_interval_edge_cases() -> None:
    empty = wilson_rate_interval([], confidence_level=0.95)
    one_zero = wilson_rate_interval([0], confidence_level=0.95)
    one_one = wilson_rate_interval([1], confidence_level=0.95)

    assert empty["point"] == 0.0
    assert empty["ci_low"] == 0.0
    assert empty["ci_high"] == 0.0

    assert one_zero["point"] == 0.0
    assert 0.0 <= one_zero["ci_low"] <= one_zero["ci_high"] <= 1.0

    assert one_one["point"] == 1.0
    assert 0.0 <= one_one["ci_low"] <= one_one["ci_high"] <= 1.0


def test_permutation_rate_delta_test_is_deterministic_with_fixed_seed() -> None:
    values_a = [0, 0, 0, 0, 0, 1, 0, 0]
    values_b = [1, 1, 1, 1, 1, 1, 0, 1]
    first = permutation_rate_delta_test(values_a, values_b, resamples=3000, seed=42)
    second = permutation_rate_delta_test(values_a, values_b, resamples=3000, seed=42)

    assert first is not None
    assert second is not None
    assert first == second


def test_permutation_rate_delta_test_strong_signal_is_significant() -> None:
    result = permutation_rate_delta_test([0] * 30, [1] * 30, resamples=3000, seed=42)
    assert result is not None
    assert result["point"] == 1.0
    assert result["significant"] is True
    assert float(result["p_value_two_sided"]) < 0.05


def test_permutation_rate_delta_test_returns_none_when_inputs_empty() -> None:
    assert permutation_rate_delta_test([], [1, 0, 1], seed=42) is None
    assert permutation_rate_delta_test([1, 0, 1], [], seed=42) is None


def test_cohens_h_rate_delta_and_magnitude() -> None:
    effect_h = cohens_h_rate_delta(0.0, 0.25)
    assert effect_h == pytest.approx(1.0471975512, rel=1e-6)
    assert cohens_h_magnitude(abs(effect_h)) == "large"


def test_cohens_h_magnitude_thresholds() -> None:
    assert cohens_h_magnitude(0.0) == "negligible"
    assert cohens_h_magnitude(0.19) == "negligible"
    assert cohens_h_magnitude(0.2) == "small"
    assert cohens_h_magnitude(0.49) == "small"
    assert cohens_h_magnitude(0.5) == "medium"
    assert cohens_h_magnitude(0.79) == "medium"
    assert cohens_h_magnitude(0.8) == "large"


def test_benjamini_hochberg_adjust_is_deterministic_and_preserves_order() -> None:
    first = benjamini_hochberg_adjust([0.01, 0.03, 0.2], alpha=0.05)
    second = benjamini_hochberg_adjust([0.01, 0.03, 0.2], alpha=0.05)
    assert first == second
    assert len(first) == 3
    assert first[0]["adjusted_p_value"] == pytest.approx(0.03, rel=1e-6)
    assert first[1]["adjusted_p_value"] == pytest.approx(0.045, rel=1e-6)
    assert first[2]["adjusted_p_value"] == pytest.approx(0.2, rel=1e-6)
    assert first[0]["significant"] is True
    assert first[1]["significant"] is True
    assert first[2]["significant"] is False


def test_benjamini_hochberg_adjust_handles_edge_cases() -> None:
    assert benjamini_hochberg_adjust([]) == []
    tied = benjamini_hochberg_adjust([0.02, 0.02], alpha=0.05)
    assert len(tied) == 2
    assert tied[0]["adjusted_p_value"] == pytest.approx(0.02, rel=1e-6)
    assert tied[1]["adjusted_p_value"] == pytest.approx(0.02, rel=1e-6)
