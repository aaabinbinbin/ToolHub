from __future__ import annotations

import logging
from uuid import UUID

from app.common.config import get_settings
from app.harness.workflow import AgentHarnessWorkflow
from app.repositories.db import get_connection
from app.repositories.task_event_repository import TaskEventRepository
from app.repositories.task_repository import TaskRepository
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)
settings = get_settings()


@celery_app.task(
    name="toolhub.run_agent_task",
    soft_time_limit=settings.workflow_soft_time_limit_seconds, # 给任务机会清理资源、记录日志
    time_limit=settings.workflow_time_limit_seconds, # 防止无限挂起的任务占用资源
)
def run_agent_task(task_id: str) -> dict:
    """Celery worker 入口：执行一个后台 Agent 任务。"""
    task_uuid = UUID(task_id)
    with get_connection() as connection:
        task_repository = TaskRepository(connection)
        # 验证任务存在性,防止执行不存在的数据
        task = task_repository.get_by_id(task_uuid)
        if task is None:
            raise ValueError(f"Task not found: {task_id}")
        # 更新任务状态为 RUNNING
        task_repository.update_status(
            task_id=task_uuid,
            status="RUNNING",
            current_step="task_worker",
        )
        TaskEventRepository(connection).create(
            task_id=task_uuid,
            run_id=task["run_id"],
            trace_id=task["trace_id"],
            event_type="TASK_STARTED",
            step="task_worker",
            message="Celery worker 已开始执行任务。",
        )

    try:
        final_state = AgentHarnessWorkflow().run(task)
        final_status = final_state.get("final_status", "SUCCESS")
        error_message = final_state.get("error_message")
        result = {
            "intent": final_state.get("intent"),
            "route": final_state.get("route"),
            "permission": final_state.get("permission"),
            "tool_input": final_state.get("tool_input"),
            "tool_result": final_state.get("tool_result"),
            "summary": final_state.get("summary"),
        }
        with get_connection() as connection:
            TaskRepository(connection).update_status(
                task_id=task_uuid,
                status=final_status,
                current_step="completed",
                error_message=error_message,
                result=result,
            )
            TaskEventRepository(connection).create(
                task_id=task_uuid,
                run_id=task["run_id"],
                trace_id=task["trace_id"],
                event_type="TASK_COMPLETED"
                if final_status == "SUCCESS"
                else f"TASK_{final_status}",
                step="completed",
                message=f"任务结束，状态：{final_status}。",
                payload=result,
            )
        return {"task_id": task_id, "status": final_status}
    except Exception as exc:
        logger.exception("Agent task failed: %s", task_id)
        with get_connection() as connection:
            TaskRepository(connection).update_status(
                task_id=task_uuid,
                status="FAILED",
                current_step="task_worker",
                error_message=f"{exc.__class__.__name__}: {exc}",
            )
            TaskEventRepository(connection).create(
                task_id=task_uuid,
                run_id=task["run_id"],
                trace_id=task["trace_id"],
                event_type="TASK_FAILED",
                step="task_worker",
                message=f"{exc.__class__.__name__}: {exc}",
            )
        raise
