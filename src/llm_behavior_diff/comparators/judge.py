"""Optional LLM-as-judge comparator (metadata-only)."""

from __future__ import annotations

import json
import re

from ..schema import TestCase
from .base import ComparatorResult

_JSON_BLOCK_PATTERN = re.compile(r"\{.*\}", re.DOTALL)
_ALLOWED_WINNERS = {"A", "B", "TIE", "UNKNOWN"}


def _clamp_confidence(value: object, fallback: float = 0.0) -> float:
    """Clamp confidence values into [0, 1] with a safe fallback."""
    if not isinstance(value, (int, float, str)):
        return fallback
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return min(1.0, max(0.0, parsed))


class JudgeComparator:
    """Parse and map judge model output into ComparatorResult."""

    def __init__(self, max_tokens: int = 256, temperature: float = 0.0):
        self.max_tokens = max_tokens
        self.temperature = temperature

    def build_prompt(self, test_case: TestCase, response_a: str, response_b: str) -> str:
        """Build a deterministic judge prompt with strict JSON output requirement."""
        return (
            "You are a strict evaluator. Compare two assistant responses to the same prompt.\n"
            "Use the expected behavior as rubric.\n"
            "Return JSON only with fields: winner, confidence, reason.\n"
            "winner must be one of: A, B, TIE, UNKNOWN.\n"
            "confidence must be a number from 0 to 1.\n"
            "reason must be concise.\n\n"
            f"PROMPT:\n{test_case.prompt}\n\n"
            f"EXPECTED_BEHAVIOR:\n{test_case.expected_behavior}\n\n"
            f"RESPONSE_A:\n{response_a}\n\n"
            f"RESPONSE_B:\n{response_b}\n"
        )

    def compare_from_output(self, output_text: str) -> ComparatorResult:
        """Parse raw judge output and convert it into ComparatorResult."""
        payload = self._parse_payload(output_text)
        if payload is None:
            return self.uncertain_result("Judge output is not valid JSON.")

        winner = str(payload.get("winner", "UNKNOWN")).strip().upper()
        if winner not in _ALLOWED_WINNERS:
            return self.uncertain_result(f"Unsupported winner value: {winner}")

        confidence = _clamp_confidence(payload.get("confidence"), fallback=0.0)
        raw_reason = payload.get("reason", "")
        reason = str(raw_reason).strip()
        if not reason:
            reason = self._default_reason_for_winner(winner)

        return self._result_from_winner(winner=winner, confidence=confidence, reason=reason)

    def uncertain_result(self, reason: str) -> ComparatorResult:
        """Return normalized uncertain judge outcome."""
        return ComparatorResult(
            score_a=0.0,
            score_b=0.0,
            delta=0.0,
            applies=True,
            decision="judge_uncertain",
            confidence=0.0,
            reason=reason,
        )

    def error_result(self, reason: str) -> ComparatorResult:
        """Return normalized judge error outcome."""
        return ComparatorResult(
            score_a=0.0,
            score_b=0.0,
            delta=0.0,
            applies=True,
            decision="judge_error",
            confidence=0.0,
            reason=reason,
        )

    def _parse_payload(self, output_text: str) -> dict[str, object] | None:
        text = output_text.strip()
        if not text:
            return None

        if text.startswith("```"):
            # Handle fenced JSON like ```json ... ```
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)

        parsed = self._try_parse_json(text)
        if isinstance(parsed, dict):
            return parsed

        block_match = _JSON_BLOCK_PATTERN.search(text)
        if not block_match:
            return None

        parsed = self._try_parse_json(block_match.group(0))
        return parsed if isinstance(parsed, dict) else None

    def _try_parse_json(self, text: str) -> object | None:
        try:
            parsed: object = json.loads(text)
            return parsed
        except Exception:
            return None

    def _result_from_winner(self, winner: str, confidence: float, reason: str) -> ComparatorResult:
        if winner == "A":
            return ComparatorResult(
                score_a=1.0,
                score_b=0.0,
                delta=-1.0,
                applies=True,
                decision="judge_regression",
                confidence=confidence,
                reason=reason,
            )
        if winner == "B":
            return ComparatorResult(
                score_a=0.0,
                score_b=1.0,
                delta=1.0,
                applies=True,
                decision="judge_improvement",
                confidence=confidence,
                reason=reason,
            )
        if winner == "TIE":
            return ComparatorResult(
                score_a=0.5,
                score_b=0.5,
                delta=0.0,
                applies=True,
                decision="judge_no_change",
                confidence=confidence,
                reason=reason,
            )
        return self.uncertain_result(reason)

    def _default_reason_for_winner(self, winner: str) -> str:
        if winner == "A":
            return "Judge selected model A."
        if winner == "B":
            return "Judge selected model B."
        if winner == "TIE":
            return "Judge reported no meaningful difference."
        return "Judge could not decide."
