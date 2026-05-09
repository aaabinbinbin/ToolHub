from __future__ import annotations

from typing import Any
from uuid import UUID

from app.schemas.tool import ToolResponse
from app.tools.adapters.base import BaseToolAdapter
from app.tools.mcp_client import MCPClient


class MCPToolAdapter(BaseToolAdapter):
    """MCP 工具适配器，通过 MCPClient 调用真实 MCP 服务上的工具。"""

    def __init__(self, client: MCPClient | None = None) -> None:
        self.client = client or MCPClient()

    def call(
        self,
        tool: ToolResponse,
        tool_input: dict[str, Any],
        *,
        task_id: UUID | None = None,
        run_id: UUID | None = None,
        trace_id: UUID | None = None,
    ) -> dict[str, Any]:
        if not tool.mcp_url:
            raise ValueError("MCP tool requires mcp_url")

        remote_tool_name = str(
            tool_input.get("_mcp_tool_name")
            or tool_input.get("tool_name")
            or tool.endpoint
            or tool.name
        )
        timeout_seconds = float(tool_input.get("timeout", 30))
        arguments = self._arguments_from_tool_input(tool_input)

        return self.client.call_tool(
            mcp_url=tool.mcp_url,
            transport=tool.transport,
            tool_name=remote_tool_name,
            arguments=arguments,
            timeout_seconds=timeout_seconds,
        )

    def _arguments_from_tool_input(self, tool_input: dict[str, Any]) -> dict[str, Any]:
        explicit_arguments = tool_input.get("arguments")
        if isinstance(explicit_arguments, dict):
            return explicit_arguments

        control_keys = {"_mcp_tool_name", "tool_name", "arguments", "timeout"}
        return {
            key: value
            for key, value in tool_input.items()
            if key not in control_keys
        }
