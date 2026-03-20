"""Guards for workflow-level Node24 JavaScript action runtime hardening."""

from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = ROOT / ".github" / "workflows"


def test_all_workflows_force_node24_runtime() -> None:
    """Ensure all workflow files keep FORCE_JAVASCRIPT_ACTIONS_TO_NODE24 enabled."""
    workflow_files = sorted(WORKFLOWS_DIR.glob("*.yml"))
    assert workflow_files, "No workflow files found under .github/workflows."

    violations: list[str] = []
    for workflow_file in workflow_files:
        payload = yaml.safe_load(workflow_file.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            violations.append(f"{workflow_file.name}: invalid top-level YAML mapping")
            continue

        env = payload.get("env")
        if not isinstance(env, dict):
            violations.append(f"{workflow_file.name}: missing top-level env block")
            continue

        value = env.get("FORCE_JAVASCRIPT_ACTIONS_TO_NODE24")
        if str(value).lower() != "true":
            violations.append(
                f"{workflow_file.name}: FORCE_JAVASCRIPT_ACTIONS_TO_NODE24 must be true"
            )

    assert not violations, "Workflow Node24 guard failed:\n" + "\n".join(violations)
