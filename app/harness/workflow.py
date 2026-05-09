from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any, TypedDict
from uuid import UUID

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph

from app.common.config import get_settings
from app.context.instruction_loader import InstructionLoader
from app.harness.step_planner import HarnessStepPlanner
from app.harness.tool_input_normalizer import ToolInputNormalizer
from app.llm.intent_service import IntentService
from app.llm.result_summarizer_service import ResultSummarizerService
from app.repositories.db import get_connection
from app.repositories.task_event_repository import TaskEventRepository
from app.repositories.task_repository import TaskRepository
from app.schemas.permission import RunMode
from app.services.approval_service import ApprovalService
from app.schemas.tool import ToolResponse
from app.security.permission_engine import PermissionEngine
from app.services.tool_router_service import ToolRouterService
from app.tools.dispatcher import ToolAdapterDispatcher


class HarnessState(TypedDict, total=False):
    """LangGraph 中流转的 Harness 状态。"""

    task_id: str                        # 任务的唯一标识
    run_id: str                         # 单次运行的标识（同一任务可能多次运行）
    trace_id: str                       # 分布式追踪ID，用于日志关联
    user_input: str                     # 用户原始输入文本
    run_mode: str                       # 运行模式（如 "auto", "manual"）
    instructions_ref: str               # 项目规则引用，避免完整内容进入 checkpoint
    instructions_hash: str              # 项目规则内容哈希
    instructions_length: int            # 项目规则长度
    intent: dict[str, Any]              # LLM 识别的结构化意图
    route: dict[str, Any]               # 工具路由决策结果
    permission: dict[str, Any] | None   # 权限检查结果
    tool_input: dict[str, Any]          # 传递给工具的参数
    tool_result: dict[str, Any] | None  # 工具执行结果
    plan: dict[str, Any]                # 多步执行计划
    steps: list[dict[str, Any]]         # 计划中的步骤列表
    current_step_index: int             # 当前执行步骤下标
    max_steps: int                      # 单次任务最多执行步骤数
    observations: list[dict[str, Any]]  # 每步执行后的观察结果
    stop_reason: str | None             # 多步循环停止原因
    summary: dict[str, Any]             # LLM 生成的最终用户答案
    final_status: str                   # 最终状态（SUCCESS/FAILED/DENIED等）
    error_message: str | None           #  错误信息


