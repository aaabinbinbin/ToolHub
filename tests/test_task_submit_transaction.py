from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.schemas.task import TaskRunConfig, TaskSubmitRequest
from app.schemas.permission import RunMode
from app.services.task_service import TaskService


def test_submit_creates_both_task_and_event_in_same_transaction() -> None:
    """同一次 submit 中 create_queued_task 和 create 事件应在同一个连接事务内。"""
    service = TaskService()
    request = TaskSubmitRequest(
        user_input="test",
        run_mode=RunMode.SAFE_EXECUTE,
        run_config=TaskRunConfig(max_steps=3, max_retries=1, timeout_seconds=60),
    )

    connection_mock = MagicMock()
    connections_used = []

    class FakeConnectionCtx:
        def __enter__(self):
            connections_used.append(connection_mock)
            return connection_mock

        def __exit__(self, *args):
            return False

    with (
        patch("app.services.task_service.get_connection", return_value=FakeConnectionCtx()),
        patch("app.services.task_service.TaskRepository") as mock_repo_cls,
        patch("app.services.task_service.TaskEventRepository") as mock_event_cls,
        patch("app.workers.task_worker.run_agent_task"),
    ):
        mock_repo = mock_repo_cls.return_value
        mock_repo.create_queued_task.return_value = {
            "id": "00000000-0000-0000-0000-000000000001",
            "run_id": "00000000-0000-0000-0000-000000000002",
            "trace_id": "00000000-0000-0000-0000-000000000003",
            "status": "QUEUED",
        }
        mock_event = mock_event_cls.return_value

        service.submit_task(request)

        # 验证 TaskRepository 和 TaskEventRepository 用同一个 connection 创建
        mock_repo_cls.assert_called_once_with(connection_mock)
        mock_event_cls.assert_called_once_with(connection_mock)


def test_run_config_defaults() -> None:
    """不传 run_config 时应使用 TaskRunConfig 默认值。"""
    request = TaskSubmitRequest(user_input="test")
    config = request.run_config
    assert config.max_steps == 3
    assert config.max_retries == 1
    assert config.timeout_seconds is None
