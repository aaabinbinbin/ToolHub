from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.permission import RunMode


class TaskSubmitRequest(BaseModel):
    """提交后台 Agent 任务的请求。"""

    user_input: str = Field(min_length=1)
    run_mode: RunMode = RunMode.SAFE_EXECUTE
    priority: str = "default"


class TaskResponse(BaseModel):
    """任务状态响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    trace_id: UUID
    user_input: str
    run_mode: RunMode
    selected_tool_id: UUID | None
    priority: str
    status: str
    current_step: str | None
    retry_count: int
    max_retries: int
    error_message: str | None
    result: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class TaskSubmitResponse(BaseModel):
    """提交任务后的立即响应。"""

    task_id: UUID
    run_id: UUID
    trace_id: UUID
    status: str


class TaskEventResponse(BaseModel):
    """任务事件响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    run_id: UUID
    trace_id: UUID
    event_type: str
    step: str | None
    message: str | None
    payload: dict[str, Any] | None
    created_at: datetime

