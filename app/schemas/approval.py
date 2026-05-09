from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ApprovalStatus(StrEnum):
    """审批请求状态。"""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ApprovalRequestResponse(BaseModel):
    """审批请求响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    run_id: UUID
    trace_id: UUID
    tool_id: UUID | None
    requested_action: str
    reason: str
    status: ApprovalStatus
    requested_by: str | None
    decided_by: str | None
    decision_reason: str | None
    created_at: datetime
    decided_at: datetime | None


class ApprovalDecisionRequest(BaseModel):
    """审批通过/拒绝请求。"""

    decided_by: str = "local-user"
    decision_reason: str | None = None


class ApprovalDecisionResponse(BaseModel):
    """审批动作响应。"""

    approval: ApprovalRequestResponse
    task: dict[str, Any]
