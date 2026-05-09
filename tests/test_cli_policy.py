from __future__ import annotations

import pytest

from app.security.cli_policy import CLICommandPolicy


def test_cli_policy_supports_legacy_git_status() -> None:
    plan = CLICommandPolicy().build_plan(
        endpoint=None,
        tool_input={"command": "git status --short"},
    )

    assert plan.rule.id == "cli://git/status-short"
    assert plan.argv == ["-c", "safe.directory=/workspace", "status", "--short"]


def test_cli_policy_builds_structured_git_diff_args() -> None:
    plan = CLICommandPolicy().build_plan(
        endpoint="cli://git/diff",
        tool_input={"args": {"path": "app", "staged": True}},
    )

    assert plan.argv == [
        "-c",
        "safe.directory=/workspace",
        "diff",
        "--staged",
        "--",
        "app",
    ]


def test_cli_policy_rejects_shell_syntax_and_parent_path() -> None:
    policy = CLICommandPolicy()

    with pytest.raises(ValueError):
        policy.build_plan(
            endpoint=None,
            tool_input={"command": "git status --short; rm -rf /"},
        )

    with pytest.raises(ValueError):
        policy.build_plan(
            endpoint="cli://git/diff",
            tool_input={"args": {"path": "../secret"}},
        )

