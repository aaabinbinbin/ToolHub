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


def make_tool(
    name: str,
    description: str,
    tags: list[str],
    *,
    tool_type: ToolType = ToolType.CLI,
    input_schema: dict | None = None,
    quality_score: float | None = None,
    success_rate: float | None = None,
    avg_duration_ms: int | None = None,
) -> ToolResponse:
    now = datetime.now(timezone.utc)
    return ToolResponse(
        id=uuid4(),
        name=name,
        description=description,
        tool_type=tool_type,
        endpoint="cli://git/status-short",
        mcp_url=None,
        transport=None,
        version="1.0.0",
        input_schema=input_schema,
        output_schema=None,
        tags=tags,
        risk_level=RiskLevel.MEDIUM,
        status=ToolStatus.ACTIVE,
        health_status=HealthStatus.UNKNOWN,
        last_checked_at=None,
        quality_score=quality_score,
        success_rate=success_rate,
        avg_duration_ms=avg_duration_ms,
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


def test_router_rejects_candidate_when_schema_required_field_is_missing() -> None:
    service = ToolRouterService(
        FakeToolRegistryService(
            [
                make_tool(
                    "calculator",
                    "计算数学表达式",
                    ["calculator", "math"],
                    tool_type=ToolType.MCP,
                    input_schema={
                        "type": "object",
                        "required": ["expression"],
                        "properties": {"expression": {"type": "string"}},
                        "additionalProperties": False,
                    },
                )
            ]
        )
    )

    route = service.select_tool(
        user_input="请计算一个表达式",
        intent="CALCULATE",
        suggested_tool_type="MCP",
        tool_input={},
    )

    assert route.selected_tool is None
    assert route.schema_match is False
    assert route.missing_fields == ["expression"]
    assert route.candidate_details[0].schema_match is False


def test_router_prefers_schema_matching_candidate_over_higher_invalid_candidate() -> None:
    invalid_tool = make_tool(
        "calculator-pro",
        "计算数学表达式",
        ["calculator", "math"],
        tool_type=ToolType.MCP,
        input_schema={
            "type": "object",
            "required": ["expression"],
            "properties": {"expression": {"type": "string"}},
            "additionalProperties": False,
        },
    )
    valid_tool = make_tool(
        "calculator-basic",
        "计算数学表达式",
        ["calculator", "math"],
        tool_type=ToolType.MCP,
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "additionalProperties": False,
        },
    )
    service = ToolRouterService(FakeToolRegistryService([invalid_tool, valid_tool]))

    route = service.select_tool(
        user_input="请使用 calculator-pro 计算",
        intent="CALCULATE",
        suggested_tool_type="MCP",
        tool_input={"query": "1 + 2"},
    )

    assert route.selected_tool is not None
    assert route.selected_tool.name == "calculator-basic"
    assert route.schema_match is True
    assert route.candidate_details[0].tool.name == "calculator-basic"


def test_router_returns_top_k_candidate_score_breakdown() -> None:
    service = ToolRouterService(
        FakeToolRegistryService(
            [
                make_tool(
                    "git-status-fast",
                    "查看 git 工作区状态",
                    ["git", "status"],
                    quality_score=0.9,
                    success_rate=1.0,
                    avg_duration_ms=200,
                ),
                make_tool(
                    "git-status-slow",
                    "查看 git 工作区状态",
                    ["git", "status"],
                    quality_score=0.2,
                    success_rate=0.5,
                    avg_duration_ms=8000,
                ),
            ]
        )
    )

    route = service.select_tool(
        user_input="请查看 git status",
        intent="CLI_EXECUTION",
        suggested_tool_type="CLI",
        top_k=2,
    )

    assert route.selected_tool is not None
    assert route.selected_tool.name == "git-status-fast"
    assert len(route.candidate_details) == 2
    assert route.candidate_details[0].rank == 1
    assert "quality" in route.candidate_details[0].score_breakdown
    assert route.candidate_details[0].score > route.candidate_details[1].score


class FakeRerankService:
    def rerank(self, **kwargs):
        from app.schemas.routing import ToolRouteRerankMetadata

        candidates = kwargs["candidates"]
        for candidate in candidates:
            if candidate.tool.name == "git-status-second":
                candidate.score += 20
                candidate.score_breakdown["llm_rerank"] = 20
                candidate.llm_rerank_rank = 1
                candidate.llm_rerank_reason = "更符合用户措辞"
        return ToolRouteRerankMetadata(
            enabled=True,
            applied=True,
            fallback_used=False,
            reason="fake rerank applied",
        )


def test_router_applies_llm_rerank_within_top_k_candidates() -> None:
    service = ToolRouterService(
        FakeToolRegistryService(
            [
                make_tool("git-status-first", "查看 git 工作区状态", ["git", "status"]),
                make_tool("git-status-second", "查看 git 工作区状态", ["git", "status"]),
            ]
        ),
        rerank_service=FakeRerankService(),
    )

    route = service.select_tool(
        user_input="请查看 git status",
        intent="CLI_EXECUTION",
        suggested_tool_type="CLI",
        top_k=2,
        enable_llm_rerank=True,
    )

    assert route.selected_tool is not None
    assert route.selected_tool.name == "git-status-second"
    assert route.rerank.applied is True
    assert route.candidate_details[0].llm_rerank_rank == 1
