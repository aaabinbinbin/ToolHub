from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.schemas.permission import RunMode
from app.schemas.task import TaskCancelRequest, TaskSubmitRequest
from app.services.task_service import TaskService


def test_cancel_task_changes_cancel_fields() -> None:
    """cancel_task 应正确设置 cancel_requested / cancel_reason。"""
    service = TaskService()
    task_id = uuid4()
    run_id = uuid4()
    trace_id = uuid4()

    mock_task = {
        "id": task_id,
        "run_id": run_id,
        "trace_id": trace_id,
        "user_input": "test",
        "run_mode": "SAFE_EXECUTE",
        "user_id": "local-user",
        "workspace_id": "default",
        "priority": "default",
        "status": "RUNNING",
        "cancel_requested": False,
        "cancel_reason": None,
    }
    mock_cancelled = {
        "id": task_id,
        "run_id": run_id,
        "trace_id": trace_id,
        "status": "CANCELLED",
        "cancel_requested": True,
        "cancel_reason": "user request",
        "workspace_id": "default",
    }

    with (
        patch("app.services.task_service.get_connection") as mock_conn,
        patch("app.services.task_service.TaskRepository") as mock_repo_cls,
        patch("app.services.task_service.TaskEventRepository") as mock_event_cls,
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_by_id.return_value = mock_task
        mock_repo.request_cancel.return_value = mock_cancelled

        result = service.cancel_task(task_id, TaskCancelRequest(reason="user request"))

        assert result.task_id == task_id
        assert result.status == "CANCELLED"
        assert result.cancel_requested is True
        assert result.cancel_reason == "user request"


def test_cancel_terminal_task_preserves_status() -> None:
    """取消已终止的任务应保留原状态。"""
    service = TaskService()
    task_id = uuid4()
    run_id = uuid4()
    trace_id = uuid4()

    mock_task = {
        "id": task_id,
        "run_id": run_id,
        "trace_id": trace_id,
        "user_input": "test",
        "run_mode": "SAFE_EXECUTE",
        "user_id": "local-user",
        "workspace_id": "default",
        "priority": "default",
        "status": "SUCCESS",
        "cancel_requested": False,
        "cancel_reason": None,
    }
    mock_cancelled = {
        "id": task_id,
        "run_id": run_id,
        "trace_id": trace_id,
        "status": "SUCCESS",
        "cancel_requested": True,
        "cancel_reason": "user request",
        "workspace_id": "default",
    }

    with (
        patch("app.services.task_service.get_connection") as mock_conn,
        patch("app.services.task_service.TaskRepository") as mock_repo_cls,
        patch("app.services.task_service.TaskEventRepository") as mock_event_cls,
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_by_id.return_value = mock_task
        mock_repo.request_cancel.return_value = mock_cancelled

        result = service.cancel_task(task_id, TaskCancelRequest(reason="too late"))

        # 终端任务即使收到取消请求，状态也应保持 SUCCESS
        assert result.status == "SUCCESS"
        assert result.cancel_requested is True
