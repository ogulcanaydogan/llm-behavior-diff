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


def test_dependabot_github_actions_policy_is_weekly_group_rollup() -> None:
    """The github-actions ecosystem must ship as a single weekly grouped rollup.

    Policy intent: keep CI noise low (one PR per week per ecosystem) while still
    receiving every available update through a single group rollup PR. The
    previous "ignore-major + limit 5" policy was retired in favour of grouped
    delivery so a single review covers the whole week.
    """
    assert DEPENDABOT_FILE.exists(), ".github/dependabot.yml is missing."

    payload = yaml.safe_load(DEPENDABOT_FILE.read_text(encoding="utf-8")) or {}
    assert isinstance(payload, dict), "dependabot.yml must be a top-level mapping."
    assert payload.get("version") == 2, "dependabot.yml version must be 2."

    update = _find_github_actions_update(payload)
    assert update is not None, "github-actions update block not found in dependabot.yml."

    schedule = update.get("schedule")
    assert isinstance(schedule, dict), "schedule must be a mapping."
    assert schedule.get("interval") == "weekly", "schedule interval must remain weekly."

    assert (
        update.get("open-pull-requests-limit") == 1
    ), "open-pull-requests-limit must remain 1 (one grouped PR per week)."

    commit_message = update.get("commit-message")
    assert isinstance(commit_message, dict), "commit-message must be a mapping."
    assert commit_message.get("prefix") == "chore", "commit message prefix must remain 'chore'."

    labels = update.get("labels")
    assert isinstance(labels, list), "labels must be a list."
    assert "dependencies" in labels, "labels must include 'dependencies'."

    groups = update.get("groups")
    assert isinstance(groups, dict) and groups, "groups must be present and non-empty."
    rollup = groups.get("actions-weekly-rollup")
    assert isinstance(rollup, dict), "'actions-weekly-rollup' group must be defined."
    assert rollup.get("patterns") == ["*"], "rollup must include all actions via '*' pattern."

    update_types = rollup.get("update-types") or []
    assert isinstance(update_types, list), "rollup update-types must be a list."
    for required in ("major", "minor", "patch"):
        assert (
            required in update_types
        ), f"rollup must include '{required}' update-types for full coverage."
