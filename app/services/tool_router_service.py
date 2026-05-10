from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from app.schemas.routing import (
    ToolRouteCandidateDetail,
    ToolRouteRerankMetadata,
    ToolRouteResult,
)
from app.schemas.tool import HealthStatus, RiskLevel, ToolResponse
from app.services.schema_validation_service import SchemaValidationService
from app.services.tool_registry_service import ToolRegistryService
from app.services.tool_rerank_service import ToolRerankService


class ToolRouterService:
    """根据用户输入、意图、schema 和工具质量选择最合适的工具。"""

    STOP_TOKENS = {
        "请",
        "我",
        "一个",
        "工具",
        "处理",
        "问题",
        "需求",
        "任务",
        "帮我",
        "当前",
        "没有",
        "查看",
        "执行",
    }

    # 危险输入关键词 — 命中后直接返回 NO_TOOL，不进入候选打分。
    DANGEROUS_PATTERNS = [
        # 破坏性系统命令
        "rm -rf",
        "rm -r",
        "format c:",
        "format /",
        "del /f",
        "del /s",
        "dd if=",
        "mkfs.",
        ":(){ :|:& };:",  # fork bomb
        # 敏感文件访问
        "/etc/shadow",
        "/etc/passwd",
        "/etc/sudoers",
        ".env",
        "id_rsa",
        "authorized_keys",
        # 路径穿越
        "../",
        "..\\",
        # 云元数据
        "169.254.169.254",
        "metadata.google.internal",
        # 恶意下载执行
        "curl http://evil",
        "wget http://evil",
        "http://evil",
        "https://evil",
    ]

    MIN_SCORE_WITHOUT_INTENT = 2.0

    def __init__(
        self,
        tool_registry_service: ToolRegistryService | None = None,
        schema_validation_service: SchemaValidationService | None = None,
        rerank_service: ToolRerankService | None = None,
    ) -> None:
        """创建工具路由服务。"""
        self.tool_registry_service = tool_registry_service or ToolRegistryService()
        self.schema_validation_service = schema_validation_service or SchemaValidationService()
        self.rerank_service = rerank_service or ToolRerankService()

    def select_tool(
        self,
        *,
        user_input: str,
        intent: str | None = None,
        suggested_tool_type: str | None = None,
        tool_input: dict[str, Any] | None = None,
        top_k: int = 5,
        enable_llm_rerank: bool = False,
        task_id: UUID | None = None,
        run_id: UUID | None = None,
        trace_id: UUID | None = None,
    ) -> ToolRouteResult:
        """从 ACTIVE 工具中选择最合适的工具，并返回 top-k 候选解释。"""
        # 危险输入门禁 —— 先于所有打分和路由逻辑，命中后直接返回 NO_TOOL。
        danger_reason = self._check_dangerous(user_input, tool_input or {})
        if danger_reason is not None:
            return ToolRouteResult(
                selected_tool=None,
                score=0,
                reason=danger_reason,
                candidates=[],
                candidate_details=[],
                top_k=top_k,
            )

        top_k = min(max(top_k, 1), 20)
        normalized_tool_input = tool_input or {}
        tools = self.tool_registry_service.search_tools("", include_disabled=False)
        if not tools:
            return ToolRouteResult(
                selected_tool=None,
                score=0,
                reason="没有可用的 ACTIVE 工具。",
                candidates=[],
                candidate_details=[],
                top_k=top_k,
            )

        candidate_details = [
            self._build_candidate_detail(
                tool=tool,
                user_input=user_input,
                intent=intent,
                suggested_tool_type=suggested_tool_type,
                tool_input=normalized_tool_input,
            )
            for tool in tools
        ]
        self._sort_and_rank(candidate_details)
        top_candidates = candidate_details[:top_k]
        rerank_metadata = ToolRouteRerankMetadata(enabled=enable_llm_rerank)
        if enable_llm_rerank:
            rerank_metadata = self.rerank_service.rerank(
                user_input=user_input,
                intent=intent,
                suggested_tool_type=suggested_tool_type,
                tool_input=normalized_tool_input,
                candidates=top_candidates,
                task_id=task_id,
                run_id=run_id,
                trace_id=trace_id,
            )
            self._sort_and_rank(candidate_details)
            top_candidates = candidate_details[:top_k]

        valid_candidates = [item for item in candidate_details if item.schema_match]
        if not valid_candidates:
            best = candidate_details[0]
            return ToolRouteResult(
                selected_tool=None,
                score=0,
                reason=f"候选工具的输入 schema 均不匹配：{best.rejection_reason}",
                candidates=[item.tool for item in top_candidates],
                candidate_details=top_candidates,
                schema_match=False,
                missing_fields=best.missing_fields,
                rejection_reason=best.rejection_reason,
                top_k=top_k,
                rerank=rerank_metadata,
            )

        selected_candidate = valid_candidates[0]
        selected_tool = selected_candidate.tool
        score = selected_candidate.score
        has_intent_signal = bool(suggested_tool_type or self._intent_to_tool_type(intent))
        if (
            not selected_candidate.matched_signals
            or score <= 0
            or (score < self.MIN_SCORE_WITHOUT_INTENT and not has_intent_signal)
        ):
            return ToolRouteResult(
                selected_tool=None,
                score=0,
                reason="没有工具与当前用户输入或意图形成足够强的相关性；质量分不会单独触发路由。",
                candidates=[item.tool for item in top_candidates],
                candidate_details=top_candidates,
                top_k=top_k,
                rerank=rerank_metadata,
            )

        return ToolRouteResult(
            selected_tool=selected_tool,
            score=score,
            reason=self._build_reason(selected_candidate, intent, suggested_tool_type),
            candidates=[item.tool for item in top_candidates],
            candidate_details=top_candidates,
            schema_match=selected_candidate.schema_match,
            missing_fields=selected_candidate.missing_fields,
            rejection_reason=selected_candidate.rejection_reason,
            top_k=top_k,
            rerank=rerank_metadata,
        )

    def _build_candidate_detail(
        self,
        *,
        tool: ToolResponse,
        user_input: str,
        intent: str | None,
        suggested_tool_type: str | None,
        tool_input: dict[str, Any],
    ) -> ToolRouteCandidateDetail:
        """生成候选工具分项打分和 schema 诊断信息。"""
        schema_result = self.schema_validation_service.validate_tool_input(
            tool.input_schema,
            tool_input,
        )
        # schema 是硬门禁：合法不代表相关，非法直接降权到不可选。
        schema_score = 0.0 if schema_result.valid else -100.0
        score_breakdown, matched_signals = self._score_tool(
            tool=tool,
            user_input=user_input,
            intent=intent,
            suggested_tool_type=suggested_tool_type,
            schema_score=schema_score,
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
            score=sum(score_breakdown.values()),
            score_breakdown=score_breakdown,
            matched_signals=matched_signals,
            schema_match=schema_result.valid,
            schema_score=schema_score,
            missing_fields=schema_result.missing_fields,
            rejection_reason=rejection_reason,
        )

    def _score_tool(
        self,
        *,
        tool: ToolResponse,
        user_input: str,
        intent: str | None,
        suggested_tool_type: str | None,
        schema_score: float,
    ) -> tuple[dict[str, float], list[str]]:
        """计算候选工具的综合分。"""
        normalized_input = user_input.lower()
        tokens = self._tokens(normalized_input)
        breakdown: dict[str, float] = {"schema": schema_score}
        matched_signals: list[str] = []

        type_score = 0.0
        if suggested_tool_type and tool.tool_type.value == suggested_tool_type.upper():
            type_score += 8.0
            matched_signals.append("suggested_tool_type")

        intent_tool_type = self._intent_to_tool_type(intent)
        if intent_tool_type and tool.tool_type.value == intent_tool_type:
            type_score += 6.0
            matched_signals.append("intent_tool_type")
        breakdown["type"] = type_score

        keyword_score = 0.0
        if tool.name.lower() in normalized_input:
            keyword_score += 5.0
            matched_signals.append("tool_name")

        for tag in tool.tags:
            if tag.lower() in tokens:
                keyword_score += 3.0
                matched_signals.append(f"tag:{tag}")

        description = tool.description.lower()
        for token in tokens:
            if token and token in description:
                keyword_score += 1.0
                matched_signals.append(f"description:{token}")
        breakdown["keyword"] = keyword_score

        quality_score = 0.0
        if tool.quality_score is not None:
            quality_score += float(tool.quality_score) * 2.0
        if tool.success_rate is not None:
            quality_score += float(tool.success_rate) * 2.0
        if tool.avg_duration_ms is not None:
            if tool.avg_duration_ms <= 1000:
                quality_score += 1.0
            elif tool.avg_duration_ms <= 5000:
                quality_score += 0.5
            else:
                quality_score -= 0.5
        breakdown["quality"] = quality_score

        health_score = 0.0
        if tool.health_status == HealthStatus.UP:
            health_score += 1.0
        elif tool.health_status == HealthStatus.DOWN:
            health_score -= 3.0
        breakdown["health"] = health_score

        risk_score = 0.0
        if tool.risk_level == RiskLevel.HIGH and intent != "RUN_CODE":
            risk_score -= 1.0
        elif tool.risk_level == RiskLevel.LOW:
            risk_score += 0.5
        breakdown["risk"] = risk_score
        return breakdown, matched_signals

    def _sort_and_rank(self, candidates: list[ToolRouteCandidateDetail]) -> None:
        """按可执行性和综合分排序，并写入 rank。"""
        candidates.sort(key=lambda item: (item.schema_match, item.score), reverse=True)
        for index, candidate in enumerate(candidates, start=1):
            candidate.rank = index

    def _intent_to_tool_type(self, intent: str | None) -> str | None:
        """把标准化 intent 映射到更适合的工具类型。"""
        mapping = {
            "RUN_CODE": "SANDBOX",
            "CLI_EXECUTION": "CLI",
            "HTTP_CALL": "HTTP",
            "CALCULATE": "MCP",
        }
        return mapping.get((intent or "").upper())

    def _check_dangerous(
        self,
        user_input: str,
        tool_input: dict[str, Any],
    ) -> str | None:
        """检查用户输入是否包含危险操作模式，命中则返回拒绝原因。"""
        combined = f"{user_input} {str(tool_input)}".lower()
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern.lower() in combined:
                return f"拒绝路由：用户输入包含危险操作模式（命中: {pattern}）"
        return None

    def _tokens(self, text: str) -> set[str]:
        """把用户输入拆成用于匹配的 token。"""
        return {
            token
            for token in re.findall(r"[a-zA-Z0-9_\-\u4e00-\u9fff]+", text.lower())
            if token not in self.STOP_TOKENS
        }

    def _build_reason(
        self,
        candidate: ToolRouteCandidateDetail,
        intent: str | None,
        suggested_tool_type: str | None,
    ) -> str:
        """构造可展示、可审计的工具选择理由。"""
        breakdown = ", ".join(
            f"{name}={score:.2f}" for name, score in candidate.score_breakdown.items()
        )
        return (
            f"选择工具 {candidate.tool.name}，综合得分 {candidate.score:.2f}。"
            f" intent={intent or 'UNKNOWN'}，suggested_tool_type={suggested_tool_type or 'NONE'}，"
            f"schema_match={'YES' if candidate.schema_match else 'NO'}，"
            f"breakdown=[{breakdown}]。"
        )
