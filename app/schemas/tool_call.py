from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ToolCallRequest(BaseModel):
    """工具调用请求。

    Day 4 直接按 tool_id 调用工具，用于验证四类 Adapter 是否可用。
    后续 AgentHarness 会在权限通过后自动构造这个调用。
    """

    tool_id: UUID
    tool_input: dict[str, Any] = Field(default_factory=dict)
    task_id: UUID | None = None
    run_id: UUID | None = None
    trace_id: UUID | None = None


class ToolCallResult(BaseModel):
    """统一工具调用结果。"""

    success: bool
    status: str
    tool_id: UUID
    tool_name: str
    tool_type: str
    input: dict[str, Any]
    output: dict[str, Any] | None = None
    error_message: str | None = None
    duration_ms: int
    run_id: UUID
    trace_id: UUID
    task_id: UUID | None = None
