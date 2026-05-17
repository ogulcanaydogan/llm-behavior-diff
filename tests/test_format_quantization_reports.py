"""Tests for quantization profile section in markdown and HTML report formatters."""

from __future__ import annotations

from llm_behavior_diff.cli import _format_html, _format_markdown
from llm_behavior_diff.profiles.quantization import QuantizationProfile
from llm_behavior_diff.schema import BehaviorReport


def _minimal_report(metadata: dict | None = None) -> BehaviorReport:
    return BehaviorReport(
        model_a="gpt-4o",
        model_b="gpt-4o-mini-int8",
        suite_name="test-suite",
        total_tests=5,
        total_diffs=1,
        regressions=0,
        improvements=1,
        duration_seconds=0.5,
        metadata=metadata or {},
    )


def test_format_markdown_includes_quantization_when_present() -> None:
    profile_dict = QuantizationProfile.for_format("int8").to_dict()
    report = _minimal_report(metadata={"quantization_profile": profile_dict})
    md = _format_markdown(report)
    assert "## Quantization Profile" in md
    assert "- **Format**: int8" in md
    assert "- **Semantic Threshold**: 0.92" in md
    assert "- **Factual Regression Threshold**: -0.05" in md
    assert "- **Format Strict**: False" in md
    assert "factual=1.5" in md


def test_format_markdown_omits_quantization_when_absent() -> None:
    report = _minimal_report()
    md = _format_markdown(report)
    assert "Quantization Profile" not in md


def test_format_markdown_omits_quantization_for_invalid_metadata() -> None:
    report = _minimal_report(metadata={"quantization_profile": "not-a-dict"})
    md = _format_markdown(report)
    assert "Quantization Profile" not in md


def test_format_html_includes_quantization_when_present() -> None:
    profile_dict = QuantizationProfile.for_format("fp8").to_dict()
    report = _minimal_report(metadata={"quantization_profile": profile_dict})
    html = _format_html(report)
    assert "<h2>Quantization Profile</h2>" in html
    assert "fp8" in html
    assert "quant-profile-section" in html
    assert "Semantic Threshold" in html
    assert "factual=1.5" in html


def test_format_html_omits_quantization_when_absent() -> None:
    report = _minimal_report()
    html = _format_html(report)
    assert "Quantization Profile" not in html
    assert "quant-profile-section" not in html


def test_format_html_omits_quantization_for_invalid_metadata() -> None:
    report = _minimal_report(metadata={"quantization_profile": 42})
    html = _format_html(report)
    assert "Quantization Profile" not in html


def test_format_markdown_all_formats() -> None:
    for fmt in ("int8", "fp8", "awq", "gptq", "int4"):
        profile_dict = QuantizationProfile.for_format(fmt).to_dict()
        report = _minimal_report(metadata={"quantization_profile": profile_dict})
        md = _format_markdown(report)
        assert f"- **Format**: {fmt}" in md
