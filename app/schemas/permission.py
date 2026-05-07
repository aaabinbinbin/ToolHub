from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel

from app.schemas.tool import RiskLevel, ToolResponse


class RunMode(StrEnum):
    """Agent Harness 支持的运行模式。

    PLAN_ONLY 只规划不执行；SAFE_EXECUTE 允许低中风险工具；FULL_EXECUTE 允许高风险工具继续检查并执行。
    """

    PLAN_ONLY = "PLAN_ONLY"
    SAFE_EXECUTE = "SAFE_EXECUTE"
    FULL_EXECUTE = "FULL_EXECUTE"


class PermissionDecisionType(StrEnum):
    """权限判断结果。

    ASK 预留给后续人工审批；Day 3 MVP 先使用 ALLOW / DENY。
    """

    ALLOW = "ALLOW"
    ASK = "ASK"
    DENY = "DENY"


class PermissionCheckRequest(BaseModel):
    """权限检查请求。

    用于单独验证某个工具在指定运行模式下是否允许执行。
    """

    tool_id: UUID
    run_mode: RunMode = RunMode.SAFE_EXECUTE


class PermissionDecision(BaseModel):
    """PermissionEngine 的标准输出。

    required_mode 表示如果当前模式不允许执行，至少需要切换到哪种模式。
    """

    allowed: bool
    decision: PermissionDecisionType
    reason: str
    run_mode: RunMode
    risk_level: RiskLevel
    required_mode: RunMode | None = None


class PermissionCheckResponse(BaseModel):
    """权限检查 API 响应。"""

    tool: ToolResponse
    permission: PermissionDecision
