from __future__ import annotations

from uuid import UUID

from app.common.exceptions import NotFoundError
from app.repositories.db import get_connection
from app.repositories.task_event_repository import TaskEventRepository
from app.repositories.task_repository import TaskRepository
from app.schemas.task import (
    TaskEventResponse,
    TaskResponse,
    TaskSubmitRequest,
    TaskSubmitResponse,
)


class TaskService:
    """后台任务服务，负责提交任务、查询任务和查询事件。"""

    def submit_task(self, request: TaskSubmitRequest) -> TaskSubmitResponse:
        """创建 QUEUED 任务并投递到 Celery worker。"""
        with get_connection() as connection:
            task = TaskRepository(connection).create_queued_task(
                user_input=request.user_input,
                run_mode=request.run_mode,
                priority=request.priority,
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
                },
            )
        # 延迟导入,因为 task_service 被 task_worker 间接依赖
        # 避免模块导入时 Celery 与 Service 互相引用，投递任务放在事务提交之后执行。
        from app.workers.task_worker import run_agent_task

        # 异步发送任务消息到 Redis
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

    def get_task_events(self, task_id: UUID) -> list[TaskEventResponse]:
        """查询任务事件列表。"""
        with get_connection() as connection:
            task = TaskRepository(connection).get_by_id(task_id)
            if task is None:
                raise NotFoundError(f"Task not found: {task_id}")
            events = TaskEventRepository(connection).list_by_task_id(task_id)
        return [TaskEventResponse.model_validate(event) for event in events]

