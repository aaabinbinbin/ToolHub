from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from app.llm.llm_client import LLMClient


class HarnessReplanner:
    """根据 observation 修正当前步骤的输入，但不绕过路由和权限。"""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or LLMClient()
        self.last_raw_response: str | None = None
        self.last_fallback_used = True
        self.last_reason: str | None = None

    def replan_step(
        self,
        *,
        user_input: str,
        current_step: dict[str, Any],
        observation: dict[str, Any],
        retry_count: int,
        max_retries: int,
        task_id: UUID,
        run_id: UUID,
        trace_id: UUID,
    ) -> dict[str, Any]:
        """返回修正后的 step；LLM 不可用时保守复用原始输入。"""
        self.last_raw_response = None
        self.last_fallback_used = True
        self.last_reason = "fallback: reuse current tool_input"

        prompt = self._build_prompt(
            user_input=user_input,
            current_step=current_step,
            observation=observation,
            retry_count=retry_count,
            max_retries=max_retries,
        )
        try:
            result, parsed = self.llm_client.complete_json(
                prompt,
                node_name="replan_step",
                task_id=task_id,
                run_id=run_id,
                trace_id=trace_id,
                system_message=self._build_system_message(),
            )
            self.last_raw_response = result.text
        except Exception as exc:
            self.last_reason = f"LLM replanner failed: {exc.__class__.__name__}: {exc}"
            return dict(current_step)

        if not isinstance(parsed, dict):
            self.last_reason = "LLM replanner returned non-object JSON"
            return dict(current_step)

        tool_input = parsed.get("tool_input")
        if not isinstance(tool_input, dict):
            self.last_reason = "LLM replanner did not return tool_input"
            return dict(current_step)

        self.last_fallback_used = False
        self.last_reason = str(parsed.get("reason") or "LLM 修正了当前步骤输入")
        return {
            **current_step,
            "tool_input": tool_input,
            "replan_reason": self.last_reason,
        }

    def _build_system_message(self) -> str:
        """构造 replanner 的 system message。"""
        return (
            "你是 ToolHub 的 HarnessReplanner，只能基于失败 observation 修正当前步骤的 "
            "tool_input。你不能决定权限，不能跳过 router/schema/PermissionEngine，"
            "不能新增危险动作。只返回严格 JSON。"
        )

    def _build_prompt(
        self,
        *,
        user_input: str,
        current_step: dict[str, Any],
        observation: dict[str, Any],
        retry_count: int,
        max_retries: int,
    ) -> str:
        """构造 replanner 的输入上下文。"""
        payload = {
            "user_input": user_input,
            "retry_count": retry_count,
            "max_retries": max_retries,
            "current_step": current_step,
            "observation": observation,
            "output_schema": {
                "tool_input": "修正后的结构化工具输入",
                "reason": "简短说明为什么这样修正",
            },
            "rules": [
                "只允许修正 tool_input，不允许绕过工具路由和权限检查。",
                "无法确定修正方式时返回原 tool_input。",
                "不要生成任意 shell 命令；CLI 仍然必须使用 rule_id + args。",
            ],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)
