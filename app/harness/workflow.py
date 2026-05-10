from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any, TypedDict
from uuid import UUID

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph

from app.common.config import get_settings
from app.context.instruction_loader import InstructionLoader
from app.harness.replanner import HarnessReplanner
from app.harness.step_planner import HarnessStepPlanner
from app.harness.tool_input_normalizer import ToolInputNormalizer
from app.llm.intent_service import IntentService
from app.llm.result_summarizer_service import ResultSummarizerService
from app.repositories.db import get_connection
from app.repositories.task_event_repository import TaskEventRepository
from app.repositories.task_repository import TaskRepository
from app.schemas.permission import RunMode
from app.schemas.tool import ToolResponse
from app.security.permission_engine import PermissionEngine
from app.services.approval_service import ApprovalService
from app.services.tool_router_service import ToolRouterService
from app.tools.dispatcher import ToolAdapterDispatcher


class HarnessState(TypedDict, total=False):
    """LangGraph 中流转的 Harness 状态。"""

    task_id: str
    run_id: str
    trace_id: str
    user_input: str
    run_mode: str
    user_id: str
    workspace_id: str
    instructions_ref: str
    instructions_hash: str
    instructions_length: int
    intent: dict[str, Any]
    route: dict[str, Any]
    permission: dict[str, Any] | None
    tool_input: dict[str, Any]
    tool_result: dict[str, Any] | None
    plan: dict[str, Any]
    steps: list[dict[str, Any]]
    current_step_index: int
    max_steps: int
    max_retries: int
    timeout_seconds: int | None
    deadline_at: str | None
    observations: list[dict[str, Any]]
    stop_reason: str | None
    summary: dict[str, Any]
    final_status: str
    error_message: str | None


