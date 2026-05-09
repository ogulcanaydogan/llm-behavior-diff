"""Diff profiles — pre-tuned threshold and weight bundles for specific comparison contexts.

A profile bundles comparator weights, thresholds, and category filters tuned for a
specific kind of model change (full-version upgrade, quantization, fine-tune,
distillation). Selecting a profile via ``--profile <name>`` overrides the defaults
without requiring callers to hand-tune individual flags.
"""

from llm_behavior_diff.profiles.quantization import QuantizationProfile

__all__ = ["QuantizationProfile"]
