from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from app.common.exceptions import NotFoundError
from app.repositories.approval_repository import ApprovalRepository
from app.repositories.db import get_connection
from app.repositories.llm_call_repository import LLMCallRepository
from app.repositories.sandbox_execution_repository import SandboxExecutionRepository
from app.repositories.task_event_repository import TaskEventRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.tool_call_repository import ToolCallRepository
from app.schemas.trace import TraceResponse, TraceSummary, TraceTimelineItem


class TraceService:
    """按 trace_id 聚合 Agent 执行链路，服务 Console 和排障视图。"""

    def get_trace(self, trace_id: UUID) -> TraceResponse:
        """查询并聚合同一 trace 下的全部审计数据。"""
        with get_connection() as connection:
            tasks = TaskRepository(connection).list_by_trace_id(trace_id)
            task_events = TaskEventRepository(connection).list_by_trace_id(trace_id)
            tool_calls = ToolCallRepository(connection).list_by_trace_id(trace_id)
            llm_calls = LLMCallRepository(connection).list_by_trace_id(trace_id)
            sandbox_executions = SandboxExecutionRepository(connection).list_by_trace_id(trace_id)
            approval_requests = ApprovalRepository(connection).list_by_trace_id(trace_id)

        if not any([tasks, task_events, tool_calls, llm_calls, sandbox_executions, approval_requests]):
            raise NotFoundError(f"Trace not found: {trace_id}")

        timeline = self._build_timeline(
            task_events=task_events,
            tool_calls=tool_calls,
            llm_calls=llm_calls,
            sandbox_executions=sandbox_executions,
            approval_requests=approval_requests,
        )
        summary = self._build_summary(
            trace_id=trace_id,
            tasks=tasks,
            task_events=task_events,
            tool_calls=tool_calls,
            llm_calls=llm_calls,
            sandbox_executions=sandbox_executions,
            approval_requests=approval_requests,
        )
        return TraceResponse(
            trace_id=trace_id,
            summary=summary,
            tasks=tasks,
            task_events=task_events,
            tool_calls=tool_calls,
            llm_calls=llm_calls,
            sandbox_executions=sandbox_executions,
            approval_requests=approval_requests,
            timeline=timeline,
        )

    def _build_timeline(
        self,
        *,
        task_events: list[dict[str, Any]],
        tool_calls: list[dict[str, Any]],
        llm_calls: list[dict[str, Any]],
        sandbox_executions: list[dict[str, Any]],
        approval_requests: list[dict[str, Any]],
    ) -> list[TraceTimelineItem]:
        """把不同审计表统一投影到一条时间线。"""
        items: list[TraceTimelineItem] = []
        for event in task_events:
            items.append(
                TraceTimelineItem(
                    source="task_events",
                    event_type=event["event_type"],
                    step=event.get("step"),
                    message=event.get("message"),
                    created_at=event["created_at"],
                    payload=event.get("payload"),
                    ref_id=event.get("id"),
                )
            )
        for call in tool_calls:
            items.append(
                TraceTimelineItem(
                    source="tool_calls",
                    event_type="TOOL_CALL",
                    status=call.get("status"),
                    step=call.get("tool_name"),
                    message=call.get("error_message"),
                    created_at=call["created_at"],
                    payload={
                        "tool_id": str(call["tool_id"]),
                        "tool_name": call.get("tool_name"),
                        "duration_ms": call.get("duration_ms"),
                        "replay_of_tool_call_id": str(call["replay_of_tool_call_id"])
                        if call.get("replay_of_tool_call_id")
                        else None,
                    },
                    ref_id=call.get("id"),
                )
            )
        for call in llm_calls:
            items.append(
                TraceTimelineItem(
                    source="llm_calls",
                    event_type="LLM_CALL",
                    status=call.get("status"),
                    step=call.get("node_name"),
                    message=call.get("error_message"),
                    created_at=call["created_at"],
                    payload={
                        "provider": call.get("provider"),
                        "model": call.get("model"),
                        "duration_ms": call.get("duration_ms"),
                        "input_tokens": call.get("input_tokens"),
                        "output_tokens": call.get("output_tokens"),
                    },
                    ref_id=call.get("id"),
                )
            )
        for execution in sandbox_executions:
            items.append(
                TraceTimelineItem(
                    source="sandbox_executions",
                    event_type="SANDBOX_EXECUTION",
                    status=execution.get("status"),
                    step=execution.get("tool_name"),
                    message=execution.get("error_message"),
                    created_at=execution["created_at"],
                    payload={
                        "command": execution.get("command"),
                        "exit_code": execution.get("exit_code"),
                        "duration_ms": execution.get("duration_ms"),
                        "language": execution.get("language"),
                        "artifacts": execution.get("artifacts"),
                    },
                    ref_id=execution.get("id"),
                )
            )
        for approval in approval_requests:
            items.append(
                TraceTimelineItem(
                    source="approval_requests",
                    event_type="APPROVAL_REQUEST",
                    status=approval.get("status"),
                    step=approval.get("requested_action"),
                    message=approval.get("reason"),
                    created_at=approval["created_at"],
                    payload={
                        "tool_id": str(approval["tool_id"]) if approval.get("tool_id") else None,
                        "requested_by": approval.get("requested_by"),
                        "decided_by": approval.get("decided_by"),
                        "approval_scope": approval.get("approval_scope"),
                        "expires_at": approval.get("expires_at").isoformat()
                        if approval.get("expires_at")
                        else None,
                    },
                    ref_id=approval.get("id"),
                )
            )
        return sorted(items, key=lambda item: item.created_at)

    def _build_summary(
        self,
        *,
        trace_id: UUID,
        tasks: list[dict[str, Any]],
        task_events: list[dict[str, Any]],
        tool_calls: list[dict[str, Any]],
        llm_calls: list[dict[str, Any]],
        sandbox_executions: list[dict[str, Any]],
        approval_requests: list[dict[str, Any]],
    ) -> TraceSummary:
        """生成 Trace 摘要和错误类型统计。"""
        error_types: dict[str, int] = {}
        for item in [*task_events, *tool_calls, *llm_calls, *sandbox_executions]:
            error_type = self._error_type(item)
            if error_type:
                error_types[error_type] = error_types.get(error_type, 0) + 1

        first_task = tasks[0] if tasks else None
        last_task = tasks[-1] if tasks else None
        return TraceSummary(
            trace_id=trace_id,
            task_count=len(tasks),
            event_count=len(task_events),
            tool_call_count=len(tool_calls),
            llm_call_count=len(llm_calls),
            sandbox_execution_count=len(sandbox_executions),
            approval_count=len(approval_requests),
            final_status=last_task.get("status") if last_task else None,
            total_duration_ms=self._duration_ms(first_task, last_task),
            error_count=sum(error_types.values()),
            error_types=error_types,
        )

    def _error_type(self, item: dict[str, Any]) -> str | None:
        """把不同表中的失败状态映射成标准错误类型。"""
        status = str(item.get("status") or "").upper()
        event_type = str(item.get("event_type") or "").upper()
        message = str(item.get("error_message") or item.get("message") or "").upper()
        if status in {"SUCCESS", "RUNNING", "QUEUED", "PLANNED", "APPROVED"}:
            return None
        if "NO_TOOL" in event_type or status == "NO_TOOL":
            return "NO_TOOL"
        if "DENIED" in event_type or status == "DENIED":
            return "PERMISSION_DENIED"
        if "TIMEOUT" in event_type or status == "TIMEOUT" or "TIMEOUT" in message:
            return "SANDBOX_TIMEOUT" if "SANDBOX" in event_type else "TASK_TIMEOUT"
        if "LLM" in event_type or item.get("node_name"):
            return "LLM_PROVIDER_FAILED" if status == "FAILED" else None
        if "TOOL" in event_type or item.get("tool_id"):
            return "TOOL_EXECUTION_FAILED" if status == "FAILED" else None
        if "FAILED" in event_type or status == "FAILED":
            return "TASK_FAILED"
        return None

    def _duration_ms(
        self,
        first_task: dict[str, Any] | None,
        last_task: dict[str, Any] | None,
    ) -> int | None:
        """根据任务开始和结束时间估算 trace 总耗时。"""
        if not first_task or not last_task:
            return None
        started_at: datetime | None = first_task.get("started_at") or first_task.get("created_at")
        finished_at: datetime | None = last_task.get("finished_at") or last_task.get("updated_at")
        if started_at is None or finished_at is None:
            return None
        return max(0, int((finished_at - started_at).total_seconds() * 1000))