class AgentHarnessWorkflow:
    """Agent Harness 工作流：规划、路由、权限、执行、观察、重试和总结。"""

    def __init__(self) -> None:
        self.instruction_loader = InstructionLoader()
        self.intent_service = IntentService()
        self.tool_router_service = ToolRouterService()
        self.permission_engine = PermissionEngine()
        self.approval_service = ApprovalService()
        self.dispatcher = ToolAdapterDispatcher()
        self.tool_input_normalizer = ToolInputNormalizer()
        self.step_planner = HarnessStepPlanner()
        self.replanner = HarnessReplanner()
        self.result_summarizer = ResultSummarizerService()

    def run(self, task: dict[str, Any]) -> HarnessState:
        """用 PostgresSaver checkpoint 执行一次 LangGraph workflow。"""
        run_config = self._run_config(task)
        timeout_seconds = run_config.get("timeout_seconds")
        deadline_at = (
            datetime.now(timezone.utc) + timedelta(seconds=timeout_seconds)
        ).isoformat() if timeout_seconds else None
        initial_state: HarnessState = {
            "task_id": str(task["id"]),
            "run_id": str(task["run_id"]),
            "trace_id": str(task["trace_id"]),
            "user_input": task["user_input"],
            "run_mode": task["run_mode"],
            "user_id": task.get("user_id", "local-user"),
            "workspace_id": task.get("workspace_id", "default"),
            "final_status": "RUNNING",
            "current_step_index": 0,
            "max_steps": run_config["max_steps"],
            "max_retries": run_config["max_retries"],
            "timeout_seconds": timeout_seconds,
            "deadline_at": deadline_at,
            "observations": [],
            "stop_reason": None,
        }
        config = {"configurable": {"thread_id": str(task["run_id"])}}

        with PostgresSaver.from_conn_string(get_settings().database_url) as checkpointer:
            checkpointer.setup()
            graph = self._build_graph().compile(checkpointer=checkpointer)
            return graph.invoke(initial_state, config=config)

    def _build_graph(self) -> StateGraph:
        """构建 LangGraph 节点和边。"""
        graph = StateGraph(HarnessState)
        graph.add_node("load_instructions", self._wrap_node("load_instructions", self._load_instructions))
        graph.add_node("understand_intent", self._wrap_node("understand_intent", self._understand_intent))
        graph.add_node("make_plan", self._wrap_node("make_plan", self._make_plan))
        graph.add_node("select_tool", self._wrap_node("select_tool", self._select_tool))
        graph.add_node("check_permission", self._wrap_node("check_permission", self._check_permission))
        graph.add_node("execute_tool", self._wrap_node("execute_tool", self._execute_tool))
        graph.add_node("observe_result", self._wrap_node("observe_result", self._observe_result))
        graph.add_node("decide_next_step", self._wrap_node("decide_next_step", self._decide_next_step))
        graph.add_node("summarize_result", self._wrap_node("summarize_result", self._summarize_result))

        graph.add_edge(START, "load_instructions")
        graph.add_edge("load_instructions", "understand_intent")
        graph.add_edge("understand_intent", "make_plan")
        graph.add_conditional_edges(
            "make_plan",
            self._next_after_plan,
            {"execute": "select_tool", "summarize": "summarize_result"},
        )
        graph.add_edge("select_tool", "check_permission")
        graph.add_edge("check_permission", "execute_tool")
        graph.add_edge("execute_tool", "observe_result")
        graph.add_edge("observe_result", "decide_next_step")
        graph.add_conditional_edges(
            "decide_next_step",
            self._next_after_decision,
            {"continue": "select_tool", "summarize": "summarize_result"},
        )
        graph.add_edge("summarize_result", END)
        return graph

    def _load_instructions(self, state: HarnessState) -> dict[str, Any]:
        """加载项目规则，给后续 LLM 节点提供约束上下文。"""
        instructions = self.instruction_loader.load()
        instructions_hash = hashlib.sha256(instructions.encode("utf-8")).hexdigest()
        self._record_event(
            state,
            event_type="INSTRUCTIONS_LOADED",
            step="load_instructions",
            message="已加载 TOOLHUB.md 项目规则。",
            payload={
                "instructions_ref": "TOOLHUB.md",
                "length": len(instructions),
                "sha256": instructions_hash,
            },
        )
        return {
            "instructions_ref": "TOOLHUB.md",
            "instructions_hash": instructions_hash,
            "instructions_length": len(instructions),
        }

    def _understand_intent(self, state: HarnessState) -> dict[str, Any]:
        """理解用户意图。"""
        intent = self.intent_service.understand_intent(
            state["user_input"],
            run_mode=state["run_mode"],
            task_id=UUID(state["task_id"]),
            run_id=UUID(state["run_id"]),
            trace_id=UUID(state["trace_id"]),
        )
        payload = intent.model_dump(mode="json")
        self._record_event(
            state,
            event_type="INTENT_UNDERSTOOD",
            step="understand_intent",
            message=f"已识别用户意图：{intent.intent}。",
            payload=payload,
        )
        return {"intent": payload, "tool_input": payload.get("tool_input") or {}}

    def _make_plan(self, state: HarnessState) -> dict[str, Any]:
        """生成本次任务的多步执行计划。"""
        intent = state.get("intent") or {}
        max_steps = int(state.get("max_steps", HarnessStepPlanner.DEFAULT_MAX_STEPS))
        steps = self.step_planner.create_steps(
            user_input=state["user_input"],
            intent=intent,
            run_mode=state["run_mode"],
            task_id=UUID(state["task_id"]),
            run_id=UUID(state["run_id"]),
            trace_id=UUID(state["trace_id"]),
            max_steps=max_steps,
        )
        plan = {
            "steps": steps,
            "max_steps": max_steps,
            "max_retries": state.get("max_retries", 0),
            "timeout_seconds": state.get("timeout_seconds"),
            "planner": self.step_planner.last_planner,
            "fallback_used": self.step_planner.last_fallback_used,
            "warnings": self.step_planner.last_warnings,
            "raw_response": self.step_planner.last_raw_response,
        }
        is_plan_only = state["run_mode"] == RunMode.PLAN_ONLY.value
        self._record_event(
            state,
            event_type="PLAN_CREATED",
            step="make_plan",
            message=(
                f"已生成执行计划，共 {len(steps)} 个步骤。"
                if not is_plan_only
                else f"PLAN_ONLY 模式已生成执行计划，共 {len(steps)} 个步骤，不会执行工具。"
            ),
            payload=plan,
        )
        first_step = steps[0] if steps else {}
        output: dict[str, Any] = {
            "plan": plan,
            "steps": steps,
            "current_step_index": 0,
            "tool_input": first_step.get("tool_input") or state.get("tool_input") or {},
        }
        if is_plan_only:
            output["final_status"] = "PLANNED"
            output["stop_reason"] = "PLAN_ONLY 模式只生成计划，不执行工具。"
        return output

    def _select_tool(self, state: HarnessState) -> dict[str, Any]:
        """为当前步骤选择工具。"""
        if terminal := self._terminal_guard(state, "select_tool"):
            return terminal

        intent = state.get("intent") or {}
        current_step = self._current_step(state)
        route = self.tool_router_service.select_tool(
            user_input=current_step.get("objective") or state["user_input"],
            intent=current_step.get("intent") or intent.get("intent"),
            suggested_tool_type=current_step.get("suggested_tool_type") or intent.get("suggested_tool_type"),
            tool_input=current_step.get("tool_input") or state.get("tool_input") or {},
            enable_llm_rerank=True,
            task_id=UUID(state["task_id"]),
            run_id=UUID(state["run_id"]),
            trace_id=UUID(state["trace_id"]),
        )
        payload = route.model_dump(mode="json")
        selected_tool_id = route.selected_tool.id if route.selected_tool else None
        with get_connection() as connection:
            TaskRepository(connection).update_status(
                task_id=UUID(state["task_id"]),
                status="RUNNING",
                current_step="select_tool",
                selected_tool_id=selected_tool_id,
            )
        self._record_event(
            state,
            event_type="TOOL_SELECTED" if route.selected_tool else "TOOL_ROUTING_FAILED",
            step="select_tool",
            message=route.reason,
            payload={
                "step_index": state.get("current_step_index", 0),
                "step_objective": current_step.get("objective"),
                "route": payload,
            },
        )
        return {
            "route": payload,
            "tool_input": current_step.get("tool_input") or state.get("tool_input") or {},
        }

    def _check_permission(self, state: HarnessState) -> dict[str, Any]:
        """检查当前工具调用是否允许执行。"""
        if terminal := self._terminal_guard(state, "check_permission"):
            return terminal

        selected_tool = self._selected_tool_from_state(state)
        if selected_tool is None:
            self._record_event(
                state,
                event_type="NO_TOOL",
                step="check_permission",
                message="没有可执行工具，任务结束。",
            )
            return {"permission": None, "final_status": "NO_TOOL"}

        permission = self.permission_engine.check(
            selected_tool,
            RunMode(state["run_mode"]),
            user_id=state.get("user_id"),
            workspace_id=state.get("workspace_id"),
        )
        payload = permission.model_dump(mode="json")
        permission_event_type = (
            "PERMISSION_ALLOWED"
            if permission.allowed
            else "PERMISSION_ASKED"
            if permission.decision.value == "ASK"
            else "PERMISSION_DENIED"
        )
        self._record_event(
            state,
            event_type=permission_event_type,
            step="check_permission",
            message=permission.reason,
            payload={"step_index": state.get("current_step_index", 0), "permission": payload},
        )
        if permission.decision.value == "ASK":
            approval = self.approval_service.create_or_get_pending(
                task_id=UUID(state["task_id"]),
                run_id=UUID(state["run_id"]),
                trace_id=UUID(state["trace_id"]),
                tool_id=selected_tool.id,
                requested_action=f"execute:{selected_tool.name}",
                reason=permission.reason,
                requested_by=state.get("user_id", "harness"),
                workspace_id=state.get("workspace_id", "default"),
            )
            return {
                "permission": {
                    **payload,
                    "approval_id": str(approval.id),
                    "approval_status": approval.status.value,
                },
                "final_status": "WAITING_APPROVAL",
            }
        return {
            "permission": payload,
            "final_status": "RUNNING" if permission.allowed else "DENIED",
        }

    def _execute_tool(self, state: HarnessState) -> dict[str, Any]:
        """执行当前步骤选择出的工具。"""
        if terminal := self._terminal_guard(state, "execute_tool"):
            return terminal

        selected_tool = self._selected_tool_from_state(state)
        permission = state.get("permission")
        if selected_tool is None:
            return {"tool_result": None, "final_status": "NO_TOOL"}
        if not permission or not permission.get("allowed"):
            if permission and permission.get("decision") == "ASK":
                self._record_event(
                    state,
                    event_type="TASK_WAITING_APPROVAL",
                    step="execute_tool",
                    message="权限检查需要人工审批，任务暂停执行。",
                    payload={"permission": permission},
                )
                return {"tool_result": None, "final_status": "WAITING_APPROVAL"}
            self._record_event(
                state,
                event_type="TASK_DENIED",
                step="execute_tool",
                message="权限检查未通过，跳过工具执行。",
                payload={"permission": permission},
            )
            return {"tool_result": None, "final_status": "DENIED"}

        tool_input = self.tool_input_normalizer.normalize(
            tool=selected_tool,
            tool_input=state.get("tool_input") or {},
        )
        result = self.dispatcher.dispatch(
            tool=selected_tool,
            tool_input=tool_input,
            task_id=UUID(state["task_id"]),
            run_id=UUID(state["run_id"]),
            trace_id=UUID(state["trace_id"]),
            user_id=state.get("user_id"),
            workspace_id=state.get("workspace_id"),
        )
        payload = result.model_dump(mode="json")
        self._record_event(
            state,
            event_type="TOOL_EXECUTED" if result.success else "TOOL_EXECUTION_FAILED",
            step="execute_tool",
            message="工具执行完成。" if result.success else result.error_message,
            payload={"step_index": state.get("current_step_index", 0), "tool_call": payload},
        )
        return {
            "tool_input": tool_input,
            "tool_result": payload,
            "final_status": "SUCCESS" if result.success else "FAILED",
            "error_message": result.error_message,
        }

    def _observe_result(self, state: HarnessState) -> dict[str, Any]:
        """记录当前步骤 observation，供下一步和最终总结使用。"""
        observations = list(state.get("observations") or [])
        steps = list(state.get("steps") or [])
        step_index = int(state.get("current_step_index", 0))
        current_step = self._current_step(state)
        final_status = state.get("final_status", "FAILED")
        observation = {
            "step_index": step_index,
            "objective": current_step.get("objective"),
            "status": final_status,
            "route": state.get("route"),
            "permission": state.get("permission"),
            "tool_input": state.get("tool_input"),
            "tool_result": state.get("tool_result"),
            "error_message": state.get("error_message"),
        }
        observations.append(observation)

        if 0 <= step_index < len(steps):
            steps[step_index] = {
                **steps[step_index],
                "status": final_status,
                "observation_index": len(observations) - 1,
            }

        self._record_event(
            state,
            event_type="TOOL_OBSERVED",
            step="observe_result",
            message=f"已记录第 {step_index + 1} 步观察结果：{final_status}。",
            payload=observation,
        )
        return {"observations": observations, "steps": steps}

    def _decide_next_step(self, state: HarnessState) -> dict[str, Any]:
        """根据 observation 决定重试、继续下一步或总结。"""
        if terminal := self._terminal_guard(state, "decide_next_step"):
            return terminal

        steps = list(state.get("steps") or [])
        current_index = int(state.get("current_step_index", 0))
        final_status = state.get("final_status", "FAILED")

        if final_status != "SUCCESS":
            if self._can_retry(state, final_status):
                return self._retry_current_step(state, steps, current_index)
            stop_reason = f"第 {current_index + 1} 步状态为 {final_status}，停止后续执行。"
            self._record_event(
                state,
                event_type="NEXT_STEP_DECIDED",
                step="decide_next_step",
                message=stop_reason,
                payload={"next_action": "summarize", "stop_reason": stop_reason},
            )
            return {"stop_reason": stop_reason}

        next_index = current_index + 1
        if next_index >= len(steps):
            stop_reason = "所有计划步骤已完成。"
            self._record_event(
                state,
                event_type="NEXT_STEP_DECIDED",
                step="decide_next_step",
                message=stop_reason,
                payload={"next_action": "summarize", "stop_reason": stop_reason},
            )
            return {"stop_reason": stop_reason}

        if next_index >= int(state.get("max_steps", HarnessStepPlanner.DEFAULT_MAX_STEPS)):
            stop_reason = "已达到最大步骤数限制。"
            self._record_event(
                state,
                event_type="NEXT_STEP_DECIDED",
                step="decide_next_step",
                message=stop_reason,
                payload={"next_action": "summarize", "stop_reason": stop_reason},
            )
            return {"stop_reason": stop_reason}

        next_step = steps[next_index]
        message = f"继续执行第 {next_index + 1} 步：{next_step.get('objective')}。"
        self._record_event(
            state,
            event_type="NEXT_STEP_DECIDED",
            step="decide_next_step",
            message=message,
            payload={"next_action": "continue", "next_step_index": next_index, "next_step": next_step},
        )
        return {
            "current_step_index": next_index,
            "tool_input": next_step.get("tool_input") or {},
            "route": {},
            "permission": None,
            "tool_result": None,
            "error_message": None,
            "final_status": "RUNNING",
            "stop_reason": None,
        }

    def _summarize_result(self, state: HarnessState) -> dict[str, Any]:
        """把结构化执行结果总结成用户可读答案。"""
        tool_result = self._summary_tool_result(state)
        summary = self.result_summarizer.summarize(
            user_input=state["user_input"],
            status=state.get("final_status", "FAILED"),
            intent=state.get("intent"),
            route=state.get("route"),
            permission=state.get("permission"),
            tool_input=state.get("tool_input"),
            tool_result=tool_result,
            task_id=UUID(state["task_id"]),
            run_id=UUID(state["run_id"]),
            trace_id=UUID(state["trace_id"]),
        )
        payload = summary.model_dump(mode="json")
        self._record_event(
            state,
            event_type="RESULT_SUMMARIZED",
            step="summarize_result",
            message="已生成最终答案。",
            payload=payload,
        )
        return {"summary": payload}

    def _next_after_decision(self, state: HarnessState) -> str:
        """LangGraph 条件边：决定继续执行还是总结。"""
        if state.get("final_status") == "RUNNING":
            return "continue"
        return "summarize"

    def _next_after_plan(self, state: HarnessState) -> str:
        """LangGraph 条件边：PLAN_ONLY 只总结计划，其余模式继续执行。"""
        if state.get("final_status") == "PLANNED":
            return "summarize"
        return "execute"

    def _current_step(self, state: HarnessState) -> dict[str, Any]:
        """获取当前计划步骤。"""
        steps = state.get("steps") or []
        step_index = int(state.get("current_step_index", 0))
        if 0 <= step_index < len(steps):
            return steps[step_index]
        return {}

    def _summary_tool_result(self, state: HarnessState) -> dict[str, Any] | None:
        """为 ResultSummarizer 聚合多步 observation。"""
        observations = state.get("observations") or []
        if not observations:
            if state.get("final_status") == "PLANNED":
                return {
                    "success": True,
                    "status": "PLANNED",
                    "output": {"steps": state.get("steps") or [], "stop_reason": state.get("stop_reason")},
                    "error_message": None,
                }
            return state.get("tool_result")
        return {
            "success": state.get("final_status") == "SUCCESS",
            "status": state.get("final_status"),
            "output": {
                "observations": observations,
                "steps": state.get("steps") or [],
                "stop_reason": state.get("stop_reason"),
            },
            "error_message": state.get("error_message"),
        }

    def _selected_tool_from_state(self, state: HarnessState) -> ToolResponse | None:
        """从路由结果中提取工具对象。"""
        route = state.get("route") or {}
        selected_tool = route.get("selected_tool")
        if not selected_tool:
            return None
        return ToolResponse.model_validate(selected_tool)

    def _can_retry(self, state: HarnessState, final_status: str) -> bool:
        """判断当前失败是否允许自动重试。"""
        if final_status not in {"FAILED"}:
            return False
        current_step = self._current_step(state)
        retry_count = int(current_step.get("retry_count", 0))
        return retry_count < int(state.get("max_retries", 0))

    def _retry_current_step(
        self,
        state: HarnessState,
        steps: list[dict[str, Any]],
        current_index: int,
    ) -> dict[str, Any]:
        """基于最近 observation 修正当前步骤输入，并重新进入路由和权限链路。"""
        current_step = dict(self._current_step(state))
        retry_count = int(current_step.get("retry_count", 0)) + 1
        latest_observation = (state.get("observations") or [{}])[-1]
        replanned_step = self.replanner.replan_step(
            user_input=state["user_input"],
            current_step=current_step,
            observation=latest_observation,
            retry_count=retry_count,
            max_retries=int(state.get("max_retries", 0)),
            task_id=UUID(state["task_id"]),
            run_id=UUID(state["run_id"]),
            trace_id=UUID(state["trace_id"]),
        )
        replanned_step = {
            **replanned_step,
            "retry_count": retry_count,
            "status": "RETRYING",
        }
        if 0 <= current_index < len(steps):
            steps[current_index] = replanned_step

        with get_connection() as connection:
            TaskRepository(connection).increment_retry_count(UUID(state["task_id"]))

        self._record_event(
            state,
            event_type="STEP_RETRY_PLANNED",
            step="decide_next_step",
            message=f"第 {current_index + 1} 步失败后准备第 {retry_count} 次重试。",
            payload={
                "step_index": current_index,
                "retry_count": retry_count,
                "max_retries": state.get("max_retries"),
                "replanner_fallback_used": self.replanner.last_fallback_used,
                "replan_reason": self.replanner.last_reason,
                "replanned_step": replanned_step,
            },
        )
        return {
            "steps": steps,
            "tool_input": replanned_step.get("tool_input") or {},
            "route": {},
            "permission": None,
            "tool_result": None,
            "error_message": None,
            "final_status": "RUNNING",
            "stop_reason": None,
        }

    def _run_config(self, task: dict[str, Any]) -> dict[str, Any]:
        """读取任务级运行参数，兼容旧任务记录。"""
        raw_config = dict(task.get("run_config") or {})
        return {
            "max_steps": int(raw_config.get("max_steps") or HarnessStepPlanner.DEFAULT_MAX_STEPS),
            "max_retries": int(raw_config.get("max_retries") if raw_config.get("max_retries") is not None else task.get("max_retries", 1)),
            "timeout_seconds": raw_config.get("timeout_seconds"),
        }

    def _terminal_guard(self, state: HarnessState, step: str) -> dict[str, Any] | None:
        """在节点边界检查取消和超时，避免继续进入工具执行。"""
        if state.get("final_status") in {"CANCELLED", "TIMEOUT"}:
            return {"final_status": state["final_status"], "stop_reason": state.get("stop_reason")}
        if self._is_timed_out(state):
            stop_reason = "任务已超过 run_config.timeout_seconds 限制。"
            self._record_event(
                state,
                event_type="TASK_TIMEOUT",
                step=step,
                message=stop_reason,
                payload={"deadline_at": state.get("deadline_at")},
            )
            return {"final_status": "TIMEOUT", "stop_reason": stop_reason, "error_message": stop_reason}
        if self._is_cancel_requested(state):
            stop_reason = "任务已收到取消请求。"
            self._record_event(
                state,
                event_type="TASK_CANCELLED",
                step=step,
                message=stop_reason,
                payload={"step": step},
            )
            return {"final_status": "CANCELLED", "stop_reason": stop_reason, "error_message": stop_reason}
        return None

    def _is_timed_out(self, state: HarnessState) -> bool:
        """检查任务级 deadline 是否已经到达。"""
        deadline_at = state.get("deadline_at")
        if not deadline_at:
            return False
        try:
            deadline = datetime.fromisoformat(deadline_at)
        except ValueError:
            return False
        return datetime.now(timezone.utc) >= deadline

    def _is_cancel_requested(self, state: HarnessState) -> bool:
        """从数据库读取取消标记，确保外部 API 能打断后续节点。"""
        with get_connection() as connection:
            task = TaskRepository(connection).get_by_id(UUID(state["task_id"]))
        return bool(task and task.get("cancel_requested"))

    def _record_event(
        self,
        state: HarnessState,
        *,
        event_type: str,
        step: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """记录任务事件，同时把主任务 current_step 更新到当前节点。"""
        with get_connection() as connection:
            TaskRepository(connection).update_status(
                task_id=UUID(state["task_id"]),
                status="RUNNING",
                current_step=step,
            )
            TaskEventRepository(connection).create(
                task_id=UUID(state["task_id"]),
                run_id=UUID(state["run_id"]),
                trace_id=UUID(state["trace_id"]),
                event_type=event_type,
                step=step,
                message=message,
                payload=payload,
                user_id=state.get("user_id"),
                workspace_id=state.get("workspace_id"),
            )

    def _wrap_node(
        self,
        step: str,
        node: Callable[[HarnessState], dict[str, Any]],
    ) -> Callable[[HarnessState], dict[str, Any]]:
        """统一包装 LangGraph 节点，失败时写入节点级审计事件。"""
        def wrapped(state: HarnessState) -> dict[str, Any]:
            try:
                return node(state)
            except Exception as exc:
                self._record_node_failure(state, step, exc)
                raise

        return wrapped

    def _record_node_failure(
        self,
        state: HarnessState,
        step: str,
        exc: Exception,
    ) -> None:
        """记录节点失败，便于 Dashboard 定位失败位置。"""
        error_message = f"{exc.__class__.__name__}: {exc}"
        with get_connection() as connection:
            TaskRepository(connection).update_status(
                task_id=UUID(state["task_id"]),
                status="FAILED",
                current_step=step,
                error_message=error_message,
            )
            TaskEventRepository(connection).create(
                task_id=UUID(state["task_id"]),
                run_id=UUID(state["run_id"]),
                trace_id=UUID(state["trace_id"]),
                event_type="NODE_FAILED",
                step=step,
                message=error_message,
                payload={"node": step, "error_type": exc.__class__.__name__},
                user_id=state.get("user_id"),
                workspace_id=state.get("workspace_id"),
            )
