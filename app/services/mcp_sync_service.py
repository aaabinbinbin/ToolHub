from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.common.exceptions import ConflictError
from app.schemas.tool import RiskLevel, ToolRegisterRequest, ToolResponse, ToolType
from app.services.tool_registry_service import ToolRegistryService
from app.tools.mcp_client import MCPClient


@dataclass(frozen=True)
class MCPSyncResult:
    name: str
    remote_tool_name: str
    tool_id: str
    status: str


class MCPSyncService:
    """把远端 MCP 工具同步到 ToolHub 的工具注册中心。"""

    def __init__(
        self,
        *,
        mcp_client: MCPClient | None = None,
        tool_registry_service: ToolRegistryService | None = None,
    ) -> None:
        self.mcp_client = mcp_client or MCPClient()
        self.tool_registry_service = tool_registry_service or ToolRegistryService()

    def sync_tools(
        self,
        *,
        mcp_url: str,
        transport: str | None = None,
        name_prefix: str = "mcp",
        tags: list[str] | None = None,
        risk_level: RiskLevel = RiskLevel.LOW,
        timeout_seconds: float = 30,
    ) -> list[MCPSyncResult]:
        remote_tools = self.mcp_client.list_tools(
            mcp_url=mcp_url,
            transport=transport,
            timeout_seconds=timeout_seconds,
        )
        results: list[MCPSyncResult] = []
        for remote_tool in remote_tools:
            request = self._build_register_request(
                remote_tool,
                mcp_url=mcp_url,
                transport=transport,
                name_prefix=name_prefix,
                tags=tags or [],
                risk_level=risk_level,
            )
            existing = self._find_existing_tool(request.name)
            if existing is not None:
                if existing.status.value != "ACTIVE":
                    existing = self.tool_registry_service.enable_tool(existing.id)
                results.append(
                    MCPSyncResult(
                        name=existing.name,
                        remote_tool_name=str(remote_tool["name"]),
                        tool_id=str(existing.id),
                        status="reused",
                    )
                )
                continue

            try:
                created = self.tool_registry_service.register_tool(request)
                results.append(
                    MCPSyncResult(
                        name=created.name,
                        remote_tool_name=str(remote_tool["name"]),
                        tool_id=str(created.id),
                        status="created",
                    )
                )
            except ConflictError:
                existing = self._find_existing_tool(request.name)
                if existing is None:
                    raise
                results.append(
                    MCPSyncResult(
                        name=existing.name,
                        remote_tool_name=str(remote_tool["name"]),
                        tool_id=str(existing.id),
                        status="reused_after_conflict",
                    )
                )
        return results

    def _build_register_request(
        self,
        remote_tool: dict[str, Any],
        *,
        mcp_url: str,
        transport: str | None,
        name_prefix: str,
        tags: list[str],
        risk_level: RiskLevel,
    ) -> ToolRegisterRequest:
        remote_tool_name = str(remote_tool["name"])
        tool_name = f"{name_prefix}-{remote_tool_name}".replace(" ", "-")
        return ToolRegisterRequest(
            name=tool_name,
            description=str(
                remote_tool.get("description")
                or remote_tool.get("title")
                or f"MCP tool synced from {mcp_url}: {remote_tool_name}"
            ),
            tool_type=ToolType.MCP,
            endpoint=remote_tool_name,
            mcp_url=mcp_url,
            transport=transport,
            version="1.0.0",
            input_schema=remote_tool.get("input_schema") or {"type": "object"},
            output_schema=remote_tool.get("output_schema"),
            tags=sorted({*tags, "mcp", "synced", remote_tool_name}),
            risk_level=risk_level,
        )

    def _find_existing_tool(self, name: str) -> ToolResponse | None:
        for tool in self.tool_registry_service.search_tools(name, include_disabled=True):
            if tool.name == name:
                return tool
        return None
