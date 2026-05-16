"""CLI integration tests for the --quantization flag (v1.1.0)."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from llm_behavior_diff.cli import main
from llm_behavior_diff.schema import BehaviorReport


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


_SUITE_YAML = """
name: quant_suite
description: quantization smoke suite
test_cases:
  - id: q1
    prompt: "What is 2+2?"
    category: factual_knowledge
    expected_behavior: Returns four
""".strip()


def test_run_quantization_fp8_wires_threshold(tmp_path: Path, monkeypatch) -> None:
    suite_path = _write(tmp_path / "suite.yaml", _SUITE_YAML)
    output_path = tmp_path / "report.json"
    captured: dict[str, object] = {}

    class FakeRunner:
        def __init__(
            self,
            model_a: str,
            model_b: str,
            semantic_threshold: float = 0.85,
            **kwargs,
        ) -> None:
            self.model_a = model_a
            self.model_b = model_b
            captured["semantic_threshold"] = semantic_threshold

        async def run_suite(self, suite_obj):
            return BehaviorReport(
                model_a=self.model_a,
                model_b=self.model_b,
                suite_name=suite_obj.name,
                total_tests=1,
            )

    monkeypatch.setattr("llm_behavior_diff.cli.BehaviorDiffRunner", FakeRunner)

    result = CliRunner().invoke(
        main,
        [
            "run",
            "--model-a",
            "model-fp16",
            "--model-b",
            "model-fp8",
            "--suite",
            str(suite_path),
            "--output",
            str(output_path),
            "--quantization",
            "fp8",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["semantic_threshold"] == 0.94

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    qp = payload["metadata"]["quantization_profile"]
    assert qp["format"] == "fp8"
    assert qp["semantic_threshold"] == 0.94
    assert qp["format_strict"] is False


def test_run_quantization_int8_wires_threshold(tmp_path: Path, monkeypatch) -> None:
    suite_path = _write(tmp_path / "suite.yaml", _SUITE_YAML)
    output_path = tmp_path / "report.json"
    captured: dict[str, object] = {}

    class FakeRunner:
        def __init__(
            self,
            model_a: str,
            model_b: str,
            semantic_threshold: float = 0.85,
            **kwargs,
        ) -> None:
            self.model_a = model_a
            self.model_b = model_b
            captured["semantic_threshold"] = semantic_threshold

        async def run_suite(self, suite_obj):
            return BehaviorReport(
                model_a=self.model_a,
                model_b=self.model_b,
                suite_name=suite_obj.name,
                total_tests=1,
            )

    monkeypatch.setattr("llm_behavior_diff.cli.BehaviorDiffRunner", FakeRunner)

    result = CliRunner().invoke(
        main,
        [
            "run",
            "--model-a",
            "model-fp16",
            "--model-b",
            "model-int8",
            "--suite",
            str(suite_path),
            "--output",
            str(output_path),
            "--quantization",
            "int8",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["semantic_threshold"] == 0.92
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["metadata"]["quantization_profile"]["format"] == "int8"


def test_run_without_quantization_uses_default_threshold(tmp_path: Path, monkeypatch) -> None:
    suite_path = _write(tmp_path / "suite.yaml", _SUITE_YAML)
    output_path = tmp_path / "report.json"
    captured: dict[str, object] = {}

    class FakeRunner:
        def __init__(
            self,
            model_a: str,
            model_b: str,
            semantic_threshold: float = 0.85,
            **kwargs,
        ) -> None:
            self.model_a = model_a
            self.model_b = model_b
            captured["semantic_threshold"] = semantic_threshold

        async def run_suite(self, suite_obj):
            return BehaviorReport(
                model_a=self.model_a,
                model_b=self.model_b,
                suite_name=suite_obj.name,
                total_tests=1,
            )

    monkeypatch.setattr("llm_behavior_diff.cli.BehaviorDiffRunner", FakeRunner)

    result = CliRunner().invoke(
        main,
        [
            "run",
            "--model-a",
            "gpt-4o",
            "--model-b",
            "gpt-4.5",
            "--suite",
            str(suite_path),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["semantic_threshold"] == 0.85
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert "quantization_profile" not in payload["metadata"]
