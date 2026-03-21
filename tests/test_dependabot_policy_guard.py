"""Guards for Dependabot governance policy on GitHub Actions updates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]
DEPENDABOT_FILE = ROOT / ".github" / "dependabot.yml"


def _find_github_actions_update(payload: dict[str, Any]) -> dict[str, Any] | None:
    updates = payload.get("updates")
    if not isinstance(updates, list):
        return None

    for entry in updates:
        if not isinstance(entry, dict):
            continue
        if entry.get("package-ecosystem") == "github-actions" and entry.get("directory") == "/":
            return entry
    return None


def test_dependabot_github_actions_policy_is_minor_patch_only() -> None:
    assert DEPENDABOT_FILE.exists(), ".github/dependabot.yml is missing."

    payload = yaml.safe_load(DEPENDABOT_FILE.read_text(encoding="utf-8")) or {}
    assert isinstance(payload, dict), "dependabot.yml must be a top-level mapping."
    assert payload.get("version") == 2, "dependabot.yml version must be 2."

    update = _find_github_actions_update(payload)
    assert update is not None, "github-actions update block not found in dependabot.yml."

    schedule = update.get("schedule")
    assert isinstance(schedule, dict), "schedule must be a mapping."
    assert schedule.get("interval") == "weekly", "schedule interval must remain weekly."

    assert update.get("open-pull-requests-limit") == 5, "open-pull-requests-limit must remain 5."

    commit_message = update.get("commit-message")
    assert isinstance(commit_message, dict), "commit-message must be a mapping."
    assert (
        commit_message.get("prefix") == "chore(ci-actions)"
    ), "commit message prefix must remain 'chore(ci-actions)'."

    labels = update.get("labels")
    assert isinstance(labels, list), "labels must be a list."
    assert (
        "dependencies" in labels and "github-actions" in labels
    ), "labels must include 'dependencies' and 'github-actions'."

    ignore = update.get("ignore")
    assert isinstance(ignore, list) and ignore, "ignore list must be present and non-empty."

    major_ignored = False
    for entry in ignore:
        if not isinstance(entry, dict):
            continue
        dependency_name = entry.get("dependency-name")
        update_types = entry.get("update-types")
        if dependency_name != "*":
            continue
        if isinstance(update_types, list) and "version-update:semver-major" in update_types:
            major_ignored = True
            break

    assert major_ignored, "dependabot github-actions policy must ignore semver-major updates."
