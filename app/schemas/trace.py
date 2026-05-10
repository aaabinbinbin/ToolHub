from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class TraceTimelineItem(BaseModel):
    """Trace 时间线中的统一事件项。"""

    source: str
    event_type: str
    status: str | None = None
    step: str | None = None
    message: str | None = None
    created_at: datetime
    payload: dict[str, Any] | None = None
    ref_id: UUID | None = None


class TraceSummary(BaseModel):
    """Trace 聚合摘要，方便 Console 顶部直接展示关键指标。"""

    trace_id: UUID
    task_count: int = 0
    event_count: int = 0
    tool_call_count: int = 0
    llm_call_count: int = 0
    sandbox_execution_count: int = 0
    approval_count: int = 0
    final_status: str | None = None
    total_duration_ms: int | None = None
    error_count: int = 0
    error_types: dict[str, int] = Field(default_factory=dict)


class TraceResponse(BaseModel):
    """按 trace_id 聚合出的完整调试视图。"""

    trace_id: UUID
    summary: TraceSummary
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    task_events: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    llm_calls: list[dict[str, Any]] = Field(default_factory=list)
    sandbox_executions: list[dict[str, Any]] = Field(default_factory=list)
    approval_requests: list[dict[str, Any]] = Field(default_factory=list)
    timeline: list[TraceTimelineItem] = Field(default_factory=list)
