from __future__ import annotations

import re
from typing import Any
from uuid import UUID, uuid4

from app.context.instruction_loader import InstructionLoader
from app.llm.llm_client import LLMClient
from app.schemas.llm import IntentResult
from app.services.tool_registry_service import ToolRegistryService


class IntentService:
    """负责把用户输入转换成结构化意图。

    只实现意图理解，不做最终工具路由和权限决策。
    LLM 可以给出风险建议，但最终是否允许执行由后续 PermissionEngine 决定。
    """

    def __init__(
        self,
        instruction_loader: InstructionLoader | None = None,
        llm_client: LLMClient | None = None,
        tool_registry_service: ToolRegistryService | None = None,
    ) -> None:
        """创建 IntentService。

        Args:
            instruction_loader: 项目规则加载器。
            llm_client: LLM 调用客户端。
            tool_registry_service: 工具注册中心服务，用于读取当前可用工具摘要。
        """
        self.instruction_loader = instruction_loader or InstructionLoader()
        self.llm_client = llm_client or LLMClient()
        self.tool_registry_service = tool_registry_service or ToolRegistryService()

    def understand_intent(
        self,
        user_input: str,
        *,
        run_mode: str = "SAFE_EXECUTE",
        task_id: UUID | None = None,
        run_id: UUID | None = None,
        trace_id: UUID | None = None,
    ) -> IntentResult:
        """理解用户输入并输出结构化意图。

        Args:
            user_input: 用户原始输入。
            run_mode: 当前运行模式。
            task_id: 可选任务 ID。目前还没有完整任务系统，因此允许为空。
            run_id: 可选 run ID。不传时临时生成。
            trace_id: 可选 trace ID。不传时临时生成。

        Returns:
            标准化后的 IntentResult。
        """
        run_id = run_id or uuid4()
        trace_id = trace_id or uuid4()
        instructions = self.instruction_loader.load()
        prompt = self._build_user_prompt(user_input, run_mode)
        system_message = self._build_system_message(instructions)

        llm_result, parsed = self.llm_client.complete_json(
            prompt,
            node_name="understand_intent",
            task_id=task_id,
            run_id=run_id,
            trace_id=trace_id,
            system_message=system_message,
        )

        fallback_used = parsed is None
        if parsed is None:
            # LLM 输出不是合法 JSON 时使用规则兜底，保证后续节点仍能继续。
            parsed = self._fallback_intent(user_input)

        normalized_intent = self._normalize_intent(parsed.get("intent"), user_input)
        return IntentResult(
            intent=normalized_intent,
            summary=parsed.get("summary", "用户意图需要进一步分析。"),
            confidence=self._safe_confidence(parsed.get("confidence")),
            risk_hint=parsed.get("risk_hint", "LOW"),
            suggested_tool_type=self._normalize_tool_type(
                parsed.get("suggested_tool_type"), normalized_intent
            ),
            tool_input=self._normalize_tool_input(parsed.get("tool_input")),
            fallback_used=fallback_used,
            raw_response=llm_result.text,
            run_id=run_id,
            trace_id=trace_id,
        )

    def _normalize_tool_input(self, value: Any) -> dict[str, Any]:
        """把模型返回的 tool_input 统一转换为 dict。"""
        if isinstance(value, dict):
            return value
        if value is None:
            return {}
        return {"value": value}

    def _normalize_tool_type(self, value: Any, intent: str) -> str | None:
        """根据 intent 归一化建议工具类型。"""
        intent_defaults = {
            "RUN_CODE": "SANDBOX",
            "CLI_EXECUTION": "CLI",
            "HTTP_CALL": "HTTP",
        }
        if intent in intent_defaults:
            return intent_defaults[intent]

        raw_value = str(value or "").strip().upper()
        if raw_value in {"MCP", "HTTP", "CLI", "SANDBOX"}:
            return raw_value
        return None

    def _safe_confidence(self, value: Any) -> float:
        """把模型返回的置信度归一化到 0~1。"""
        if isinstance(value, int | float):
            return max(0.0, min(float(value), 1.0))
        if isinstance(value, str):
            label_map = {"LOW": 0.35, "MEDIUM": 0.65, "HIGH": 0.9}
            upper_value = value.strip().upper()
            if upper_value in label_map:
                return label_map[upper_value]
            try:
                return max(0.0, min(float(value), 1.0))
            except ValueError:
                return 0.5
        return 0.5

    def _normalize_intent(self, intent: Any, user_input: str) -> str:
        """把模型返回的意图标签归一化为 ToolHub 内部稳定枚举。"""
        raw_intent = str(intent or "").strip().upper()
        alias_map = {
            "EXECUTE_PYTHON_CODE": "RUN_CODE",
            "PYTHON_CODE_EXECUTION": "RUN_CODE",
            "CODE_EXECUTION": "RUN_CODE",
            "RUN_PYTHON": "RUN_CODE",
            "RUN_CODE": "RUN_CODE",
            "CLI": "CLI_EXECUTION",
            "CLI_EXECUTION": "CLI_EXECUTION",
            "HTTP": "HTTP_CALL",
            "HTTP_CALL": "HTTP_CALL",
            "CALCULATE": "CALCULATE",
            "GENERAL_QUERY": "GENERAL_QUERY",
        }
        if raw_intent in alias_map:
            return alias_map[raw_intent]
        return self._fallback_intent(user_input)["intent"]

    def _build_system_message(self, instructions: str) -> str:
        """构造 system message。

        system message 放项目规则、安全规则和角色约束；user prompt 只放本次任务输入。
        """
        return f"""
        你是 ToolHub 的 IntentService，负责把用户自然语言输入转换成严格 JSON。
        
        你必须遵守下面的项目规则和安全规则。你可以给出风险建议，但不能替代 PermissionEngine 做最终权限决策。
        
        项目规则：
        {instructions}
        """

    def _build_user_prompt(self, user_input: str, run_mode: str) -> str:
        """构造 user prompt。"""
        available_tools = self._load_available_tool_summaries()
        return f"""
        运行模式：
        {run_mode}
        
        当前可用工具摘要：
        {available_tools}
        
        用户输入：
        {user_input}
        
        请只返回 JSON，不要输出 Markdown，不要输出解释文字。
        JSON 字段必须包含：
        - intent
        - summary
        - confidence
        - risk_hint
        - suggested_tool_type
        - tool_input
        """

    def _load_available_tool_summaries(self) -> list[dict[str, Any]]:
        """读取当前 ACTIVE 工具摘要，作为意图理解上下文。"""
        tools = self.tool_registry_service.search_tools("", include_disabled=False)
        return [
            {
                "name": tool.name,
                "tool_type": tool.tool_type.value,
                "description": tool.description,
                "tags": tool.tags,
                "risk_level": tool.risk_level.value,
            }
            for tool in tools
        ]

    def _fallback_intent(self, user_input: str) -> dict[str, Any]:
        """JSON 解析失败或意图标签未知时的规则兜底。"""
        text = user_input.lower()
        if "python" in text or "print(" in text:
            code_match = re.search(r"(print\(.*\)|sum\(.*\))", user_input)
            return {
                "intent": "RUN_CODE",
                "summary": "用户想运行 Python 代码。",
                "confidence": 0.65,
                "risk_hint": "HIGH",
                "suggested_tool_type": "SANDBOX",
                "tool_input": {
                    "language": "python",
                    "code_hint": code_match.group(1) if code_match else None,
                },
            }
        if "git status" in text or "git 状态" in text:
            return {
                "intent": "CLI_EXECUTION",
                "summary": "用户想查看 git 状态。",
                "confidence": 0.6,
                "risk_hint": "MEDIUM",
                "suggested_tool_type": "CLI",
                "tool_input": {"command": "git status"},
            }
        if "echo" in text or "http" in text:
            return {
                "intent": "HTTP_CALL",
                "summary": "用户想调用 HTTP 工具。",
                "confidence": 0.55,
                "risk_hint": "LOW",
                "suggested_tool_type": "HTTP",
                "tool_input": {},
            }
        return {
            "intent": "GENERAL_QUERY",
            "summary": "用户意图需要进一步分析。",
            "confidence": 0.4,
            "risk_hint": "LOW",
            "suggested_tool_type": None,
            "tool_input": {},
        }
