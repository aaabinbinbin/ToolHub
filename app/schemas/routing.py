from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.llm import IntentResult
from app.schemas.permission import PermissionDecision, RunMode
from app.schemas.tool import ToolResponse


class ToolRouteRequest(BaseModel):
    """工具路由请求。

    可以直接传用户输入，也可以带上 IntentService 已识别出的 intent 和建议工具类型。
    """

    user_input: str = Field(min_length=1)
    intent: str | None = None
    suggested_tool_type: str | None = None
    tool_input: dict[str, Any] = Field(default_factory=dict)
    top_k: int = Field(default=5, ge=1, le=20)
    enable_llm_rerank: bool = False
    task_id: UUID | None = None
    run_id: UUID | None = None
    trace_id: UUID | None = None


class ToolRouteCandidateDetail(BaseModel):
    """单个候选工具的路由诊断信息。"""

    tool: ToolResponse
    score: float
    rank: int | None = None
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    matched_signals: list[str] = Field(default_factory=list)
    schema_match: bool = True
    schema_score: float = 0
    missing_fields: list[str] = Field(default_factory=list)
    rejection_reason: str | None = None
    llm_rerank_rank: int | None = None
    llm_rerank_reason: str | None = None


class ToolRouteRerankMetadata(BaseModel):
    """LLM rerank 的审计元数据。"""

    enabled: bool = False
    applied: bool = False
    fallback_used: bool = True
    reason: str | None = None
    raw_response: str | None = None


class ToolRouteResult(BaseModel):
    """ToolRouterService 的标准输出。

    candidates 保存 top-k 候选工具；candidate_details 保存每个候选的分项打分和拒绝原因。
    """

    selected_tool: ToolResponse | None
    score: float
    reason: str
    candidates: list[ToolResponse]
    candidate_details: list[ToolRouteCandidateDetail] = Field(default_factory=list)
    schema_match: bool = True
    missing_fields: list[str] = Field(default_factory=list)
    rejection_reason: str | None = None
    top_k: int = 5
    rerank: ToolRouteRerankMetadata = Field(default_factory=ToolRouteRerankMetadata)


class HarnessPlanRequest(BaseModel):
    """预演接口请求。

    这个接口只做 intent -> route -> permission，不执行工具。
    """

    user_input: str = Field(min_length=1)
    run_mode: RunMode = RunMode.SAFE_EXECUTE
    priority: str = "default"
    user_id: str = "local-user"
    workspace_id: str = "default"


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