class AgentHarnessWorkflow:
    """ Agent Harness 工作流。

    当前实现一条线性 LangGraph 链路：
    load_instructions -> understand_intent -> select_tool -> check_permission -> execute_tool -> summarize_result。
    后面 会继续补 多步 Agent loop。
    """

    def __init__(self) -> None:
        self.instruction_loader = InstructionLoader() # 加载项目规则（TOOLHUB.md）
        self.intent_service = IntentService() # 理解用户意图
        self.tool_router_service = ToolRouterService() # 选择合适的工具
        self.permission_engine = PermissionEngine() # 权限检查
        self.approval_service = ApprovalService() # 人工审批请求
        self.dispatcher = ToolAdapterDispatcher() # 分发并执行工具
        self.tool_input_normalizer = ToolInputNormalizer() # 归一化 LLM 生成的工具参数
        self.step_planner = HarnessStepPlanner() # 生成多步执行计划
        self.result_summarizer = ResultSummarizerService() # 总结工具结果并生成最终答案

    def run(self, task: dict[str, Any]) -> HarnessState:
        """用 PostgresSaver checkpoint 执行一次 LangGraph workflow。"""
        initial_state: HarnessState = {
            "task_id": str(task["id"]),
            "run_id": str(task["run_id"]),
            "trace_id": str(task["trace_id"]),
            "user_input": task["user_input"],
            "run_mode": task["run_mode"],
            "final_status": "RUNNING", # 初始状态设为运行中
            "current_step_index": 0,
            "max_steps": HarnessStepPlanner.DEFAULT_MAX_STEPS,
            "observations": [],
            "stop_reason": None,
        }
        # LangGraph 使用 thread_id 作为状态存储的键
        # 同一个 run_id 的多次调用会共享状态历史
        # 支持时间旅行调试：可以查看任意时刻的状态快照
        config = {"configurable": {"thread_id": str(task["run_id"])}}

        # 创建连接: 从配置获取数据库URL，创建 PostgreSQL 连接
        with PostgresSaver.from_conn_string(get_settings().database_url) as checkpointer:
            # 初始化表结构: setup() 创建 checkpoint 所需的表（如果不存在）
            checkpointer.setup()
            # 编译图: 将 StateGraph 编译为可执行的 Runnable
            graph = self._build_graph().compile(checkpointer=checkpointer)
            # 调用执行: invoke() 触发整个工作流，返回最终状态
            return graph.invoke(initial_state, config=config)

    def _build_graph(self) -> StateGraph:
        """图的构建"""
        graph = StateGraph(HarnessState)
        # 添加节点
        graph.add_node("load_instructions", self._wrap_node("load_instructions", self._load_instructions))
        graph.add_node("understand_intent", self._wrap_node("understand_intent", self._understand_intent))
        graph.add_node("make_plan", self._wrap_node("make_plan", self._make_plan))
        graph.add_node("select_tool", self._wrap_node("select_tool", self._select_tool))
        graph.add_node("check_permission", self._wrap_node("check_permission", self._check_permission))
        graph.add_node("execute_tool", self._wrap_node("execute_tool", self._execute_tool))
        graph.add_node("observe_result", self._wrap_node("observe_result", self._observe_result))
        graph.add_node("decide_next_step", self._wrap_node("decide_next_step", self._decide_next_step))
        graph.add_node("summarize_result", self._wrap_node("summarize_result", self._summarize_result))

        # 边的连接
        graph.add_edge(START, "load_instructions")
        graph.add_edge("load_instructions", "understand_intent")
        graph.add_edge("understand_intent", "make_plan")
        graph.add_conditional_edges(
            "make_plan",
            self._next_after_plan,
            {
                "execute": "select_tool",
                "summarize": "summarize_result",
            },
        )
        graph.add_edge("select_tool", "check_permission")
        graph.add_edge("check_permission", "execute_tool")
        graph.add_edge("execute_tool", "observe_result")
        graph.add_edge("observe_result", "decide_next_step")
        graph.add_conditional_edges(
            "decide_next_step",
            self._next_after_decision,
            {
                "continue": "select_tool",
                "summarize": "summarize_result",
            },
        )
        graph.add_edge("summarize_result", END)
        return graph

    def _load_instructions(self, state: HarnessState) -> dict[str, Any]:
        """项目规则读取节点
        为后续 LLM 调用提供系统提示（System Prompt）
        确保 AI 遵循项目规范和约束
        """
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
        """意图理解节点"""
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
        max_steps = state.get("max_steps", HarnessStepPlanner.DEFAULT_MAX_STEPS)
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
        output = {
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
        """工具选择节点"""
        intent = state.get("intent") or {}
        current_step = self._current_step(state)
        route = self.tool_router_service.select_tool(
            user_input=current_step.get("objective") or state["user_input"],
            intent=current_step.get("intent") or intent.get("intent"),
            suggested_tool_type=current_step.get("suggested_tool_type")
            or intent.get("suggested_tool_type"),
            tool_input=current_step.get("tool_input") or state.get("tool_input") or {},
        )
        payload = route.model_dump(mode="json")
        selected_tool_id = route.selected_tool.id if route.selected_tool else None
        # selected_tool_id 是任务的重要属性，需要在主表中标记
        with get_connection() as connection:
            TaskRepository(connection).update_status(
                task_id=UUID(state["task_id"]),
                status="RUNNING",
                current_step="select_tool",
                selected_tool_id=selected_tool_id,
            )
        # _record_event 只记录事件，不更新任务主表
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
        """权限校验节点"""
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
            payload={
                "step_index": state.get("current_step_index", 0),
                "permission": payload,
            },
        )
        if permission.decision.value == "ASK":
            approval = self.approval_service.create_or_get_pending(
                task_id=UUID(state["task_id"]),
                run_id=UUID(state["run_id"]),
                trace_id=UUID(state["trace_id"]),
                tool_id=selected_tool.id,
                requested_action=f"execute:{selected_tool.name}",
                reason=permission.reason,
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
        """工具执行节点"""
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

        # 把 LLM 生成的 tool_input 归一化为各类 Adapter 可接受的结构。
        tool_input = self.tool_input_normalizer.normalize(
            tool=selected_tool,
            tool_input=state.get("tool_input") or {},
        )
        # 选择工具并执行
        result = self.dispatcher.dispatch(
            tool=selected_tool,
            tool_input=tool_input,
            task_id=UUID(state["task_id"]),
            run_id=UUID(state["run_id"]),
            trace_id=UUID(state["trace_id"]),
        )
        payload = result.model_dump(mode="json")
        self._record_event(
            state,
            event_type="TOOL_EXECUTED" if result.success else "TOOL_EXECUTION_FAILED",
            step="execute_tool",
            message="工具执行完成。" if result.success else result.error_message,
            payload={
                "step_index": state.get("current_step_index", 0),
                "tool_call": payload,
            },
        )
        return {
            "tool_input": tool_input,
            "tool_result": payload,
            "final_status": "SUCCESS" if result.success else "FAILED",
            "error_message": result.error_message,
        }

    def _observe_result(self, state: HarnessState) -> dict[str, Any]:
        """记录当前步骤的 observation，供后续步骤和最终总结使用。"""
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
        return {
            "observations": observations,
            "steps": steps,
        }

    def _decide_next_step(self, state: HarnessState) -> dict[str, Any]:
        """根据当前状态决定继续下一步还是进入总结。"""
        steps = state.get("steps") or []
        current_index = int(state.get("current_step_index", 0))
        final_status = state.get("final_status", "FAILED")

        if final_status != "SUCCESS":
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
            payload={
                "next_action": "continue",
                "next_step_index": next_index,
                "next_step": next_step,
            },
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
        """结果总结节点，把结构化执行结果转换为用户可读 final_answer。"""
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
                    "output": {
                        "steps": state.get("steps") or [],
                        "stop_reason": state.get("stop_reason"),
                    },
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
        """从嵌套的路由数据中提取工具对象"""
        route = state.get("route") or {}
        selected_tool = route.get("selected_tool")
        if not selected_tool:
            return None
        return ToolResponse.model_validate(selected_tool)

    def _record_event(
        self,
        state: HarnessState,
        *,
        event_type: str,
        step: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """更新task表"""
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
        """记录节点失败，便于 Dashboard 精确展示失败位置。"""
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
            )
