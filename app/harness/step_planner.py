from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from app.llm.llm_client import LLMClient
from app.services.tool_registry_service import ToolRegistryService


class HarnessStepPlanner:
    """生成 Harness 执行步骤的规划器。

    优先让 LLM 基于可用工具生成多步计划，再对模型输出做结构化校验和字段归一化。
    如果 LLM 不可用、输出不是合法 JSON，或者计划为空，则退回到确定性规则，保证 demo
    和自动化测试仍然稳定可重复。
    """

    DEFAULT_MAX_STEPS = 3
    VALID_TOOL_TYPES = {"MCP", "HTTP", "CLI", "SANDBOX"}

    def __init__(
        self,
        *,
        llm_client: LLMClient | None = None,
        tool_registry_service: ToolRegistryService | None = None,
    ) -> None:
        self.llm_client = llm_client or LLMClient()
        self.tool_registry_service = tool_registry_service or ToolRegistryService()
        self.last_planner = "deterministic-fallback-v1"
        self.last_fallback_used = True
        self.last_raw_response: str | None = None
        self.last_warnings: list[str] = []

    def create_steps(
        self,
        *,
        user_input: str,
        intent: dict[str, Any],
        run_mode: str = "SAFE_EXECUTE",
        task_id: UUID | None = None,
        run_id: UUID | None = None,
        trace_id: UUID | None = None,
        max_steps: int | None = None,
    ) -> list[dict[str, Any]]:
        """根据用户输入和 intent 生成执行步骤列表。"""
        limit = max_steps or self.DEFAULT_MAX_STEPS
        self._reset_metadata()
        llm_steps = self._llm_steps(
            user_input=user_input,
            intent=intent,
            run_mode=run_mode,
            task_id=task_id,
            run_id=run_id,
            trace_id=trace_id,
            max_steps=limit,
        )
        if llm_steps:
            self.last_planner = "llm-v1"
            self.last_fallback_used = False
            return llm_steps

        self.last_fallback_used = True
        self.last_planner = "deterministic-fallback-v1"
        fallback_steps = self._fallback_steps(user_input=user_input, intent=intent)
        return fallback_steps[:limit]

    def _llm_steps(
        self,
        *,
        user_input: str,
        intent: dict[str, Any],
        run_mode: str,
        task_id: UUID | None,
        run_id: UUID | None,
        trace_id: UUID | None,
        max_steps: int,
    ) -> list[dict[str, Any]]:
        """调用 LLM 生成计划；缺少审计 ID 时跳过，避免纯单元测试误写数据库。"""
        if task_id is None or run_id is None or trace_id is None:
            self.last_warnings.append("缺少 task/run/trace ID，已跳过 LLM planner。")
            return []

        try:
            prompt = self._build_planner_prompt(
                user_input=user_input,
                intent=intent,
                run_mode=run_mode,
                max_steps=max_steps,
            )
            llm_result, parsed = self.llm_client.complete_json(
                prompt,
                node_name="make_plan",
                task_id=task_id,
                run_id=run_id,
                trace_id=trace_id,
                system_message=self._build_system_message(),
            )
            self.last_raw_response = llm_result.text
        except Exception as exc:
            self.last_warnings.append(f"LLM planner 调用失败：{exc.__class__.__name__}: {exc}")
            return []

        if parsed is None:
            self.last_warnings.append("LLM planner 返回内容不是合法 JSON。")
            return []

        steps = self._sanitize_llm_steps(parsed, max_steps=max_steps)
        if not steps:
            self.last_warnings.append("LLM planner 没有返回可执行步骤。")
        return steps

    def _fallback_steps(
        self,
        *,
        user_input: str,
        intent: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """LLM 规划不可用时使用的确定性兜底步骤。"""
        cli_steps = self._git_cli_steps(user_input)
        if cli_steps:
            return cli_steps

        return [
            {
                "index": 0,
                "objective": intent.get("summary") or user_input,
                "intent": intent.get("intent"),
                "suggested_tool_type": intent.get("suggested_tool_type"),
                "tool_input": self._normalize_planned_tool_input(
                    intent.get("tool_input") or {}
                ),
                "status": "PENDING",
            }
        ]

    def _build_system_message(self) -> str:
        """构造 planner 的 system message。"""
        return """
你是 ToolHub 的 StepPlanner，负责把用户目标拆成可执行步骤。
你只生成计划，不执行工具，不决定权限，不绕过 ToolHub 的路由、schema 校验和 PermissionEngine。
你必须只返回严格 JSON，不要输出 Markdown 或解释文字。
"""

    def _build_planner_prompt(
        self,
        *,
        user_input: str,
        intent: dict[str, Any],
        run_mode: str,
        max_steps: int,
    ) -> str:
        """构造 planner 的 user prompt。"""
        payload = {
            "run_mode": run_mode,
            "max_steps": max_steps,
            "user_input": user_input,
            "intent": intent,
            "available_tools": self._available_tool_summaries(),
            "output_schema": {
                "steps": [
                    {
                        "objective": "这一步要完成的目标",
                        "intent": "CLI_EXECUTION / RUN_CODE / HTTP_CALL / CALCULATE / GENERAL_QUERY",
                        "suggested_tool_type": "MCP / HTTP / CLI / SANDBOX",
                        "tool_input": {
                            "说明": "给工具的结构化参数。CLI 必须优先使用 rule_id + args，不要生成任意 shell 命令。"
                        },
                    }
                ],
                "reason": "简短说明为什么这样拆分",
            },
            "planning_rules": [
                "步骤数量不能超过 max_steps。",
                "每一步只能描述一个明确动作。",
                "如果任务只需要一个工具调用，就只生成一个步骤。",
                "CLI 步骤必须使用已知 rule_id，例如 cli://git/status-short、cli://git/diff、cli://git/log-oneline。",
                "Sandbox Python 步骤必须把代码放在 tool_input.code，语言放在 tool_input.language。",
                "无法确定参数时不要编造危险参数，保留可由后续 schema 检查发现的问题。",
            ],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _available_tool_summaries(self) -> list[dict[str, Any]]:
        """读取当前可用工具，压缩成 planner 所需的摘要。"""
        try:
            tools = self.tool_registry_service.search_tools("", include_disabled=False)
        except Exception as exc:
            self.last_warnings.append(f"读取可用工具失败：{exc.__class__.__name__}: {exc}")
            return []

        return [
            {
                "name": tool.name,
                "tool_type": tool.tool_type.value,
                "description": tool.description,
                "endpoint": tool.endpoint,
                "mcp_url": tool.mcp_url,
                "transport": tool.transport,
                "tags": tool.tags,
                "risk_level": tool.risk_level.value,
                "input_schema": tool.input_schema,
            }
            for tool in tools[:30]
        ]

    def _sanitize_llm_steps(
        self,
        parsed: dict[str, Any],
        *,
        max_steps: int,
    ) -> list[dict[str, Any]]:
        """把 LLM 输出清洗为 Harness 内部稳定的 step 结构。"""
        raw_steps = parsed.get("steps") if isinstance(parsed, dict) else None
        if not isinstance(raw_steps, list):
            return []

        steps: list[dict[str, Any]] = []
        for raw_step in raw_steps[:max_steps]:
            if not isinstance(raw_step, dict):
                self.last_warnings.append("已跳过非对象类型的计划步骤。")
                continue

            tool_input = self._normalize_planned_tool_input(
                raw_step.get("tool_input") or {}
            )
            suggested_tool_type = self._normalize_tool_type(
                raw_step.get("suggested_tool_type")
            )
            intent = self._normalize_intent(raw_step.get("intent"), suggested_tool_type)
            if suggested_tool_type == "CLI":
                tool_input = self._normalize_cli_tool_input(tool_input)

            steps.append(
                {
                    "index": len(steps),
                    "objective": str(raw_step.get("objective") or "执行计划步骤").strip(),
                    "intent": intent,
                    "suggested_tool_type": suggested_tool_type,
                    "tool_input": tool_input,
                    "status": "PENDING",
                }
            )

        return steps

    def _normalize_tool_type(self, value: Any) -> str | None:
        """把模型输出的工具类型归一化为 ToolHub 枚举值。"""
        text = str(value or "").strip().upper()
        return text if text in self.VALID_TOOL_TYPES else None

    def _normalize_intent(self, value: Any, suggested_tool_type: str | None) -> str | None:
        """把模型输出的 intent 归一化，缺失时根据工具类型推断。"""
        text = str(value or "").strip().upper()
        aliases = {
            "CLI": "CLI_EXECUTION",
            "CLI_EXECUTION": "CLI_EXECUTION",
            "RUN_CODE": "RUN_CODE",
            "CODE_EXECUTION": "RUN_CODE",
            "RUN_PYTHON": "RUN_CODE",
            "HTTP": "HTTP_CALL",
            "HTTP_CALL": "HTTP_CALL",
            "CALCULATE": "CALCULATE",
            "GENERAL_QUERY": "GENERAL_QUERY",
        }
        if text in aliases:
            return aliases[text]
        return {
            "CLI": "CLI_EXECUTION",
            "SANDBOX": "RUN_CODE",
            "HTTP": "HTTP_CALL",
            "MCP": "CALCULATE",
        }.get(suggested_tool_type or "")

    def _git_cli_steps(self, user_input: str) -> list[dict[str, Any]]:
        """为 git 只读命令生成稳定的多步 demo 计划。"""
        text = user_input.lower()
        if "git" not in text:
            return []

        steps: list[dict[str, Any]] = []
        if "status" in text or "状态" in text:
            steps.append(
                self._cli_step(
                    index=len(steps),
                    objective="查看 Git 工作区状态",
                    rule_id="cli://git/status-short",
                    args={},
                )
            )
        if "diff" in text or "变更" in text or "差异" in text:
            steps.append(
                self._cli_step(
                    index=len(steps),
                    objective="查看 Git 工作区 diff",
                    rule_id="cli://git/diff",
                    args={"path": ".", "staged": False},
                )
            )
        if "log" in text or "提交历史" in text:
            steps.append(
                self._cli_step(
                    index=len(steps),
                    objective="查看 Git 最近提交历史",
                    rule_id="cli://git/log-oneline",
                    args={"max_count": 5},
                )
            )
        return steps

    def _cli_step(
        self,
        *,
        index: int,
        objective: str,
        rule_id: str,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "index": index,
            "objective": objective,
            "intent": "CLI_EXECUTION",
            "suggested_tool_type": "CLI",
            "tool_input": {
                "rule_id": rule_id,
                "args": args,
            },
            "status": "PENDING",
        }

    def _normalize_planned_tool_input(
        self,
        tool_input: dict[str, Any],
    ) -> dict[str, Any]:
        """对计划阶段能确定的字段做轻量归一化。"""
        normalized = dict(tool_input)
        if "code" not in normalized and normalized.get("code_hint"):
            normalized["code"] = normalized["code_hint"]
        normalized.pop("code_hint", None)
        return normalized

    def _normalize_cli_tool_input(self, tool_input: dict[str, Any]) -> dict[str, Any]:
        """把 LLM 可能生成的常见 CLI 写法转换为安全 rule_id 写法。"""
        normalized = dict(tool_input)
        raw_command = str(normalized.get("command") or normalized.get("rule_id") or "").lower()
        if "rule_id" not in normalized:
            if "git status" in raw_command:
                normalized["rule_id"] = "cli://git/status-short"
                normalized.setdefault("args", {})
            elif "git diff" in raw_command:
                normalized["rule_id"] = "cli://git/diff"
                normalized.setdefault("args", {"path": ".", "staged": False})
            elif "git log" in raw_command:
                normalized["rule_id"] = "cli://git/log-oneline"
                normalized.setdefault("args", {"max_count": 5})
        normalized.pop("command", None)
        if "args" not in normalized:
            normalized["args"] = {}
        return normalized

    def _reset_metadata(self) -> None:
        """重置上一次规划的诊断元数据。"""
        self.last_planner = "deterministic-fallback-v1"
        self.last_fallback_used = True
        self.last_raw_response = None
        self.last_warnings = []
