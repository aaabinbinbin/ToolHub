from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class LLMResult(BaseModel):
    """LLMClient 返回给业务层的标准结果。"""

    text: str
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_ms: int | None = None
    status: str = "SUCCESS"
    error_message: str | None = None


class IntentRequest(BaseModel):
    """意图理解 API 的请求体。"""

    user_input: str = Field(min_length=1)
    run_mode: str = "SAFE_EXECUTE"


class IntentResult(BaseModel):
    """IntentService 输出的结构化意图。"""

    intent: str
    summary: str
    confidence: float
    risk_hint: str
    suggested_tool_type: str | None = None
    tool_input: dict[str, Any] = Field(default_factory=dict)
    fallback_used: bool = False
    raw_response: str | None = None
    run_id: UUID
    trace_id: UUID


class LLMCallRecord(BaseModel):
    """写入 `llm_calls` 表的标准记录。"""

    task_id: UUID | None = None
    run_id: UUID
    trace_id: UUID
    node_name: str
    provider: str
    model: str
    prompt: str
    response: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_ms: int | None = None
    estimated_cost: float | None = None
    status: str
    error_message: str | None = None
