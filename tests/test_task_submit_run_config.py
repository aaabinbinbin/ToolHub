from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.schemas.permission import RunMode
from app.schemas.task import TaskRunConfig, TaskSubmitRequest
from app.services.task_service import TaskService


def test_submit_task_passes_run_config_to_repository() -> None:
    """submit_task 应将 run_config / user_id / workspace_id 传给 create_queued_task。"""
    service = TaskService()
    request = TaskSubmitRequest(
        user_input="请执行 git status",
        run_mode=RunMode.SAFE_EXECUTE,
        priority="default",
        user_id="test-user-001",
        workspace_id="ws-42",
        run_config=TaskRunConfig(max_steps=5, max_retries=2, timeout_seconds=120),
    )

    with (
        patch("app.services.task_service.get_connection") as mock_conn,
        patch("app.services.task_service.TaskRepository") as mock_repo_cls,
        patch("app.services.task_service.TaskEventRepository") as mock_event_cls,
        patch("app.workers.task_worker.run_agent_task") as mock_task,
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        mock_repo = mock_repo_cls.return_value
        mock_repo.create_queued_task.return_value = {
            "id": "00000000-0000-0000-0000-000000000001",
            "run_id": "00000000-0000-0000-0000-000000000002",
            "trace_id": "00000000-0000-0000-0000-000000000003",
            "status": "QUEUED",
        }

        service.submit_task(request)

        call_kwargs = mock_repo.create_queued_task.call_args.kwargs
        assert call_kwargs["user_id"] == "test-user-001"
        assert call_kwargs["workspace_id"] == "ws-42"
        assert call_kwargs["run_config"] == request.run_config
        assert call_kwargs["run_mode"] == RunMode.SAFE_EXECUTE


def test_submit_task_enqueues_celery_after_commit() -> None:
    """Celery delay 必须在 with 块结束后调用，即事务提交之后。"""
    service = TaskService()
    request = TaskSubmitRequest(user_input="test")

    call_order = []

    class FakeConnectionCtx:
        def __enter__(self):
            call_order.append("enter")
            return MagicMock()

        def __exit__(self, *args):
            call_order.append("commit")
            return False

    with (
        patch("app.services.task_service.get_connection", return_value=FakeConnectionCtx()),
        patch("app.services.task_service.TaskRepository") as mock_repo_cls,
        patch("app.services.task_service.TaskEventRepository"),
        patch("app.workers.task_worker.run_agent_task") as mock_task,
    ):
        mock_repo = mock_repo_cls.return_value
        mock_repo.create_queued_task.return_value = {
            "id": "00000000-0000-0000-0000-000000000001",
            "run_id": "00000000-0000-0000-0000-000000000002",
            "trace_id": "00000000-0000-0000-0000-000000000003",
            "status": "QUEUED",
        }

        def fake_delay(_task_id: str) -> None:
            call_order.append("delay")

        mock_task.delay = fake_delay

        service.submit_task(request)

        # delay 必须在 commit 之后
        assert call_order == ["enter", "commit", "delay"], (
            f"Expected enter → commit → delay, got {call_order}"
        )
