"""Documentation consistency checks for implemented feature claims."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC_PATHS = [ROOT / "README.md", ROOT / "ROADMAP.md", *sorted((ROOT / "docs").glob("**/*.md"))]
STALE_PHRASES = {
    "llm-as-judge is not implemented yet",
    "no llm-as-judge mode yet",
    "no statistical significance layer yet",
    "llm-as-judge is planned as an optional layer",
    "no llm-as-judge in this version",
}


def test_docs_do_not_include_stale_feature_claims() -> None:
    violations: list[str] = []
    for path in DOC_PATHS:
        content = path.read_text(encoding="utf-8").lower()
        for phrase in STALE_PHRASES:
            if phrase in content:
                violations.append(f"{path.relative_to(ROOT)} -> '{phrase}'")

    assert not violations, "Stale claims found in docs:\n" + "\n".join(violations)
