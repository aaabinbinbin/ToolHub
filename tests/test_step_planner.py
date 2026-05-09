from __future__ import annotations

from uuid import uuid4

from app.schemas.llm import LLMResult
from app.harness.step_planner import HarnessStepPlanner


class FakeLLMClient:
    def __init__(self, parsed: dict | None) -> None:
        self.parsed = parsed

    def complete_json(self, prompt: str, **kwargs):
        return (
            LLMResult(
                text="{}" if self.parsed is None else "planned",
                provider="fake",
                model="fake",
            ),
            self.parsed,
        )


class FakeToolRegistryService:
    def search_tools(self, query: str, include_disabled: bool = False):
        return []


def test_step_planner_creates_multi_step_git_plan() -> None:
    steps = HarnessStepPlanner().create_steps(
        user_input="请查看 git status 和 diff",
        intent={
            "intent": "CLI_EXECUTION",
            "suggested_tool_type": "CLI",
            "tool_input": {},
        },
    )

    assert [step["tool_input"]["rule_id"] for step in steps] == [
        "cli://git/status-short",
        "cli://git/diff",
    ]
    assert [step["index"] for step in steps] == [0, 1]
    assert all(step["status"] == "PENDING" for step in steps)


def test_step_planner_supports_git_log_step() -> None:
    steps = HarnessStepPlanner().create_steps(
        user_input="请查看 git log 提交历史",
        intent={
            "intent": "CLI_EXECUTION",
            "suggested_tool_type": "CLI",
            "tool_input": {},
        },
    )

    assert len(steps) == 1
    assert steps[0]["tool_input"] == {
        "rule_id": "cli://git/log-oneline",
        "args": {"max_count": 5},
    }


def test_step_planner_falls_back_to_intent_tool_input() -> None:
    steps = HarnessStepPlanner().create_steps(
        user_input="请计算 1 + 2",
        intent={
            "intent": "CALCULATE",
            "summary": "用户想计算表达式。",
            "suggested_tool_type": "MCP",
            "tool_input": {"expression": "1 + 2"},
        },
    )

    assert len(steps) == 1
    assert steps[0]["objective"] == "用户想计算表达式。"
    assert steps[0]["tool_input"] == {"expression": "1 + 2"}


def test_step_planner_normalizes_code_hint_for_sandbox_schema() -> None:
    steps = HarnessStepPlanner().create_steps(
        user_input="运行 Python print(1)",
        intent={
            "intent": "RUN_CODE",
            "summary": "用户想运行 Python 代码。",
            "suggested_tool_type": "SANDBOX",
            "tool_input": {"language": "python", "code_hint": "print(1)"},
        },
    )

    assert steps[0]["tool_input"]["code"] == "print(1)"
    assert "code_hint" not in steps[0]["tool_input"]


def test_step_planner_uses_llm_plan_when_audited_ids_exist() -> None:
    planner = HarnessStepPlanner(
        llm_client=FakeLLMClient(
            {
                "steps": [
                    {
                        "objective": "查看 Git 状态",
                        "intent": "CLI",
                        "suggested_tool_type": "cli",
                        "tool_input": {"command": "git status"},
                    },
                    {
                        "objective": "查看 Git diff",
                        "intent": "CLI_EXECUTION",
                        "suggested_tool_type": "CLI",
                        "tool_input": {"rule_id": "cli://git/diff", "args": {"path": "."}},
                    },
                ]
            }
        ),
        tool_registry_service=FakeToolRegistryService(),
    )

    steps = planner.create_steps(
        user_input="请查看 git 状态和 diff",
        intent={"intent": "CLI_EXECUTION", "suggested_tool_type": "CLI"},
        task_id=uuid4(),
        run_id=uuid4(),
        trace_id=uuid4(),
    )

    assert planner.last_planner == "llm-v1"
    assert planner.last_fallback_used is False
    assert [step["index"] for step in steps] == [0, 1]
    assert steps[0]["tool_input"] == {"rule_id": "cli://git/status-short", "args": {}}
    assert steps[1]["tool_input"] == {"rule_id": "cli://git/diff", "args": {"path": "."}}


def test_step_planner_falls_back_when_llm_plan_is_invalid() -> None:
    planner = HarnessStepPlanner(
        llm_client=FakeLLMClient({"items": []}),
        tool_registry_service=FakeToolRegistryService(),
    )

    steps = planner.create_steps(
        user_input="请查看 git log 提交历史",
        intent={"intent": "CLI_EXECUTION", "suggested_tool_type": "CLI"},
        task_id=uuid4(),
        run_id=uuid4(),
        trace_id=uuid4(),
    )

    assert planner.last_planner == "deterministic-fallback-v1"
    assert planner.last_fallback_used is True
    assert steps[0]["tool_input"]["rule_id"] == "cli://git/log-oneline"
