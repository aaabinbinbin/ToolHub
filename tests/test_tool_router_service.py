from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.schemas.tool import HealthStatus, RiskLevel, ToolResponse, ToolStatus, ToolType
from app.services.tool_router_service import ToolRouterService


class FakeToolRegistryService:
    def __init__(self, tools: list[ToolResponse]) -> None:
        self.tools = tools

    def search_tools(self, query: str, include_disabled: bool = False) -> list[ToolResponse]:
        return self.tools


def make_tool(name: str, description: str, tags: list[str]) -> ToolResponse:
    now = datetime.now(timezone.utc)
    return ToolResponse(
        id=uuid4(),
        name=name,
        description=description,
        tool_type=ToolType.CLI,
        endpoint="cli://git/status-short",
        mcp_url=None,
        transport=None,
        version="1.0.0",
        input_schema=None,
        output_schema=None,
        tags=tags,
        risk_level=RiskLevel.MEDIUM,
        status=ToolStatus.ACTIVE,
        health_status=HealthStatus.UNKNOWN,
        last_checked_at=None,
        created_at=now,
        updated_at=now,
    )


def test_router_returns_no_tool_for_weak_unrelated_match() -> None:
    service = ToolRouterService(
        FakeToolRegistryService(
            [make_tool("git-status", "查看 git 工作区状态", ["git", "status"])]
        )
    )

    route = service.select_tool(
        user_input="请处理一个没有工具标签匹配的抽象问题 xyz_no_tool_marker"
    )

    assert route.selected_tool is None
    assert route.score == 0


def test_router_selects_tool_with_intent_signal() -> None:
    service = ToolRouterService(
        FakeToolRegistryService(
            [make_tool("git-status", "查看 git 工作区状态", ["git", "status"])]
        )
    )

    route = service.select_tool(
        user_input="请查看 git status",
        intent="CLI_EXECUTION",
        suggested_tool_type="CLI",
    )

    assert route.selected_tool is not None
    assert route.score > 0
