from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


SummaryType = Literal["SUCCESS", "FAILED", "DENIED", "NO_TOOL"]


class ResultSummary(BaseModel):
    """工具执行结果的最终用户可读总结。"""

    final_answer: str
    summary_type: SummaryType
    next_action: str | None = None
    fallback_used: bool = False
    raw_response: str | None = None

