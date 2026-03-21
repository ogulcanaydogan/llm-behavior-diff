"""Guards for workflow action pinning and permission baselines."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterator

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = ROOT / ".github" / "workflows"

EXPECTED_PERMISSIONS: dict[str, dict[str, str]] = {
    "ci.yml": {"contents": "read"},
    "docker-image.yml": {"contents": "read", "packages": "write"},
    "model-upgrade-regression.yml": {"contents": "read"},
    "publish-pypi.yml": {"contents": "read", "id-token": "write"},
    "release-check.yml": {"contents": "read"},
}

SHA_PIN_PATTERN = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")
DEPRECATED_NODE20_ERA_SHAS = {
    "34e114876b0b11c390a56381ad16ebd13914f8d5",  # actions/checkout v4
    "a26af69be951a213d495a4c3e4e4022e16d87065",  # actions/setup-python v5
    "c94ce9fb468520275223c153574b00df6fe4bcc9",  # docker/login-action v3
    "ea165f8d65b6e75b540449e92b4886f43607fa02",  # actions/upload-artifact v4
}


def _iter_uses(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        uses = node.get("uses")
        if isinstance(uses, str):
            yield uses
        for value in node.values():
            yield from _iter_uses(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_uses(item)


def test_workflow_actions_are_sha_pinned_and_permissions_are_baselined() -> None:
    workflow_files = sorted(WORKFLOWS_DIR.glob("*.yml"))
    assert workflow_files, "No workflow files found under .github/workflows."

    actual_names = {path.name for path in workflow_files}
    expected_names = set(EXPECTED_PERMISSIONS)
    assert actual_names == expected_names, (
        "Workflow guard file list drifted.\n"
        f"Expected: {sorted(expected_names)}\n"
        f"Actual: {sorted(actual_names)}"
    )

    violations: list[str] = []
    for workflow_file in workflow_files:
        payload = yaml.safe_load(workflow_file.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            violations.append(f"{workflow_file.name}: invalid top-level YAML mapping")
            continue

        permissions = payload.get("permissions")
        expected_permissions = EXPECTED_PERMISSIONS[workflow_file.name]
        if permissions != expected_permissions:
            violations.append(
                f"{workflow_file.name}: permissions must be {expected_permissions}, "
                f"found {permissions}"
            )

        for uses in _iter_uses(payload):
            if uses.startswith("./"):
                continue
            if not SHA_PIN_PATTERN.match(uses):
                violations.append(
                    f"{workflow_file.name}: action ref must be SHA pinned, found '{uses}'"
                )
                continue

            action_ref = uses.rsplit("@", 1)[1]
            if action_ref in DEPRECATED_NODE20_ERA_SHAS:
                violations.append(
                    f"{workflow_file.name}: deprecated pre-Node24 action SHA used '{uses}'"
                )

    assert not violations, "Workflow security guard failed:\n" + "\n".join(violations)
