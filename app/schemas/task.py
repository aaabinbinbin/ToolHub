from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.permission import RunMode


class TaskRunConfig(BaseModel):
    """任务级运行控制参数，限制 Agent loop 的执行边界。"""

    max_steps: int = Field(default=3, ge=1, le=20)
    max_retries: int = Field(default=1, ge=0, le=5)
    timeout_seconds: int | None = Field(default=None, ge=1, le=3600)

    @field_validator("timeout_seconds")
    @classmethod
    def normalize_timeout(cls, value: int | None) -> int | None:
        """空值表示不启用任务级超时。"""
        return value


class TaskSubmitRequest(BaseModel):
    """提交后台 Agent 任务的请求。"""

    user_input: str = Field(min_length=1)
    run_mode: RunMode = RunMode.SAFE_EXECUTE
    priority: str = "default"
    user_id: str = "local-user"
    workspace_id: str = "default"
    run_config: TaskRunConfig = Field(default_factory=TaskRunConfig)


class TaskResponse(BaseModel):
    """任务状态响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    trace_id: UUID
    user_input: str
    run_mode: RunMode
    selected_tool_id: UUID | None
    user_id: str
    workspace_id: str
    priority: str
    run_config: dict[str, Any]
    cancel_requested: bool = False
    cancel_reason: str | None = None
    cancelled_at: datetime | None = None
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


class TaskCancelRequest(BaseModel):
    """取消任务的请求。"""

    reason: str | None = None
    requested_by: str = "local-user"


class TaskCancelResponse(BaseModel):
    """取消任务后的状态响应。"""

    task_id: UUID
    status: str
    cancel_requested: bool
    cancel_reason: str | None


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
