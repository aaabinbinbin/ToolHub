from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.harness.workflow import AgentHarnessWorkflow
from app.schemas.permission import PermissionDecisionType, RunMode
from app.schemas.tool import HealthStatus, RiskLevel, ToolResponse, ToolStatus, ToolType


def make_tool(risk_level: RiskLevel = RiskLevel.LOW) -> ToolResponse:
    now = datetime.now(timezone.utc)
    return ToolResponse(
        id=uuid4(),
        name="safe-echo",
        description="安全回显工具",
        tool_type=ToolType.HTTP,
        endpoint="https://example.com/echo",
        mcp_url=None,
        transport=None,
        version="1.0.0",
        input_schema=None,
        output_schema=None,
        tags=["http"],
        risk_level=risk_level,
        status=ToolStatus.ACTIVE,
        health_status=HealthStatus.UP,
        last_checked_at=None,
        created_at=now,
        updated_at=now,
    )


def test_plan_only_mode_routes_to_summarize() -> None:
    """PLAN_ONLY 模式在 make_plan 后应直接跳到 summarize，不执行工具。"""
    wf = AgentHarnessWorkflow()
    state = {
        "task_id": str(uuid4()),
        "run_id": str(uuid4()),
        "trace_id": str(uuid4()),
        "user_input": "plan only test",
        "run_mode": RunMode.PLAN_ONLY.value,
        "final_status": "PLANNED",
        "current_step_index": 0,
        "max_steps": 3,
        "max_retries": 1,
        "timeout_seconds": None,
        "deadline_at": None,
        "observations": [],
        "stop_reason": None,
        "user_id": "local-user",
        "workspace_id": "default",
    }
    result = wf._next_after_plan(state)
    assert result == "summarize"


def test_plan_only_no_execution_path() -> None:
    """PLAN_ONLY 的 _next_after_plan 不能返回 execute。"""
    wf = AgentHarnessWorkflow()
    state = {
        "task_id": str(uuid4()),
        "run_id": str(uuid4()),
        "trace_id": str(uuid4()),
        "user_input": "plan only test",
        "run_mode": RunMode.PLAN_ONLY.value,
        "final_status": "PLANNED",
        "current_step_index": 0,
        "max_steps": 3,
        "max_retries": 1,
        "timeout_seconds": None,
        "deadline_at": None,
        "observations": [],
        "stop_reason": None,
        "user_id": "local-user",
        "workspace_id": "default",
    }
    result = wf._next_after_plan(state)
    assert result != "execute"


def test_plan_only_terminal_guard() -> None:
    """terminal_guard 对 PLANNED 状态应返回阻止继续执行的标记。"""
    wf = AgentHarnessWorkflow()
    state = {
        "task_id": str(uuid4()),
        "run_id": str(uuid4()),
        "trace_id": str(uuid4()),
        "user_input": "test",
        "run_mode": RunMode.PLAN_ONLY.value,
        "final_status": "PLANNED",
        "stop_reason": "PLAN_ONLY 模式只生成计划",
    }
    guard = wf._terminal_guard(state, "select_tool")
    assert guard is not None
    assert guard["final_status"] == "PLANNED"


def test_plan_only_is_non_runnable() -> None:
    """PLANNED 状态应在 NON_RUNNABLE_STATES 中。"""
    assert "PLANNED" in AgentHarnessWorkflow.NON_RUNNABLE_STATES
    assert "WAITING_APPROVAL" in AgentHarnessWorkflow.NON_RUNNABLE_STATES
    assert "DENIED" in AgentHarnessWorkflow.NON_RUNNABLE_STATES
    assert "NO_TOOL" in AgentHarnessWorkflow.NON_RUNNABLE_STATES
    assert "CANCELLED" in AgentHarnessWorkflow.NON_RUNNABLE_STATES
    assert "TIMEOUT" in AgentHarnessWorkflow.NON_RUNNABLE_STATES
    # FAILED 不在 NON_RUNNABLE_STATES 中，因为 _decide_next_step 需处理 FAILED 做 bounded retry
