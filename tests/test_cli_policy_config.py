from __future__ import annotations

import json

import pytest

from app.security.cli_policy import CLICommandPolicy


def test_cli_policy_loads_git_log_from_config() -> None:
    plan = CLICommandPolicy().build_plan(
        endpoint="cli://git/log-oneline",
        tool_input={"args": {"max_count": 3}},
    )

    assert plan.rule.id == "cli://git/log-oneline"
    assert plan.argv == [
        "-c",
        "safe.directory=/workspace",
        "log",
        "--oneline",
        "-n",
        "3",
    ]


def test_cli_policy_uses_default_rules_when_config_missing(tmp_path) -> None:
    policy = CLICommandPolicy(config_path=tmp_path / "missing.json")

    plan = policy.build_plan(
        endpoint="cli://git/status-short",
        tool_input={},
    )

    assert plan.argv == ["-c", "safe.directory=/workspace", "status", "--short"]


def test_cli_policy_loads_custom_json_rule(tmp_path) -> None:
    config_path = tmp_path / "cli_policy.json"
    config_path.write_text(
        json.dumps(
            {
                "rules": [
                    {
                        "id": "cli://demo/echo",
                        "description": "测试配置化 echo 规则",
                        "effect": "ALLOW",
                        "risk_level": "LOW",
                        "image": "alpine:latest",
                        "argv_template": ["echo"],
                        "params": {
                            "message": {
                                "type": "string",
                                "default": "hello",
                                "max_length": 20,
                            }
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    plan = CLICommandPolicy(config_path=config_path).build_plan(
        endpoint="cli://demo/echo",
        tool_input={"args": {"message": "toolhub"}},
    )

    assert plan.argv == ["echo", "toolhub"]


def test_cli_policy_rejects_invalid_config(tmp_path) -> None:
    config_path = tmp_path / "cli_policy.json"
    config_path.write_text(json.dumps({"rules": [{"id": "broken"}]}), encoding="utf-8")

    with pytest.raises(ValueError):
        CLICommandPolicy(config_path=config_path)
