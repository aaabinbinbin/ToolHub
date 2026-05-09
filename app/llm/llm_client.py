from __future__ import annotations

import json
import re
import time
from collections.abc import Iterator
from typing import Any
from uuid import UUID

from openai import APIConnectionError, APIError, APITimeoutError, OpenAI, RateLimitError

from app.common.config import get_settings
from app.repositories.db import get_connection
from app.repositories.llm_call_repository import LLMCallRepository
from app.schemas.llm import LLMCallRecord, LLMResult


DEFAULT_SYSTEM_MESSAGE = """你是 ToolHub 的 LLM 节点。
请输出简洁、安全、结构化的结果。你可以提示风险，但不能替代 PermissionEngine 做最终权限决策。
"""


class LLMClient:
    """统一封装 OpenAI-compatible LLM 调用。

    当前使用 OpenAI SDK 调用兼容 OpenAI Chat Completions 协议的模型服务。
    这个类同时负责记录 `llm_calls`，保证每次 LLM 调用都可以被审计和展示。
    """

    def complete(
        self,
        prompt: str,
        *,
        node_name: str,
        run_id: UUID,
        trace_id: UUID,
        task_id: UUID | None = None,
        model: str | None = None,
        system_message: str | None = None,
        stream: bool = False,
    ) -> LLMResult:
        """调用 LLM 并返回标准化结果。

        Args:
            prompt: user message 内容。
            node_name: 当前 LLM 调用所在节点，例如 `understand_intent`。
            run_id: 本次 Harness run ID。
            trace_id: 全链路追踪 ID。
            task_id: 可选任务 ID。Day 2 还没有完整 Task Runtime，因此允许为空。
            model: 可选模型名，不传时使用配置中的默认模型。
            system_message: 可选 system message，不传时使用默认系统提示词。
            stream: 是否使用流式调用。

        Returns:
            标准化后的 LLMResult。
        """
        if stream:
            # complete_stream 会自己写入 llm_calls；这里仅聚合文本并返回给调用方。
            text = "".join(
                self.complete_stream(
                    prompt,
                    node_name=node_name,
                    run_id=run_id,
                    trace_id=trace_id,
                    task_id=task_id,
                    model=model,
                    system_message=system_message,
                )
            )
            settings = get_settings()
            return LLMResult(
                text=text,
                provider=settings.llm_provider,
                model=model or settings.llm_model,
                status="SUCCESS",
            )

        settings = get_settings()
        selected_model = model or settings.llm_model
        started_at = time.perf_counter()

        try:
            if self._should_use_mock_response():
                result = self._mock_complete(prompt, selected_model, started_at)
            else:
                result = self._call_openai_compatible(
                    prompt,
                    selected_model,
                    system_message=system_message,
                    started_at=started_at,
                )
        except (APITimeoutError, APIConnectionError, RateLimitError, APIError) as exc:
            result = self._failed_result(settings.llm_provider, selected_model, started_at, exc)
        except Exception as exc:
            result = self._failed_result(settings.llm_provider, selected_model, started_at, exc)

        self._record_call(prompt, node_name, run_id, trace_id, task_id, result)
        return result

    def complete_json(
        self, prompt: str, **kwargs: Any
    ) -> tuple[LLMResult, dict[str, Any] | None]:
        """调用 LLM 并尝试解析 JSON。

        这里不抛出 JSONDecodeError，而是返回 `(result, None)`。
        业务层可以根据 parsed 是否为 None 决定是否进入 fallback。
        """
        result = self.complete(prompt, **kwargs)
        if result.status != "SUCCESS":
            return result, None

        try:
            return result, json.loads(result.text)
        except json.JSONDecodeError:
            return result, None

    def complete_stream(
        self,
        prompt: str,
        *,
        node_name: str,
        run_id: UUID,
        trace_id: UUID,
        task_id: UUID | None = None,
        model: str | None = None,
        system_message: str | None = None,
    ) -> Iterator[str]:
        """流式调用 LLM。

        真实流式调用会优先请求服务端返回 usage。若厂商不支持流式 usage，则 token 字段保持 None，
        不用估算值伪装成精确数据。
        """
        settings = get_settings()
        selected_model = model or settings.llm_model
        started_at = time.perf_counter()
        chunks: list[str] = []
        usage: Any | None = None

        try:
            if self._should_use_mock_response():
                result = self._mock_complete(prompt, selected_model, started_at)
                yield result.text
            else:
                client = self._create_openai_client()
                response = self._create_stream_response(
                    client, selected_model, prompt, system_message
                )
                for event in response:
                    event_usage = getattr(event, "usage", None)
                    if event_usage is not None:
                        usage = event_usage

                    choices = getattr(event, "choices", None) or []
                    if not choices:
                        continue

                    delta = choices[0].delta.content
                    if delta:
                        chunks.append(delta)
                        yield delta

                text = "".join(chunks)
                input_tokens, output_tokens = self._extract_usage_tokens(usage)
                result = LLMResult(
                    text=text,
                    provider=settings.llm_provider,
                    model=selected_model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    duration_ms=int((time.perf_counter() - started_at) * 1000),
                    status="SUCCESS",
                )
        except Exception as exc:
            result = self._failed_result(settings.llm_provider, selected_model, started_at, exc)

        self._record_call(prompt, node_name, run_id, trace_id, task_id, result)

    def _call_openai_compatible(
        self,
        prompt: str,
        model: str,
        *,
        system_message: str | None,
        started_at: float,
    ) -> LLMResult:
        """执行一次非流式 OpenAI-compatible 调用。"""
        settings = get_settings()
        client = self._create_openai_client()
        response = client.chat.completions.create(
            model=model,
            messages=self._build_messages(prompt, system_message),
            temperature=0,
        )
        text = response.choices[0].message.content or ""
        input_tokens, output_tokens = self._extract_usage_tokens(response.usage)
        return LLMResult(
            text=text,
            provider=settings.llm_provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            status="SUCCESS",
        )

    def _create_stream_response(
        self,
        client: OpenAI,
        model: str,
        prompt: str,
        system_message: str | None,
    ) -> Any:
        """创建流式响应对象。

        OpenAI 和部分兼容服务支持 `stream_options={"include_usage": True}`。
        如果兼容服务不支持该参数，则退回普通 stream。
        """
        try:
            return client.chat.completions.create(
                model=model,
                messages=self._build_messages(prompt, system_message),
                temperature=0,
                stream=True,
                stream_options={"include_usage": True},
            )
        except APIError as exc:
            if "stream_options" not in str(exc):
                raise
            return client.chat.completions.create(
                model=model,
                messages=self._build_messages(prompt, system_message),
                temperature=0,
                stream=True,
            )

    def _create_openai_client(self) -> OpenAI:
        """根据配置创建 OpenAI SDK 客户端。"""
        settings = get_settings()
        return OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )

    def _build_messages(
        self, prompt: str, system_message: str | None
    ) -> list[dict[str, str]]:
        """构造 Chat Completions 所需的 system + user 消息。"""
        return [
            {"role": "system", "content": system_message or DEFAULT_SYSTEM_MESSAGE},
            {"role": "user", "content": prompt},
        ]

    def _extract_usage_tokens(self, usage: Any | None) -> tuple[int | None, int | None]:
        """从 OpenAI SDK usage 对象中提取 token 用量。"""
        if usage is None:
            return None, None
        return (
            getattr(usage, "prompt_tokens", None),
            getattr(usage, "completion_tokens", None),
        )

    def _record_call(
        self,
        prompt: str,
        node_name: str,
        run_id: UUID,
        trace_id: UUID,
        task_id: UUID | None,
        result: LLMResult,
    ) -> None:
        """将 LLM 调用结果写入 `llm_calls`。"""
        record = LLMCallRecord(
            task_id=task_id,
            run_id=run_id,
            trace_id=trace_id,
            node_name=node_name,
            provider=result.provider,
            model=result.model,
            prompt=prompt,
            response=result.text or None,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            duration_ms=result.duration_ms,
            status=result.status,
            error_message=result.error_message,
        )
        with get_connection() as connection:
            LLMCallRepository(connection).create(record)

    def _should_use_mock_response(self) -> bool:
        """判断是否启用 mock 模式。"""
        settings = get_settings()
        return (
            not settings.llm_api_key
            or settings.llm_api_key == "your_api_key"
            or "api.example.com" in settings.llm_base_url
        )

    def _mock_complete(
        self,
        prompt: str,
        model: str,
        started_at: float,
    ) -> LLMResult:
        """生成 mock LLMResult。"""
        settings = get_settings()
        text = self._mock_intent_response(prompt)
        return LLMResult(
            text=text,
            provider=f"{settings.llm_provider}:mock",
            model=model,
            input_tokens=self._estimate_tokens_for_mock(prompt),
            output_tokens=self._estimate_tokens_for_mock(text),
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            status="SUCCESS",
        )

    def _failed_result(
        self,
        provider: str,
        model: str,
        started_at: float,
        exc: Exception,
    ) -> LLMResult:
        """统一构造失败结果。"""
        error_type = exc.__class__.__name__
        return LLMResult(
            text="",
            provider=provider,
            model=model,
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            status="FAILED",
            error_message=f"{error_type}: {exc}",
        )

    def _estimate_tokens_for_mock(self, text: str) -> int:
        """粗略估算 mock 模式下的 token 数。

        真实 LLM 调用必须使用服务端 usage；这个估算只用于 mock。
        """
        return max(1, len(text) // 4)

    def _mock_intent_response(self, prompt: str) -> str:
        """根据 prompt 关键词生成 mock 意图识别结果。"""
        if '"output_schema"' in prompt and '"planning_rules"' in prompt:
            return self._mock_plan_response(prompt)
        if "final_answer" in prompt and "summary_type" in prompt:
            return self._mock_summary_response(prompt)

        user_input = self._extract_mock_user_input(prompt)
        lower_user_input = user_input.lower()
        if "python" in lower_user_input or "print(" in lower_user_input:
            code_match = re.search(r"(print\(.*\)|sum\(.*\))", user_input)
            intent = {
                "intent": "RUN_CODE",
                "summary": "用户想运行 Python 代码。",
                "confidence": 0.9,
                "risk_hint": "HIGH",
                "suggested_tool_type": "SANDBOX",
                "tool_input": {
                    "language": "python",
                    "code_hint": code_match.group(1) if code_match else None,
                },
            }
        elif "git status" in lower_user_input or "git 状态" in lower_user_input:
            intent = {
                "intent": "CLI_EXECUTION",
                "summary": "用户想查看 git 状态。",
                "confidence": 0.85,
                "risk_hint": "MEDIUM",
                "suggested_tool_type": "CLI",
                "tool_input": {"command": "git status"},
            }
        elif "http" in lower_user_input or "echo" in lower_user_input:
            intent = {
                "intent": "HTTP_CALL",
                "summary": "用户想调用 HTTP 工具。",
                "confidence": 0.75,
                "risk_hint": "LOW",
                "suggested_tool_type": "HTTP",
                "tool_input": {},
            }
        else:
            intent = {
                "intent": "GENERAL_QUERY",
                "summary": "用户意图需要进一步分析。",
                "confidence": 0.5,
                "risk_hint": "LOW",
                "suggested_tool_type": None,
                "tool_input": {},
            }
        return json.dumps(intent, ensure_ascii=False)

    def _extract_mock_user_input(self, prompt: str) -> str:
        """从 intent prompt 中提取用户输入，避免可用工具摘要影响 mock 判断。"""
        marker = "用户输入："
        if marker not in prompt:
            return prompt
        user_part = prompt.split(marker, 1)[1]
        end_marker = "请只返回 JSON"
        if end_marker in user_part:
            user_part = user_part.split(end_marker, 1)[0]
        return user_part.strip()

    def _mock_summary_response(self, prompt: str) -> str:
        """根据 prompt 关键词生成 mock 结果总结。"""
        if '"summary_type": "DENIED"' in prompt:
            summary = {
                "final_answer": "任务没有执行，因为权限检查未通过。请确认运行模式或工具风险等级后重试。",
                "summary_type": "DENIED",
                "next_action": "切换到允许的运行模式或选择低风险工具。",
            }
        elif '"summary_type": "WAITING_APPROVAL"' in prompt:
            summary = {
                "final_answer": "任务已暂停，正在等待人工审批。审批通过后任务会继续执行。",
                "summary_type": "WAITING_APPROVAL",
                "next_action": "请在审批列表中处理该请求。",
            }
        elif '"summary_type": "NO_TOOL"' in prompt:
            summary = {
                "final_answer": "当前没有可用工具可以处理这个请求，请先注册合适的工具或调整输入描述。",
                "summary_type": "NO_TOOL",
                "next_action": "注册工具或重新描述需求。",
            }
        elif '"summary_type": "PLANNED"' in prompt:
            summary = {
                "final_answer": "已生成执行计划，PLAN_ONLY 模式不会执行工具。",
                "summary_type": "PLANNED",
                "next_action": "切换到 SAFE_EXECUTE 或 FULL_EXECUTE 后可执行。",
            }
        elif '"summary_type": "FAILED"' in prompt:
            summary = {
                "final_answer": "工具执行失败，请查看 stderr、error_message 和任务事件获取具体原因。",
                "summary_type": "FAILED",
                "next_action": "查看工具调用日志后重试。",
            }
        else:
            summary = {
                "final_answer": "任务已完成，工具执行结果已经写入任务结果和审计日志。",
                "summary_type": "SUCCESS",
                "next_action": "NONE",
            }
        return json.dumps(summary, ensure_ascii=False)

    def _mock_plan_response(self, prompt: str) -> str:
        """根据 planner prompt 生成稳定的 mock 多步计划。"""
        user_input = self._extract_mock_planner_user_input(prompt)
        lower_user_input = user_input.lower()
        steps: list[dict[str, Any]] = []

        if "git" in lower_user_input:
            if "status" in lower_user_input or "状态" in user_input:
                steps.append(
                    {
                        "objective": "查看 Git 工作区状态",
                        "intent": "CLI_EXECUTION",
                        "suggested_tool_type": "CLI",
                        "tool_input": {
                            "rule_id": "cli://git/status-short",
                            "args": {},
                        },
                    }
                )
            if "diff" in lower_user_input or "变更" in user_input or "差异" in user_input:
                steps.append(
                    {
                        "objective": "查看 Git 工作区 diff",
                        "intent": "CLI_EXECUTION",
                        "suggested_tool_type": "CLI",
                        "tool_input": {
                            "rule_id": "cli://git/diff",
                            "args": {"path": ".", "staged": False},
                        },
                    }
                )
            if "log" in lower_user_input or "提交历史" in user_input:
                steps.append(
                    {
                        "objective": "查看 Git 最近提交历史",
                        "intent": "CLI_EXECUTION",
                        "suggested_tool_type": "CLI",
                        "tool_input": {
                            "rule_id": "cli://git/log-oneline",
                            "args": {"max_count": 5},
                        },
                    }
                )

        if not steps and ("python" in lower_user_input or "print(" in lower_user_input):
            code_match = re.search(r"(print\(.*\)|sum\(.*\))", user_input)
            steps.append(
                {
                    "objective": "在沙箱中运行 Python 代码",
                    "intent": "RUN_CODE",
                    "suggested_tool_type": "SANDBOX",
                    "tool_input": {
                        "language": "python",
                        "code": code_match.group(1) if code_match else user_input,
                    },
                }
            )

        if not steps and ("http" in lower_user_input or "echo" in lower_user_input):
            steps.append(
                {
                    "objective": "调用 HTTP 工具",
                    "intent": "HTTP_CALL",
                    "suggested_tool_type": "HTTP",
                    "tool_input": {"method": "GET", "params": {"q": user_input}},
                }
            )

        if not steps:
            steps.append(
                {
                    "objective": user_input,
                    "intent": "GENERAL_QUERY",
                    "suggested_tool_type": None,
                    "tool_input": {},
                }
            )

        return json.dumps(
            {
                "steps": steps[:3],
                "reason": "mock planner 根据用户输入和可用工具摘要生成稳定计划。",
            },
            ensure_ascii=False,
        )

    def _extract_mock_planner_user_input(self, prompt: str) -> str:
        """从 JSON planner prompt 中提取用户输入。"""
        try:
            payload = json.loads(prompt)
        except json.JSONDecodeError:
            return prompt
        return str(payload.get("user_input") or prompt)
