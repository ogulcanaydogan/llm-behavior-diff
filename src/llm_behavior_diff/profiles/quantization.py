"""Quantization-aware diff profile for FP16 vs INT8 / FP8 / AWQ / GPTQ comparisons.

Quantization typically produces small numerical and lexical drift (rephrasing,
minor token differences) without changing core behavior. The default diff
thresholds tuned for full model-version upgrades are too sensitive for this
case and produce false-positive regressions. This profile re-tunes thresholds
for the quantization-specific signal.

Usage
-----

>>> from llm_behavior_diff.profiles import QuantizationProfile
>>> profile = QuantizationProfile.for_format("int8")
>>> profile.semantic_threshold
0.92

Or via CLI (v1.1.0): ``llm-diff compare --profile quantization-int8 ...``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class QuantizationProfile:
    """Threshold + weight bundle calibrated for quantized-vs-FP-baseline diffs.

    Attributes:
        format: The target quantization format (``int8``, ``fp8``, ``awq``, ``gptq``, ``int4``).
        semantic_threshold: Minimum cosine similarity to consider responses "same".
            Higher than the default 0.85 because quantized outputs often paraphrase.
        behavioral_regression_threshold: Behavior-coverage delta to flag as regression.
            Less strict than -0.20 default; quantization typically doesn't break behaviors.
        factual_regression_threshold: Factual-accuracy delta to flag as regression.
            Stricter than the default; quantization SHOULD NOT introduce hallucinations.
        format_strict: Whether format comparator runs in strict mode.
            Disabled — quantization expected to produce minor format drift.
        weight_overrides: Per-comparator weight multipliers for the aggregate score.
    """

    format: str
    semantic_threshold: float
    behavioral_regression_threshold: float
    factual_regression_threshold: float
    format_strict: bool
    weight_overrides: dict[str, float] = field(default_factory=dict)

    _FORMAT_THRESHOLDS: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def for_format(cls, fmt: str) -> "QuantizationProfile":
        """Construct a profile pre-tuned for the named quantization format.

        Args:
            fmt: One of ``int8``, ``fp8``, ``awq``, ``gptq``, ``int4``.

        Raises:
            ValueError: For unknown formats.
        """
        spec = _FORMAT_SPEC.get(fmt.lower())
        if spec is None:
            raise ValueError(
                f"Unknown quantization format: {fmt!r}. " f"Supported: {sorted(_FORMAT_SPEC)}"
            )
        return cls(
            format=fmt.lower(),
            semantic_threshold=spec["semantic_threshold"],
            behavioral_regression_threshold=spec["behavioral_regression_threshold"],
            factual_regression_threshold=spec["factual_regression_threshold"],
            format_strict=spec["format_strict"],
            weight_overrides=dict(spec.get("weight_overrides", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "semantic_threshold": self.semantic_threshold,
            "behavioral_regression_threshold": self.behavioral_regression_threshold,
            "factual_regression_threshold": self.factual_regression_threshold,
            "format_strict": self.format_strict,
            "weight_overrides": dict(self.weight_overrides),
        }


_FORMAT_SPEC: dict[str, dict[str, Any]] = {
    "int8": {
        "semantic_threshold": 0.92,
        "behavioral_regression_threshold": -0.10,
        "factual_regression_threshold": -0.05,
        "format_strict": False,
        "weight_overrides": {"semantic": 0.8, "factual": 1.5, "format": 0.5},
    },
    "fp8": {
        "semantic_threshold": 0.94,
        "behavioral_regression_threshold": -0.08,
        "factual_regression_threshold": -0.03,
        "format_strict": False,
        "weight_overrides": {"semantic": 0.9, "factual": 1.5, "format": 0.7},
    },
    "awq": {
        "semantic_threshold": 0.90,
        "behavioral_regression_threshold": -0.12,
        "factual_regression_threshold": -0.05,
        "format_strict": False,
        "weight_overrides": {"semantic": 0.8, "factual": 1.4, "format": 0.5},
    },
    "gptq": {
        "semantic_threshold": 0.90,
        "behavioral_regression_threshold": -0.12,
        "factual_regression_threshold": -0.05,
        "format_strict": False,
        "weight_overrides": {"semantic": 0.8, "factual": 1.4, "format": 0.5},
    },
    "int4": {
        "semantic_threshold": 0.85,
        "behavioral_regression_threshold": -0.15,
        "factual_regression_threshold": -0.08,
        "format_strict": False,
        "weight_overrides": {"semantic": 0.7, "factual": 1.3, "format": 0.4},
    },
}


SUPPORTED_FORMATS: tuple[str, ...] = tuple(sorted(_FORMAT_SPEC))
