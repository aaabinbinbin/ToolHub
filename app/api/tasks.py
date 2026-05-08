from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.schemas.task import (
    TaskEventResponse,
    TaskResponse,
    TaskSubmitRequest,
    TaskSubmitResponse,
)
from app.services.task_service import TaskService

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def get_task_service() -> TaskService:
    """创建 TaskService 依赖。"""
    return TaskService()


@router.post("", response_model=TaskSubmitResponse)
def submit_task(
    request: TaskSubmitRequest,
    service: TaskService = Depends(get_task_service),
) -> TaskSubmitResponse:
    """提交后台 Agent 任务，立即返回 task_id/run_id/trace_id。"""
    return service.submit_task(request)


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(
    task_id: UUID,
    service: TaskService = Depends(get_task_service),
) -> TaskResponse:
    """查询任务当前状态。"""
    return service.get_task(task_id)


@router.get("/{task_id}/events", response_model=list[TaskEventResponse])
def get_task_events(
    task_id: UUID,
    service: TaskService = Depends(get_task_service),
) -> list[TaskEventResponse]:
    """查询任务执行事件。"""
    return service.get_task_events(task_id)

