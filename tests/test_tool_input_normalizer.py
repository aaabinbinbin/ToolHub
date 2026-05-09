from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.harness.tool_input_normalizer import ToolInputNormalizer
from app.schemas.tool import HealthStatus, RiskLevel, ToolResponse, ToolStatus, ToolType


def make_tool(tool_type: ToolType, endpoint: str | None = None) -> ToolResponse:
    now = datetime.now(timezone.utc)
    return ToolResponse(
        id=uuid4(),
        name="test-tool",
        description="test tool",
        tool_type=tool_type,
        endpoint=endpoint,
        mcp_url="mock://calculator" if tool_type == ToolType.MCP else None,
        transport=None,
        version="1.0.0",
        input_schema=None,
        output_schema=None,
        tags=[],
        risk_level=RiskLevel.LOW,
        status=ToolStatus.ACTIVE,
        health_status=HealthStatus.UNKNOWN,
        last_checked_at=None,
        created_at=now,
        updated_at=now,
    )


def test_normalizer_adds_cli_rule_id_from_endpoint() -> None:
    normalized = ToolInputNormalizer().normalize(
        tool=make_tool(ToolType.CLI, "cli://git/status-short"),
        tool_input={},
    )

    assert normalized["rule_id"] == "cli://git/status-short"


def test_normalizer_promotes_sandbox_code_hint() -> None:
    normalized = ToolInputNormalizer().normalize(
        tool=make_tool(ToolType.SANDBOX, "python"),
        tool_input={"code_hint": "print(1)"},
    )

    assert normalized["code"] == "print(1)"


def test_normalizer_promotes_mcp_value_to_expression() -> None:
    normalized = ToolInputNormalizer().normalize(
        tool=make_tool(ToolType.MCP),
        tool_input={"value": "1 + 2"},
    )

    assert normalized["expression"] == "1 + 2"

