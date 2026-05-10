from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.schemas.permission import PermissionDecision, PermissionDecisionType, RunMode
from app.schemas.tool import HealthStatus, RiskLevel, ToolResponse, ToolStatus, ToolType
from app.security.permission_engine import PermissionEngine


def make_tool(risk: RiskLevel) -> ToolResponse:
    now = datetime.now(timezone.utc)
    return ToolResponse(
        id=uuid4(),
        name="test-tool",
        description="test",
        tool_type=ToolType.SANDBOX,
        endpoint="python",
        mcp_url=None,
        transport=None,
        version="1.0.0",
        input_schema=None,
        output_schema=None,
        tags=["test"],
        risk_level=risk,
        status=ToolStatus.ACTIVE,
        health_status=HealthStatus.UNKNOWN,
        last_checked_at=None,
        created_at=now,
        updated_at=now,
    )


def test_demo_flow_plan_only() -> None:
    """PLAN_ONLY 模式：只规划不执行。"""
    engine = PermissionEngine()
    decision = engine.check(
        make_tool(RiskLevel.LOW),
        RunMode.PLAN_ONLY,
    )
    assert decision.allowed is False
    assert decision.decision == PermissionDecisionType.DENY


def test_demo_flow_safe_execute_high_risk_asks() -> None:
    """SAFE_EXECUTE + HIGH 风险 → 进入审批。"""
    engine = PermissionEngine()
    decision = engine.check(
        make_tool(RiskLevel.HIGH),
        RunMode.SAFE_EXECUTE,
    )
    assert decision.decision == PermissionDecisionType.ASK
    assert decision.required_mode == RunMode.FULL_EXECUTE


def test_demo_flow_full_execute_allows_high() -> None:
    """FULL_EXECUTE + HIGH 风险 → 允许执行。"""
    engine = PermissionEngine()
    decision = engine.check(
        make_tool(RiskLevel.HIGH),
        RunMode.FULL_EXECUTE,
    )
    assert decision.allowed is True


def test_demo_flow_safe_execute_low_risk_allows() -> None:
    """SAFE_EXECUTE + LOW 风险 → 允许执行。"""
    engine = PermissionEngine()
    decision = engine.check(
        make_tool(RiskLevel.LOW),
        RunMode.SAFE_EXECUTE,
    )
    assert decision.allowed is True


def test_demo_flow_medium_risk_audited() -> None:
    """MEDIUM 风险工具允许执行但需要审计。"""
    engine = PermissionEngine()
    decision = engine.check(
        make_tool(RiskLevel.MEDIUM),
        RunMode.SAFE_EXECUTE,
    )
    assert decision.allowed is True
    assert "审计" in decision.reason


def test_demo_flow_complete_permission_matrix() -> None:
    """验证完整权限矩阵：PLAN_ONLY / SAFE_EXECUTE / FULL_EXECUTE × LOW / MEDIUM / HIGH。"""
    engine = PermissionEngine()

    cases = [
        # (run_mode, risk_level, expected_decision, expected_allowed)
        (RunMode.PLAN_ONLY, RiskLevel.LOW, PermissionDecisionType.DENY, False),
        (RunMode.PLAN_ONLY, RiskLevel.MEDIUM, PermissionDecisionType.DENY, False),
        (RunMode.PLAN_ONLY, RiskLevel.HIGH, PermissionDecisionType.DENY, False),
        (RunMode.SAFE_EXECUTE, RiskLevel.LOW, PermissionDecisionType.ALLOW, True),
        (RunMode.SAFE_EXECUTE, RiskLevel.MEDIUM, PermissionDecisionType.ALLOW, True),
        (RunMode.SAFE_EXECUTE, RiskLevel.HIGH, PermissionDecisionType.ASK, False),
        (RunMode.FULL_EXECUTE, RiskLevel.LOW, PermissionDecisionType.ALLOW, True),
        (RunMode.FULL_EXECUTE, RiskLevel.MEDIUM, PermissionDecisionType.ALLOW, True),
        (RunMode.FULL_EXECUTE, RiskLevel.HIGH, PermissionDecisionType.ALLOW, True),
    ]

    for run_mode, risk, exp_decision, exp_allowed in cases:
        decision = engine.check(make_tool(risk), run_mode)
        assert decision.decision == exp_decision, (
            f"{run_mode} × {risk}: expected {exp_decision}, got {decision.decision}"
        )
        assert decision.allowed == exp_allowed, (
            f"{run_mode} × {risk}: expected allowed={exp_allowed}, got {decision.allowed}"
        )
