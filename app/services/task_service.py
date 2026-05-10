from __future__ import annotations

from uuid import UUID

from app.common.exceptions import NotFoundError
from app.repositories.db import get_connection
from app.repositories.task_event_repository import TaskEventRepository
from app.repositories.task_repository import TaskRepository
from app.schemas.task import (
    TaskCancelRequest,
    TaskCancelResponse,
    TaskEventResponse,
    TaskResponse,
    TaskSubmitRequest,
    TaskSubmitResponse,
)


class TaskService:
    """后台任务服务，负责提交、查询、取消任务和查询事件。"""

    def submit_task(self, request: TaskSubmitRequest) -> TaskSubmitResponse:
        """创建 QUEUED 任务并投递到 Celery worker。"""
        with get_connection() as connection:
            task = TaskRepository(connection).create_queued_task(
                user_input=request.user_input,
                run_mode=request.run_mode,
                priority=request.priority,
                user_id=request.user_id,
                workspace_id=request.workspace_id,
                run_config=request.run_config,
            )
            TaskEventRepository(connection).create(
                task_id=task["id"],
                run_id=task["run_id"],
                trace_id=task["trace_id"],
                event_type="TASK_SUBMITTED",
                step="submit_task",
                message="任务已提交，等待后台 worker 执行。",
                payload={
                    "run_mode": request.run_mode.value,
                    "priority": request.priority,
                    "user_id": request.user_id,
                    "workspace_id": request.workspace_id,
                    "run_config": request.run_config.model_dump(mode="json"),
                },
                user_id=request.user_id,
                workspace_id=request.workspace_id,
            )

        # 延迟导入，避免 task_service 和 task_worker 在模块加载阶段互相引用。
        from app.workers.task_worker import run_agent_task

        run_agent_task.delay(str(task["id"]))
        return TaskSubmitResponse(
            task_id=task["id"],
            run_id=task["run_id"],
            trace_id=task["trace_id"],
            status=task["status"],
        )

    def get_task(self, task_id: UUID) -> TaskResponse:
        """查询任务状态。"""
        with get_connection() as connection:
            task = TaskRepository(connection).get_by_id(task_id)
        if task is None:
            raise NotFoundError(f"Task not found: {task_id}")
        return TaskResponse.model_validate(task)

    def cancel_task(
        self,
        task_id: UUID,
        request: TaskCancelRequest,
    ) -> TaskCancelResponse:
        """请求取消任务，并写入审计事件。"""
        with get_connection() as connection:
            repository = TaskRepository(connection)
            task = repository.get_by_id(task_id)
            if task is None:
                raise NotFoundError(f"Task not found: {task_id}")

            cancelled = repository.request_cancel(
                task_id=task_id,
                reason=request.reason,
            )
            assert cancelled is not None
            TaskEventRepository(connection).create(
                task_id=task_id,
                run_id=cancelled["run_id"],
                trace_id=cancelled["trace_id"],
                event_type="TASK_CANCEL_REQUESTED",
                step="cancel_task",
                message="任务已收到取消请求。",
                payload={
                    "reason": request.reason,
                    "requested_by": request.requested_by,
                    "previous_status": task["status"],
                },
                user_id=request.requested_by,
                workspace_id=cancelled.get("workspace_id"),
            )

        return TaskCancelResponse(
            task_id=cancelled["id"],
            status=cancelled["status"],
            cancel_requested=cancelled["cancel_requested"],
            cancel_reason=cancelled["cancel_reason"],
        )

    def get_task_events(self, task_id: UUID) -> list[TaskEventResponse]:
        """查询任务事件列表。"""
        with get_connection() as connection:
            task = TaskRepository(connection).get_by_id(task_id)
            if task is None:
                raise NotFoundError(f"Task not found: {task_id}")
            events = TaskEventRepository(connection).list_by_task_id(task_id)
        return [TaskEventResponse.model_validate(event) for event in events]
