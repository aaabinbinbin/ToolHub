from __future__ import annotations

from uuid import uuid4

import pytest

from app.common.exceptions import NotFoundError
from app.repositories.approval_repository import ApprovalRepository
from app.repositories.db import get_connection, init_db
from app.repositories.llm_call_repository import LLMCallRepository
from app.repositories.sandbox_execution_repository import SandboxExecutionRepository
from app.repositories.task_event_repository import TaskEventRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.tool_call_repository import ToolCallRepository
from app.schemas.approval import ApprovalScope
from app.schemas.llm import LLMCallRecord
from app.schemas.permission import RunMode
from app.schemas.sandbox import SandboxRunResult
from app.schemas.tool import RiskLevel, ToolRegisterRequest, ToolType
from app.schemas.tool_call import ToolCallResult
from app.services.tool_registry_service import ToolRegistryService
from app.services.trace_service import TraceService


def test_trace_service_aggregates_full_trace() -> None:
    init_db()
    tool = ToolRegistryService().register_tool(
        ToolRegisterRequest(
            name=f"trace-test-{uuid4()}",
            description="Trace test tool",
            tool_type=ToolType.HTTP,
            endpoint="mock://echo",
            risk_level=RiskLevel.LOW,
        )
    )
    with get_connection() as connection:
        task = TaskRepository(connection).create_queued_task(
            user_input="trace test",
            run_mode=RunMode.SAFE_EXECUTE,
            priority="default",
        )
        trace_id = task["trace_id"]
        TaskEventRepository(connection).create(
            task_id=task["id"],
            run_id=task["run_id"],
            trace_id=trace_id,
            event_type="TASK_STARTED",
            step="task_worker",
            message="任务开始",
        )
        ToolCallRepository(connection).create(
            ToolCallResult(
                success=False,
                status="FAILED",
                tool_id=tool.id,
                tool_name=tool.name,
                tool_type=tool.tool_type.value,
                input={"q": "x"},
                output={"error": "bad"},
                error_message="bad",
                duration_ms=10,
                run_id=task["run_id"],
                trace_id=trace_id,
                task_id=task["id"],
                workspace_id="default",
            )
        )
        LLMCallRepository(connection).create(
            LLMCallRecord(
                task_id=task["id"],
                run_id=task["run_id"],
                trace_id=trace_id,
                node_name="tool_rerank",
                provider="mock",
                model="mock-model",
                prompt="prompt",
                response="{}",
                duration_ms=5,
                status="SUCCESS",
                workspace_id="default",
            )
        )
        SandboxExecutionRepository(connection).create(
            result=SandboxRunResult(
                command="python -c pass",
                stdout="",
                stderr="",
                exit_code=0,
                duration_ms=1,
                timeout_seconds=3,
                container_id="container-1",
                status="SUCCESS",
                language="python",
                artifacts=[],
            ),
            task_id=task["id"],
            run_id=task["run_id"],
            trace_id=trace_id,
            tool_name="sandbox",
        )
        ApprovalRepository(connection).create_pending(
            task_id=task["id"],
            run_id=task["run_id"],
            trace_id=trace_id,
            tool_id=tool.id,
            requested_action=f"execute:{tool.name}",
            reason="需要审批",
            approval_scope=ApprovalScope.TASK,
        )

    trace = TraceService().get_trace(trace_id)

    assert trace.trace_id == trace_id
    assert trace.summary.task_count == 1
    assert trace.summary.event_count == 1
    assert trace.summary.tool_call_count == 1
    assert trace.summary.llm_call_count == 1
    assert trace.summary.sandbox_execution_count == 1
    assert trace.summary.approval_count == 1
    assert trace.summary.error_types["TOOL_EXECUTION_FAILED"] == 1
    assert [item.created_at for item in trace.timeline] == sorted(
        item.created_at for item in trace.timeline
    )
    assert {item.source for item in trace.timeline} >= {
        "task_events",
        "tool_calls",
        "llm_calls",
        "sandbox_executions",
        "approval_requests",
    }


def test_trace_service_raises_for_missing_trace() -> None:
    init_db()
    with pytest.raises(NotFoundError):
        TraceService().get_trace(uuid4())
