from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.schemas.tool import ToolResponse


class BaseToolAdapter(ABC):
    """所有工具适配器的统一接口。"""

    @abstractmethod
    def call(self, tool: ToolResponse, tool_input: dict[str, Any]) -> dict[str, Any]:
        """调用工具并返回 JSON 兼容结果。"""
