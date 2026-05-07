from __future__ import annotations

import time
from typing import Any
from uuid import UUID, uuid4

from app.repositories.db import get_connection
from app.repositories.tool_call_repository import ToolCallRepository
from app.schemas.tool import ToolResponse, ToolType
from app.schemas.tool_call import ToolCallResult
from app.tools.adapters.base import BaseToolAdapter
from app.tools.adapters.cli_adapter import CLIToolAdapter
from app.tools.adapters.http_adapter import HTTPToolAdapter
from app.tools.adapters.mcp_adapter import MCPToolAdapter
from app.tools.adapters.sandbox_adapter import SandboxToolAdapter


class ToolAdapterDispatcher:
    """根据 tool_type 分发到对应 ToolAdapter，并统一记录 tool_calls。"""

    def __init__(self) -> None:
        self.adapters: dict[ToolType, BaseToolAdapter] = {
            ToolType.MCP: MCPToolAdapter(),
            ToolType.HTTP: HTTPToolAdapter(),
            ToolType.CLI: CLIToolAdapter(),
            ToolType.SANDBOX: SandboxToolAdapter(),
        }

    def dispatch(
        self,
        *,
        tool: ToolResponse,
        tool_input: dict[str, Any],
        task_id: UUID | None = None,
        run_id: UUID | None = None,
        trace_id: UUID | None = None,
    ) -> ToolCallResult:
        """执行工具调用并写入 tool_calls。"""
        run_id = run_id or uuid4()
        trace_id = trace_id or uuid4()
        started_at = time.perf_counter()
        adapter = self.adapters[tool.tool_type]

        try:
            output = adapter.call(tool, tool_input)
            result = ToolCallResult(
                success=True,
                status="SUCCESS",
                tool_id=tool.id,
                tool_name=tool.name,
                tool_type=tool.tool_type.value,
                input=tool_input,
                output=output,
                duration_ms=int((time.perf_counter() - started_at) * 1000),
                run_id=run_id,
                trace_id=trace_id,
                task_id=task_id,
            )
        except Exception as exc:
            result = ToolCallResult(
                success=False,
                status="FAILED",
                tool_id=tool.id,
                tool_name=tool.name,
                tool_type=tool.tool_type.value,
                input=tool_input,
                error_message=f"{exc.__class__.__name__}: {exc}",
                duration_ms=int((time.perf_counter() - started_at) * 1000),
                run_id=run_id,
                trace_id=trace_id,
                task_id=task_id,
            )

        with get_connection() as connection:
            ToolCallRepository(connection).create(result)
        return result
