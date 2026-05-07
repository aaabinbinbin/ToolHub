from __future__ import annotations

from typing import Any

from app.schemas.tool import ToolResponse
from app.tools.adapters.base import BaseToolAdapter


class MCPToolAdapter(BaseToolAdapter):
    """MCP 工具适配器。

    Day 4 先提供 calculator demo 能力；真实 MCP 协议调用后续接入 MCP client。
    """

    def call(self, tool: ToolResponse, tool_input: dict[str, Any]) -> dict[str, Any]:
        if "calculator" not in tool.name.lower():
            raise NotImplementedError("MCP adapter currently supports calculator demo only")

        expression = str(tool_input.get("expression") or tool_input.get("query") or "")
        if not expression:
            raise ValueError("calculator MCP demo requires expression")

        allowed_chars = set("0123456789+-*/(). %")
        if any(char not in allowed_chars for char in expression):
            raise ValueError("calculator expression contains unsupported characters")

        result = eval(expression, {"__builtins__": {}}, {})
        return {"expression": expression, "result": result}
