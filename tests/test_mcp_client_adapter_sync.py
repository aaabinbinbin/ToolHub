from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.schemas.tool import HealthStatus, RiskLevel, ToolResponse, ToolStatus, ToolType
from app.services.mcp_sync_service import MCPSyncService
from app.tools.adapters.mcp_adapter import MCPToolAdapter
from app.tools.mcp_client import MCPClient


def make_mcp_tool(*, endpoint: str | None = "remote_sum") -> ToolResponse:
    now = datetime.now(timezone.utc)
    return ToolResponse(
        id=uuid4(),
        name="toolhub-demo-mcp-remote-sum",
        description="Remote MCP sum tool",
        tool_type=ToolType.MCP,
        endpoint=endpoint,
        mcp_url="mock://calculator",
        transport="mock",
        version="1.0.0",
        input_schema={"type": "object"},
        output_schema=None,
        tags=["mcp"],
        risk_level=RiskLevel.LOW,
        status=ToolStatus.ACTIVE,
        health_status=HealthStatus.UNKNOWN,
        last_checked_at=None,
        created_at=now,
        updated_at=now,
    )


class FakeMCPClient:
    def __init__(self) -> None:
        self.calls = []

    def call_tool(self, **kwargs):
        self.calls.append(kwargs)
        return {"ok": True, "kwargs": kwargs}

    def list_tools(self, **kwargs):
        return [
            {
                "name": "remote_sum",
                "description": "Add numbers",
                "input_schema": {
                    "type": "object",
                    "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                    "required": ["a", "b"],
                },
                "output_schema": {"type": "object"},
            }
        ]


class FakeToolRegistryService:
    def __init__(self) -> None:
        self.created = []

    def search_tools(self, query: str, include_disabled: bool = False):
        return []

    def register_tool(self, request):
        self.created.append(request)
        now = datetime.now(timezone.utc)
        return ToolResponse(
            id=uuid4(),
            name=request.name,
            description=request.description,
            tool_type=request.tool_type,
            endpoint=request.endpoint,
            mcp_url=request.mcp_url,
            transport=request.transport,
            version=request.version,
            input_schema=request.input_schema,
            output_schema=request.output_schema,
            tags=request.tags,
            risk_level=request.risk_level,
            status=ToolStatus.ACTIVE,
            health_status=HealthStatus.UNKNOWN,
            last_checked_at=None,
            created_at=now,
            updated_at=now,
        )


def test_mcp_client_mock_calculator_call() -> None:
    result = MCPClient().call_tool(
        mcp_url="mock://calculator",
        transport="mock",
        tool_name="calculator",
        arguments={"expression": "1 + 2 * 3"},
    )

    assert result["structured_content"]["result"] == 7
    assert result["is_error"] is False


def test_mcp_adapter_calls_remote_tool_name_from_endpoint() -> None:
    client = FakeMCPClient()
    adapter = MCPToolAdapter(client=client)  # type: ignore[arg-type]

    result = adapter.call(
        make_mcp_tool(endpoint="remote_sum"),
        {"a": 1, "b": 2, "timeout": 5},
    )

    assert result["ok"] is True
    assert client.calls[0]["tool_name"] == "remote_sum"
    assert client.calls[0]["arguments"] == {"a": 1, "b": 2}
    assert client.calls[0]["timeout_seconds"] == 5


def test_mcp_sync_service_registers_remote_tools() -> None:
    registry = FakeToolRegistryService()
    service = MCPSyncService(
        mcp_client=FakeMCPClient(),  # type: ignore[arg-type]
        tool_registry_service=registry,  # type: ignore[arg-type]
    )

    results = service.sync_tools(
        mcp_url="mock://calculator",
        transport="mock",
        name_prefix="demo-mcp",
        tags=["demo"],
    )

    assert len(results) == 1
    assert results[0].name == "demo-mcp-remote_sum"
    assert registry.created[0].endpoint == "remote_sum"
    assert registry.created[0].tool_type == ToolType.MCP
    assert "synced" in registry.created[0].tags
