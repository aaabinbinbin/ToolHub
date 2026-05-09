from __future__ import annotations

import re

from typing import Any

from app.schemas.routing import ToolRouteCandidateDetail, ToolRouteResult
from app.schemas.tool import HealthStatus, RiskLevel, ToolResponse
from app.services.schema_validation_service import SchemaValidationService
from app.services.tool_registry_service import ToolRegistryService


class ToolRouterService:
    """根据用户输入和 IntentService 输出选择最合适的工具。

    目前使用规则打分实现的路由，不引入 embedding 或 LLM rerank。
    后续可以在这个服务里扩展语义检索、历史成功率加权和模型重排。
    """

    STOP_TOKENS = {
        "请",
        "我",
        "一个",
        "一下",
        "工具",
        "处理",
        "问题",
        "需求",
        "任务",
        "帮我",
        "当前",
        "没有",
    }

    def __init__(
        self,
        tool_registry_service: ToolRegistryService | None = None,
        schema_validation_service: SchemaValidationService | None = None,
    ) -> None:
        """创建工具路由服务。

        Args:
            tool_registry_service: 工具注册中心服务。不传时使用默认实现。
        """
        self.tool_registry_service = tool_registry_service or ToolRegistryService()
        self.schema_validation_service = schema_validation_service or SchemaValidationService()

    def select_tool(
        self,
        *,
        user_input: str,
        intent: str | None = None,
        suggested_tool_type: str | None = None,
        tool_input: dict[str, Any] | None = None,
    ) -> ToolRouteResult:
        """从 ACTIVE 工具中选择一个得分最高的工具。

        Args:
            user_input: 用户原始输入。
            intent: IntentService 输出的标准化意图。
            suggested_tool_type: IntentService 建议的工具类型。
            tool_input: IntentService 输出的候选工具输入，用于 schema-aware 路由。

        Returns:
            工具路由结果，包含选中的工具、分数、候选工具和选择理由。
        """
        tools = self.tool_registry_service.search_tools("", include_disabled=False)
        if not tools:
            return ToolRouteResult(
                selected_tool=None,
                score=0,
                reason="没有可用的 ACTIVE 工具。",
                candidates=[],
                candidate_details=[],
            )

        candidate_details = [
            self._build_candidate_detail(
                tool,
                self._score_tool(tool, user_input, intent, suggested_tool_type),
                tool_input or {},
            )
            for tool in tools
        ]
        # schema 匹配优先，其次分数越高越优先；只取前几个候选返回，避免响应过大。
        candidate_details.sort(
            key=lambda item: (item.schema_match, item.score),
            reverse=True,
        )
        selected_candidate = candidate_details[0]
        selected_tool = selected_candidate.tool
        score = selected_candidate.score

        has_intent_signal = bool(suggested_tool_type or self._intent_to_tool_type(intent))
        if not selected_candidate.schema_match:
            return ToolRouteResult(
                selected_tool=None,
                score=0,
                reason=f"候选工具的输入 schema 不匹配：{selected_candidate.rejection_reason}",
                candidates=[item.tool for item in candidate_details[:5]],
                candidate_details=candidate_details[:5],
                schema_match=False,
                missing_fields=selected_candidate.missing_fields,
                rejection_reason=selected_candidate.rejection_reason,
            )

        if score <= 0 or (score < 2 and not has_intent_signal):
            return ToolRouteResult(
                selected_tool=None,
                score=0,
                reason="没有工具与当前用户输入或意图匹配。",
                candidates=[item.tool for item in candidate_details[:5]],
                candidate_details=candidate_details[:5],
            )

        return ToolRouteResult(
            selected_tool=selected_tool,
            score=score,
            reason=self._build_reason(
                selected_tool,
                score,
                intent,
                suggested_tool_type,
                schema_match=selected_candidate.schema_match,
            ),
            candidates=[item.tool for item in candidate_details[:5]],
            candidate_details=candidate_details[:5],
            schema_match=selected_candidate.schema_match,
            missing_fields=selected_candidate.missing_fields,
            rejection_reason=selected_candidate.rejection_reason,
        )

    def _build_candidate_detail(
        self,
        tool: ToolResponse,
        score: int,
        tool_input: dict[str, Any],
    ) -> ToolRouteCandidateDetail:
        """生成候选工具的分数和 schema 诊断信息。"""
        schema_result = self.schema_validation_service.validate_tool_input(
            tool.input_schema,
            tool_input,
        )
        rejection_reason = None
        if not schema_result.valid:
            detail_parts = []
            if schema_result.missing_fields:
                detail_parts.append(f"缺少字段 {schema_result.missing_fields}")
            if schema_result.errors:
                detail_parts.append("; ".join(schema_result.errors))
            rejection_reason = "；".join(detail_parts) or "输入不符合工具 schema"

        return ToolRouteCandidateDetail(
            tool=tool,
            score=score,
            schema_match=schema_result.valid,
            missing_fields=schema_result.missing_fields,
            rejection_reason=rejection_reason,
        )

    def _score_tool(
        self,
        tool: ToolResponse,
        user_input: str,
        intent: str | None,
        suggested_tool_type: str | None,
    ) -> int:
        """计算工具匹配分数。

        打分规则优先相信 IntentService 的 suggested_tool_type，其次考虑 intent 映射、
        工具名称、tags、description、健康状态和风险等级。
        """
        score = 0
        normalized_input = user_input.lower()
        tokens = self._tokens(normalized_input)

        if suggested_tool_type and tool.tool_type.value == suggested_tool_type.upper():
            score += 8

        intent_tool_type = self._intent_to_tool_type(intent)
        if intent_tool_type and tool.tool_type.value == intent_tool_type:
            score += 6

        if tool.name.lower() in normalized_input:
            score += 5

        for tag in tool.tags:
            if tag.lower() in tokens:
                score += 3

        description = tool.description.lower()
        for token in tokens:
            if token and token in description:
                score += 1

        if tool.health_status == HealthStatus.UP:
            score += 1
        elif tool.health_status == HealthStatus.DOWN:
            score -= 3

        if tool.risk_level == RiskLevel.HIGH and intent != "RUN_CODE":
            score -= 1

        return score

    def _intent_to_tool_type(self, intent: str | None) -> str | None:
        """把标准化 intent 映射到更适合的工具类型。"""
        mapping = {
            "RUN_CODE": "SANDBOX",
            "CLI_EXECUTION": "CLI",
            "HTTP_CALL": "HTTP",
            "CALCULATE": "MCP",
        }
        return mapping.get((intent or "").upper())

    def _tokens(self, text: str) -> set[str]:
        """把用户输入拆成用于匹配的 token。"""
        return {
            token
            for token in re.findall(r"[a-zA-Z0-9_\-\u4e00-\u9fff]+", text.lower())
            if token not in self.STOP_TOKENS
        }

    def _build_reason(
        self,
        tool: ToolResponse,
        score: int,
        intent: str | None,
        suggested_tool_type: str | None,
        schema_match: bool,
    ) -> str:
        """构造可展示、可审计的工具选择理由。"""
        schema_text = "schema_match=YES" if schema_match else "schema_match=NO"
        return (
            f"选择工具 {tool.name}，得分 {score}。"
            f" intent={intent or 'UNKNOWN'}，suggested_tool_type={suggested_tool_type or 'NONE'}，"
            f"{schema_text}。"
        )
