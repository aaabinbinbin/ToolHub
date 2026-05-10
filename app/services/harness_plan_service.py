from __future__ import annotations

from app.llm.intent_service import IntentService
from app.repositories.db import get_connection
from app.repositories.task_event_repository import TaskEventRepository
from app.repositories.task_repository import TaskRepository
from app.schemas.permission import PermissionDecision, RunMode
from app.schemas.routing import HarnessPlanRequest, HarnessPlanResponse
from app.security.permission_engine import PermissionEngine
from app.services.tool_router_service import ToolRouterService


class HarnessPlanService:
    """轻量 Harness 预演服务。

    这个服务只串联意图理解、工具路由和权限判断，不执行工具。
    """

    def __init__(
        self,
        intent_service: IntentService | None = None,
        tool_router_service: ToolRouterService | None = None,
        permission_engine: PermissionEngine | None = None,
    ) -> None:
        """创建 Harness 预演服务。

        Args:
            intent_service: 意图理解服务。
            tool_router_service: 工具路由服务。
            permission_engine: 权限判断引擎。
        """
        self.intent_service = intent_service or IntentService()
        self.tool_router_service = tool_router_service or ToolRouterService()
        self.permission_engine = permission_engine or PermissionEngine()

    def plan(self, request: HarnessPlanRequest) -> HarnessPlanResponse:
        """执行一次不真正调用工具的 Harness 预演。

        这条链路用于验收：先识别意图，再选择工具，最后做权限判断。
        它会创建 tasks 记录并写入 task_events，但不会调用 ToolAdapter。
        """
        task = self._create_task(request)
        task_id = task["id"]
        run_id = task["run_id"]
        trace_id = task["trace_id"]

        # 调用 LLM 获得意图
        intent = self.intent_service.understand_intent(
            request.user_input,
            run_mode=request.run_mode.value,
            task_id=task_id,
            run_id=run_id,
            trace_id=trace_id,
        )

        # 根据意图选择工具，拿到工具路由
        route = self.tool_router_service.select_tool(
            user_input=request.user_input,
            intent=intent.intent,
            suggested_tool_type=intent.suggested_tool_type,
            tool_input=intent.tool_input,
        )

        permission: PermissionDecision | None = None
        # 检查当前运行模式是否支持运行该工具
        if route.selected_tool is not None:
            permission = self.permission_engine.check(
                route.selected_tool,
                request.run_mode,
                user_id=getattr(request, "user_id", None),
                workspace_id=getattr(request, "workspace_id", None),
            )

        status = self._status_from_permission(permission)
        # 记录本次工具路由和权限判断事件
        self._record_events_and_update_task(
            task_id=task_id,
            run_id=run_id,
            trace_id=trace_id,
            route=route,
            permission=permission,
            status=status,
        )

        return HarnessPlanResponse(
            task_id=task_id,
            run_id=run_id,
            trace_id=trace_id,
            status=status,
            intent=intent,
            route=route,
            permission=permission,
        )

    def _create_task(self, request: HarnessPlanRequest) -> dict:
        """创建一条用于关联事件的预演任务。"""
        with get_connection() as connection:
            return TaskRepository(connection).create_plan_task(
                user_input=request.user_input,
                run_mode=request.run_mode,
                priority=request.priority,
                user_id=request.user_id,
                workspace_id=request.workspace_id,
            )

    def _record_events_and_update_task(
        self,
        *,
        task_id,
        run_id,
        trace_id,
        route,
        permission: PermissionDecision | None,
        status: str,
    ) -> None:
        """写入工具路由和权限判断事件，并更新任务状态。"""
        with get_connection() as connection:
            event_repository = TaskEventRepository(connection)
            event_repository.create(
                task_id=task_id,
                run_id=run_id,
                trace_id=trace_id,
                event_type="TOOL_ROUTING_STARTED",
                step="select_tool",
                message="开始根据意图选择工具。",
            )
            event_repository.create(
                task_id=task_id,
                run_id=run_id,
                trace_id=trace_id,
                event_type="TOOL_SELECTED" if route.selected_tool else "TOOL_ROUTING_FAILED",
                step="select_tool",
                message=route.reason,
                payload=route.model_dump(mode="json"),
            )

            if permission is not None:
                event_repository.create(
                    task_id=task_id,
                    run_id=run_id,
                    trace_id=trace_id,
                    event_type="PERMISSION_CHECK_STARTED",
                    step="check_permission",
                    message="开始执行权限检查。",
                )
                event_repository.create(
                    task_id=task_id,
                    run_id=run_id,
                    trace_id=trace_id,
                    event_type="PERMISSION_ALLOWED"
                    if permission.allowed
                    else "PERMISSION_ASKED"
                    if permission.decision.value == "ASK"
                    else "PERMISSION_DENIED",
                    step="check_permission",
                    message=permission.reason,
                    payload=permission.model_dump(mode="json"),
                )

            TaskRepository(connection).update_status_and_selected_tool(
                task_id=task_id,
                status=status,
                selected_tool_id=route.selected_tool.id if route.selected_tool else None,
                current_step="check_permission",
            )

    def _status_from_permission(self, permission: PermissionDecision | None) -> str:
        """根据权限判断结果得到预演任务状态。"""
        if permission is None:
            return "NO_TOOL"
        if permission.decision.value == "ASK":
            return "WAITING_APPROVAL"
        return "PLANNED" if permission.allowed else "DENIED"
