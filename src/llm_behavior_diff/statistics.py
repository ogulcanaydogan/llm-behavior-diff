"""Deterministic bootstrap significance utilities."""

from __future__ import annotations

import random
from typing import Sequence

DEFAULT_BOOTSTRAP_RESAMPLES = 5000
DEFAULT_CONFIDENCE_LEVEL = 0.95
DEFAULT_BOOTSTRAP_SEED = 42


def bootstrap_rate_interval(
    values: Sequence[int | bool],
    *,
    resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
    seed: int = DEFAULT_BOOTSTRAP_SEED,
) -> dict[str, float]:
    """Compute point estimate, CI, and two-sided p-value for a binary rate."""
    sample = _coerce_binary(values)
    sample_size = len(sample)
    if sample_size == 0:
        return {
            "point": 0.0,
            "ci_low": 0.0,
            "ci_high": 0.0,
            "p_value_two_sided": 1.0,
        }

    point = _mean(sample)
    distribution = _bootstrap_means(
        sample=sample,
        resamples=resamples,
        rng=random.Random(seed),
    )
    ci_low, ci_high = _interval_from_distribution(distribution, confidence_level=confidence_level)
    p_value = _two_sided_p_value(distribution, null_value=0.0)
    return {
        "point": point,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "p_value_two_sided": p_value,
    }


def bootstrap_rate_delta_interval(
    values_a: Sequence[int | bool],
    values_b: Sequence[int | bool],
    *,
    resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
    seed: int = DEFAULT_BOOTSTRAP_SEED,
) -> dict[str, float | bool] | None:
    """Compute bootstrap CI and significance for rate delta `rate_b - rate_a`."""
    sample_a = _coerce_binary(values_a)
    sample_b = _coerce_binary(values_b)
    if not sample_a or not sample_b:
        return None

    rng = random.Random(seed)
    distribution_a = _bootstrap_means(sample=sample_a, resamples=resamples, rng=rng)
    distribution_b = _bootstrap_means(sample=sample_b, resamples=resamples, rng=rng)
    delta_distribution = [b - a for a, b in zip(distribution_a, distribution_b, strict=True)]

    point = _mean(sample_b) - _mean(sample_a)
    ci_low, ci_high = _interval_from_distribution(
        delta_distribution,
        confidence_level=confidence_level,
    )
    p_value = _two_sided_p_value(delta_distribution, null_value=0.0)

    return {
        "point": point,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "significant": ci_low > 0.0 or ci_high < 0.0,
        "p_value_two_sided": p_value,
    }


def _coerce_binary(values: Sequence[int | bool]) -> list[int]:
    return [1 if bool(value) else 0 for value in values]


def _bootstrap_means(*, sample: Sequence[int], resamples: int, rng: random.Random) -> list[float]:
    size = len(sample)
    if size == 0:
        return []

    safe_resamples = max(1, int(resamples))
    means: list[float] = []
    for _ in range(safe_resamples):
        drawn = [sample[rng.randrange(size)] for _ in range(size)]
        means.append(_mean(drawn))
    return means


def _interval_from_distribution(
    distribution: Sequence[float], *, confidence_level: float
) -> tuple[float, float]:
    if not distribution:
        return 0.0, 0.0

    clamped = min(0.9999, max(0.0, float(confidence_level)))
    alpha = 1.0 - clamped
    lower_q = alpha / 2.0
    upper_q = 1.0 - (alpha / 2.0)
    sorted_dist = sorted(distribution)
    return (
        _percentile(sorted_dist, lower_q),
        _percentile(sorted_dist, upper_q),
    )


def _percentile(sorted_values: Sequence[float], quantile: float) -> float:
    if not sorted_values:
        return 0.0

    q = min(1.0, max(0.0, quantile))
    if len(sorted_values) == 1:
        return float(sorted_values[0])

    index = q * (len(sorted_values) - 1)
    lower = int(index)
    upper = min(len(sorted_values) - 1, lower + 1)
    weight = index - lower
    return (1.0 - weight) * float(sorted_values[lower]) + weight * float(sorted_values[upper])


def _mean(values: Sequence[int | float]) -> float:
    if not values:
        return 0.0
    return float(sum(values)) / float(len(values))


def _two_sided_p_value(distribution: Sequence[float], *, null_value: float = 0.0) -> float:
    if not distribution:
        return 1.0

    count = float(len(distribution))
    prob_le_null = sum(1 for value in distribution if value <= null_value) / count
    prob_ge_null = sum(1 for value in distribution if value >= null_value) / count
    return min(1.0, 2.0 * min(prob_le_null, prob_ge_null))
