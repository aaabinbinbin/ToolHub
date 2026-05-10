from __future__ import annotations

from uuid import UUID

from app.repositories.db import get_connection
from app.repositories.tool_permission_repository import ToolPermissionRepository
from app.schemas.permission import PermissionDecision, PermissionDecisionType, RunMode
from app.schemas.tool import RiskLevel, ToolResponse


class PermissionEngine:
    """根据 run_mode 和工具风险等级做权限判断。

    当前只实现 `risk_level + run_mode` 的基础策略。
    后续可以继续接入 command policy、tool_permissions 表和人工审批。
    """

    def check(
        self,
        tool: ToolResponse,
        run_mode: RunMode,
        *,
        user_id: str | None = None,
        workspace_id: str | None = None,
        action: str = "execute",
    ) -> PermissionDecision:
        """检查当前运行模式是否允许调用指定工具。

        Args:
            tool: ToolRouter 选中的工具。
            run_mode: 当前任务运行模式。

        Returns:
            权限判断结果。后续 Harness 会根据 allowed 决定是否进入工具执行。
        """
        policy_decision = self._policy_decision(
            tool=tool,
            run_mode=run_mode,
            user_id=user_id,
            workspace_id=workspace_id,
            action=action,
        )
        if policy_decision is not None:
            return policy_decision

        if run_mode == RunMode.PLAN_ONLY:
            # PLAN_ONLY 只做规划和解释，不执行任何工具。
            return PermissionDecision(
                allowed=False,
                decision=PermissionDecisionType.DENY,
                reason="当前为 PLAN_ONLY 模式，只允许规划和路由，不允许执行工具。",
                run_mode=run_mode,
                risk_level=tool.risk_level,
                required_mode=RunMode.SAFE_EXECUTE
                if tool.risk_level != RiskLevel.HIGH
                else RunMode.FULL_EXECUTE,
            )

        if tool.risk_level == RiskLevel.HIGH and run_mode == RunMode.SAFE_EXECUTE:
            # SAFE_EXECUTE 下的 HIGH 风险工具进入人工审批，而不是直接执行。
            return PermissionDecision(
                allowed=False,
                decision=PermissionDecisionType.ASK,
                reason="工具风险等级为 HIGH，当前 run_mode 为 SAFE_EXECUTE，需要人工审批后才能执行。",
                run_mode=run_mode,
                risk_level=tool.risk_level,
                required_mode=RunMode.FULL_EXECUTE,
            )

        if tool.risk_level == RiskLevel.MEDIUM:
            # MEDIUM 风险工具暂时允许执行，但必须留下审计事件。
            return PermissionDecision(
                allowed=True,
                decision=PermissionDecisionType.ALLOW,
                reason="工具风险等级为 MEDIUM，当前模式允许执行，但需要记录审计事件。",
                run_mode=run_mode,
                risk_level=tool.risk_level,
            )

        return PermissionDecision(
            allowed=True,
            decision=PermissionDecisionType.ALLOW,
            reason="工具风险等级和运行模式允许执行。",
            run_mode=run_mode,
            risk_level=tool.risk_level,
        )

    def _policy_decision(
        self,
        *,
        tool: ToolResponse,
        run_mode: RunMode,
        user_id: str | None,
        workspace_id: str | None,
        action: str,
    ) -> PermissionDecision | None:
        """优先读取数据库中的多维 policy；读取失败时退回内置规则。"""
        try:
            with get_connection() as connection:
                policy = ToolPermissionRepository(connection).find_matching_policy(
                    tool_id=tool.id,
                    tool_type=tool.tool_type.value,
                    risk_level=tool.risk_level.value,
                    run_mode=run_mode.value,
                    user_id=user_id,
                    workspace_id=workspace_id,
                    action=action,
                )
        except Exception:
            return None
        if policy is None:
            return None

        decision = PermissionDecisionType(policy["effect"])
        required_mode = RunMode.FULL_EXECUTE if decision == PermissionDecisionType.ASK else None
        return PermissionDecision(
            allowed=decision == PermissionDecisionType.ALLOW,
            decision=decision,
            reason=f"命中权限策略：{policy.get('policy_name') or policy['id']}。",
            run_mode=run_mode,
            risk_level=tool.risk_level,
            required_mode=required_mode,
            policy_id=UUID(str(policy["id"])),
            policy_name=policy.get("policy_name"),
        )
