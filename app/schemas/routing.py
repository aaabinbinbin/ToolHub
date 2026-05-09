from __future__ import annotations

from uuid import UUID
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.llm import IntentResult
from app.schemas.permission import PermissionDecision, RunMode
from app.schemas.tool import ToolResponse


class ToolRouteRequest(BaseModel):
    """工具路由请求。

    可以直接传用户输入，也可以带上 IntentService 已经识别出的 intent 和建议工具类型。
    """

    user_input: str = Field(min_length=1)
    intent: str | None = None
    suggested_tool_type: str | None = None
    tool_input: dict[str, Any] = Field(default_factory=dict)


class ToolRouteCandidateDetail(BaseModel):
    """单个候选工具的路由诊断信息。"""

    tool: ToolResponse
    score: int
    schema_match: bool = True
    missing_fields: list[str] = Field(default_factory=list)
    rejection_reason: str | None = None


class ToolRouteResult(BaseModel):
    """ToolRouterService 的标准输出。

    candidates 保存前几个候选工具，方便调试为什么选中了某个工具。
    """

    selected_tool: ToolResponse | None
    score: int
    reason: str
    candidates: list[ToolResponse]
    candidate_details: list[ToolRouteCandidateDetail] = Field(default_factory=list)
    schema_match: bool = True
    missing_fields: list[str] = Field(default_factory=list)
    rejection_reason: str | None = None


class HarnessPlanRequest(BaseModel):
    """预演接口请求。

    这个接口只做 intent -> route -> permission，不执行工具。
    """

    user_input: str = Field(min_length=1)
    run_mode: RunMode = RunMode.SAFE_EXECUTE
    priority: str = "default"


class HarnessPlanResponse(BaseModel):
    """预演接口响应。

    返回完整的预演链路，方便前端或调试工具展示 intent、route 和 permission。
    """

    task_id: UUID
    run_id: UUID
    trace_id: UUID
    status: str
    intent: IntentResult
    route: ToolRouteResult
    permission: PermissionDecision | None
