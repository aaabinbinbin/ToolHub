from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from app.context.instruction_loader import InstructionLoader
from app.llm.llm_client import LLMClient
from app.schemas.summary import ResultSummary, SummaryType


SUMMARY_SYSTEM_TEMPLATE = """
你是 ToolHub 的 ResultSummarizerService，负责把工具执行结果总结成中文最终答案。

你必须遵守项目规则，不要声称执行了实际没有执行的工具。
权限拒绝、无工具、工具失败时，要明确说明原因和下一步建议。

项目规则：
{instructions}
"""

SUMMARY_USER_TEMPLATE = """
请根据下面的 ToolHub 执行上下文生成最终答案。

输出必须是严格 JSON，不要输出 Markdown，不要输出解释文字。
JSON 字段：
- final_answer: 面向用户的中文最终答案
- summary_type: SUCCESS / FAILED / DENIED / NO_TOOL
- next_action: 下一步建议，没有则为 NONE

执行上下文：
{payload}
"""


class ResultSummarizerService:
    """把 Harness 执行结果总结成用户可直接阅读的 final_answer。"""

    def __init__(
        self,
        instruction_loader: InstructionLoader | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        self.instruction_loader = instruction_loader or InstructionLoader()
        self.llm_client = llm_client or LLMClient()

    def summarize(
        self,
        *,
        user_input: str,
        status: str,
        intent: dict[str, Any] | None,
        route: dict[str, Any] | None,
        permission: dict[str, Any] | None,
        tool_input: dict[str, Any] | None,
        tool_result: dict[str, Any] | None,
        task_id: UUID,
        run_id: UUID,
        trace_id: UUID,
    ) -> ResultSummary:
        """调用 LLM 总结结果；LLM 不可用时使用规则 fallback。"""
        summary_type = self._summary_type(status, permission, tool_result)
        fallback = self._fallback_summary(
            summary_type=summary_type,
            permission=permission,
            tool_result=tool_result,
            route=route,
        )

        try:
            prompt = self._build_prompt(
                user_input=user_input,
                summary_type=summary_type,
                intent=intent,
                route=route,
                permission=permission,
                tool_input=tool_input,
                tool_result=tool_result,
            )
            llm_result, parsed = self.llm_client.complete_json(
                prompt,
                node_name="summarize_result",
                task_id=task_id,
                run_id=run_id,
                trace_id=trace_id,
                system_message=self._build_system_message(),
            )
        except Exception as exc:
            return fallback.model_copy(
                update={
                    "fallback_used": True,
                    "raw_response": f"{exc.__class__.__name__}: {exc}",
                }
            )

        if parsed is None:
            fallback = self._fallback_summary(
                summary_type=summary_type,
                permission=permission,
                tool_result=tool_result,
                route=route,
            )
            return fallback.model_copy(
                update={"fallback_used": True, "raw_response": llm_result.text}
            )

        return ResultSummary(
            final_answer=str(parsed.get("final_answer") or "").strip()
            or fallback.final_answer,
            summary_type=self._safe_summary_type(parsed.get("summary_type"), summary_type),
            next_action=parsed.get("next_action"),
            fallback_used=False,
            raw_response=llm_result.text,
        )

    def _build_system_message(self) -> str:
        instructions = self.instruction_loader.load()
        return SUMMARY_SYSTEM_TEMPLATE.format(instructions=instructions)

    def _build_prompt(
        self,
        *,
        user_input: str,
        summary_type: SummaryType,
        intent: dict[str, Any] | None,
        route: dict[str, Any] | None,
        permission: dict[str, Any] | None,
        tool_input: dict[str, Any] | None,
        tool_result: dict[str, Any] | None,
    ) -> str:
        payload = {
            "user_input": user_input,
            "summary_type": summary_type,
            "intent": intent,
            "route": route,
            "permission": permission,
            "tool_input": tool_input,
            "tool_result": tool_result,
        }
        return SUMMARY_USER_TEMPLATE.format(
            payload=json.dumps(payload, ensure_ascii=False)
        )

    def _summary_type(
        self,
        status: str,
        permission: dict[str, Any] | None,
        tool_result: dict[str, Any] | None,
    ) -> SummaryType:
        if status == "NO_TOOL":
            return "NO_TOOL"
        if status == "DENIED" or (permission and not permission.get("allowed", False)):
            return "DENIED"
        if status == "SUCCESS" and tool_result and tool_result.get("success"):
            return "SUCCESS"
        return "FAILED"

    def _safe_summary_type(self, value: Any, default: SummaryType) -> SummaryType:
        raw_value = str(value or "").strip().upper()
        if raw_value in {"SUCCESS", "FAILED", "DENIED", "NO_TOOL"}:
            return raw_value  # type: ignore[return-value]
        return default

    def _fallback_summary(
        self,
        *,
        summary_type: SummaryType,
        permission: dict[str, Any] | None,
        tool_result: dict[str, Any] | None,
        route: dict[str, Any] | None,
    ) -> ResultSummary:
        if summary_type == "DENIED":
            reason = (permission or {}).get("reason") or "权限检查未通过。"
            return ResultSummary(
                final_answer=f"任务未执行，因为权限检查未通过：{reason}",
                summary_type="DENIED",
                next_action=(permission or {}).get("required_mode") or "请调整运行模式或工具权限后重试。",
            )
        if summary_type == "NO_TOOL":
            reason = (route or {}).get("reason") or "没有匹配到可用工具。"
            return ResultSummary(
                final_answer=f"当前没有可用工具可以处理这个请求：{reason}",
                summary_type="NO_TOOL",
                next_action="请先注册合适的工具，或调整输入描述。",
            )
        if summary_type == "FAILED":
            error = (tool_result or {}).get("error_message")
            output = (tool_result or {}).get("output") or {}
            stderr = output.get("stderr") if isinstance(output, dict) else None
            reason = error or stderr or "工具执行失败。"
            return ResultSummary(
                final_answer=f"工具执行失败，原因：{reason}",
                summary_type="FAILED",
                next_action="请查看任务事件和工具调用日志后重试。",
            )

        output = (tool_result or {}).get("output")
        return ResultSummary(
            final_answer=f"任务已完成。工具执行结果：{output}",
            summary_type="SUCCESS",
            next_action="NONE",
        )
