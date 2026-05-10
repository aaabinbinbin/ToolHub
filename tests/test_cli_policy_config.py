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


def test_cli_policy_loads_rule_pack_directory(tmp_path, monkeypatch) -> None:
    pack_dir = tmp_path / "packs"
    pack_dir.mkdir()
    (pack_dir / "demo.json").write_text(
        json.dumps(
            {
                "rules": [
                    {
                        "id": "cli://pack/echo",
                        "description": "rule pack echo",
                        "category": "demo",
                        "owner": "toolhub",
                        "workspace_id": "default",
                        "effect": "ALLOW",
                        "risk_level": "LOW",
                        "image": "alpine:latest",
                        "argv_template": ["echo"],
                        "params": {},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CLI_POLICY_DIR", str(pack_dir))
    monkeypatch.setenv("CLI_POLICY_PATH", str(tmp_path / "missing.json"))
    from app.common.config import get_settings

    get_settings.cache_clear()
    policy = CLICommandPolicy(config_path=tmp_path / "missing.json")

    plan = policy.build_plan(endpoint="cli://pack/echo", tool_input={})

    assert plan.argv == ["echo"]
    assert plan.rule.category == "demo"


def test_cli_policy_rejects_invalid_config(tmp_path) -> None:
    config_path = tmp_path / "cli_policy.json"
    config_path.write_text(json.dumps({"rules": [{"id": "broken"}]}), encoding="utf-8")

    with pytest.raises(ValueError):
        CLICommandPolicy(config_path=config_path)
