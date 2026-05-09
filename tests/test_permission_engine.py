from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.schemas.permission import PermissionDecisionType, RunMode
from app.schemas.tool import HealthStatus, RiskLevel, ToolResponse, ToolStatus, ToolType
from app.security.permission_engine import PermissionEngine


def make_tool(risk_level: RiskLevel) -> ToolResponse:
    now = datetime.now(timezone.utc)
    return ToolResponse(
        id=uuid4(),
        name="danger-python",
        description="高风险 Python 沙箱工具",
        tool_type=ToolType.SANDBOX,
        endpoint="python",
        mcp_url=None,
        transport=None,
        version="1.0.0",
        input_schema=None,
        output_schema=None,
        tags=["sandbox"],
        risk_level=risk_level,
        status=ToolStatus.ACTIVE,
        health_status=HealthStatus.UNKNOWN,
        last_checked_at=None,
        created_at=now,
        updated_at=now,
    )


def test_high_risk_tool_requires_approval_in_safe_execute() -> None:
    decision = PermissionEngine().check(
        make_tool(RiskLevel.HIGH),
        RunMode.SAFE_EXECUTE,
    )

    assert decision.allowed is False
    assert decision.decision == PermissionDecisionType.ASK
    assert decision.required_mode == RunMode.FULL_EXECUTE


def test_high_risk_tool_allowed_in_full_execute() -> None:
    decision = PermissionEngine().check(
        make_tool(RiskLevel.HIGH),
        RunMode.FULL_EXECUTE,
    )

    assert decision.allowed is True
    assert decision.decision == PermissionDecisionType.ALLOW
