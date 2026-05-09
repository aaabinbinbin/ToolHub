from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import anyio
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamablehttp_client


class MCPClientError(RuntimeError):
    """远端 MCP 服务无法连接或调用失败时抛出。"""


class MCPClient:
    """官方 MCP Python SDK 的同步封装。

    ToolHub 现有 service / adapter 仍以同步接口为主，而 MCP SDK 的 client API
    是异步接口。这里把不同 transport 的异步细节集中封装起来，让上层通过
    简单的同步方法完成 MCP 工具列表查询和工具调用。
    """

    DEFAULT_TIMEOUT_SECONDS = 30.0

    def list_tools(
        self,
        *,
        mcp_url: str,
        transport: str | None = None,
        timeout_seconds: float | None = None,
    ) -> list[dict[str, Any]]:
        return anyio.run(
            self._list_tools_async,
            mcp_url,
            self._normalize_transport(transport, mcp_url),
            timeout_seconds or self.DEFAULT_TIMEOUT_SECONDS,
        )

    def call_tool(
        self,
        *,
        mcp_url: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        transport: str | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        normalized_transport = self._normalize_transport(transport, mcp_url)
        if normalized_transport == "mock":
            return self._call_mock_tool(mcp_url, tool_name, arguments or {})

        return anyio.run(
            self._call_tool_async,
            mcp_url,
            normalized_transport,
            tool_name,
            arguments or {},
            timeout_seconds or self.DEFAULT_TIMEOUT_SECONDS,
        )

    async def _list_tools_async(
        self,
        mcp_url: str,
        transport: str,
        timeout_seconds: float,
    ) -> list[dict[str, Any]]:
        if transport == "mock":
            return self._list_mock_tools(mcp_url)

        async with self._session(mcp_url, transport, timeout_seconds) as session:
            result = await session.list_tools()
            return [
                {
                    "name": tool.name,
                    "title": tool.title,
                    "description": tool.description,
                    "input_schema": tool.inputSchema,
                    "output_schema": tool.outputSchema,
                    "annotations": self._dump_model(tool.annotations),
                    "meta": self._dump_model(tool.meta),
                }
                for tool in result.tools
            ]

    async def _call_tool_async(
        self,
        mcp_url: str,
        transport: str,
        tool_name: str,
        arguments: dict[str, Any],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        async with self._session(mcp_url, transport, timeout_seconds) as session:
            result = await session.call_tool(
                tool_name,
                arguments=arguments,
                read_timeout_seconds=timedelta(seconds=timeout_seconds),
            )
            return self._format_call_result(tool_name, arguments, result)

    @asynccontextmanager
    async def _session(
        self,
        mcp_url: str,
        transport: str,
        timeout_seconds: float,
    ):
        try:
            if transport == "stdio":
                params = self._stdio_params(mcp_url)
                async with stdio_client(params) as (read_stream, write_stream):
                    async with ClientSession(
                        read_stream,
                        write_stream,
                        read_timeout_seconds=timedelta(seconds=timeout_seconds),
                    ) as session:
                        await session.initialize()
                        yield session
                return

            if transport == "sse":
                async with sse_client(mcp_url, timeout=timeout_seconds) as (
                    read_stream,
                    write_stream,
                ):
                    async with ClientSession(
                        read_stream,
                        write_stream,
                        read_timeout_seconds=timedelta(seconds=timeout_seconds),
                    ) as session:
                        await session.initialize()
                        yield session
                return

            if transport in {"streamable-http", "http"}:
                async with streamablehttp_client(
                    mcp_url,
                    timeout=timeout_seconds,
                    sse_read_timeout=timeout_seconds,
                ) as (read_stream, write_stream, _get_session_id):
                    async with ClientSession(
                        read_stream,
                        write_stream,
                        read_timeout_seconds=timedelta(seconds=timeout_seconds),
                    ) as session:
                        await session.initialize()
                        yield session
                return

            raise ValueError(f"Unsupported MCP transport: {transport}")
        except Exception as exc:
            if isinstance(exc, ValueError):
                raise
            raise MCPClientError(f"MCP {transport} call failed: {exc}") from exc

    def _normalize_transport(self, transport: str | None, mcp_url: str) -> str:
        raw_transport = (transport or "").strip().lower()
        if raw_transport in {"streamable_http", "streamable-http"}:
            return "streamable-http"
        if raw_transport in {"http", "sse", "stdio", "mock"}:
            return raw_transport

        parsed = urlparse(mcp_url)
        if parsed.scheme == "mock":
            return "mock"
        if parsed.scheme == "stdio":
            return "stdio"
        if parsed.path.endswith("/sse"):
            return "sse"
        return "streamable-http"

    def _stdio_params(self, mcp_url: str) -> StdioServerParameters:
        parsed = urlparse(mcp_url)
        if parsed.scheme != "stdio":
            raise ValueError("stdio MCP transport requires mcp_url starting with stdio://")

        command = unquote(parsed.netloc or parsed.path.lstrip("/"))
        if not command:
            raise ValueError("stdio MCP URL must include a command")

        query = parse_qs(parsed.query)
        args = [unquote(value) for value in query.get("arg", []) + query.get("args", [])]
        cwd = query.get("cwd", [None])[0]
        return StdioServerParameters(command=command, args=args, cwd=cwd)

    def _list_mock_tools(self, mcp_url: str) -> list[dict[str, Any]]:
        if mcp_url != "mock://calculator":
            raise ValueError(f"Unsupported mock MCP server: {mcp_url}")
        return [
            {
                "name": "calculator",
                "title": "Calculator",
                "description": "Evaluate simple arithmetic expressions.",
                "input_schema": {
                    "type": "object",
                    "properties": {"expression": {"type": "string"}},
                    "required": ["expression"],
                    "additionalProperties": False,
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "expression": {"type": "string"},
                        "result": {"type": ["number", "integer"]},
                    },
                    "required": ["expression", "result"],
                },
                "annotations": None,
                "meta": {"mock": True},
            }
        ]

    def _call_mock_tool(
        self,
        mcp_url: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        if mcp_url != "mock://calculator" or tool_name not in {
            "calculator",
            "toolhub-demo-mcp-calculator",
        }:
            raise ValueError(f"Unsupported mock MCP tool: {tool_name}")

        expression = str(arguments.get("expression") or arguments.get("query") or "")
        if not expression:
            raise ValueError("calculator MCP demo requires expression")

        allowed_chars = set("0123456789+-*/(). %")
        if any(char not in allowed_chars for char in expression):
            raise ValueError("calculator expression contains unsupported characters")

        result = eval(expression, {"__builtins__": {}}, {})
        return {
            "tool_name": "calculator",
            "arguments": {"expression": expression},
            "structured_content": {"expression": expression, "result": result},
            "content": [{"type": "text", "text": str(result)}],
            "is_error": False,
            "mock": True,
        }

    def _format_call_result(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: Any,
    ) -> dict[str, Any]:
        payload = result.model_dump(mode="json", by_alias=True)
        return {
            "tool_name": tool_name,
            "arguments": arguments,
            "structured_content": payload.get("structuredContent"),
            "content": payload.get("content", []),
            "is_error": bool(payload.get("isError", False)),
            "meta": payload.get("_meta"),
        }

    def _dump_model(self, value: Any) -> Any:
        if value is None:
            return None
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json", by_alias=True)
        return value
