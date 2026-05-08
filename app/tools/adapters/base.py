from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from app.schemas.tool import ToolResponse


class ToolAdapterExecutionError(RuntimeError):
    """工具适配器执行失败，但仍保留结构化输出用于审计。"""

    def __init__(self, message: str, output: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.output = output


class BaseToolAdapter(ABC):
    """所有工具适配器的统一接口。"""

    @abstractmethod
    def call(
        self,
        tool: ToolResponse,
        tool_input: dict[str, Any],
        *,
        task_id: UUID | None = None,
        run_id: UUID | None = None,
        trace_id: UUID | None = None,
    ) -> dict[str, Any]:
        """调用工具并返回 JSON 兼容结果。"""
