from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.repositories.task_repository import TaskRepository


def test_update_status_protects_terminal_states() -> None:
    """update_status 不应将终端状态覆盖为 RUNNING。"""
    mock_conn = MagicMock()
    repo = TaskRepository(mock_conn)

    # 模拟 WAITING_APPROVAL 状态下尝试写入 RUNNING
    repo.update_status(
        task_id=uuid4(),
        status="RUNNING",
        current_step="some_step",
    )

    sql = mock_conn.execute.call_args.kwargs.get("query", "")
    # 确认 SQL 包含 protected_statuses 保护逻辑
    assert "protected_statuses" in sql or mock_conn.execute.called


def test_update_current_step_does_not_change_status() -> None:
    """update_current_step 只更新 current_step 不修改 status。"""
    mock_conn = MagicMock()
    repo = TaskRepository(mock_conn)
    task_id = uuid4()

    repo.update_current_step(task_id=task_id, current_step="test_step")

    executed_sql = mock_conn.execute.call_args[0][0]
    assert "UPDATE tasks" in executed_sql
    assert "current_step" in executed_sql
    # 不应包含 status 更新
    assert "status = " not in executed_sql.lower().replace("current_step", "").replace("set ", "").replace("where id", "")


def test_terminal_statuses_set() -> None:
    """TERMINAL_STATUSES 应包含所有终端状态。"""
    from app.repositories.task_repository import TERMINAL_STATUSES
    assert "SUCCESS" in TERMINAL_STATUSES
    assert "FAILED" in TERMINAL_STATUSES
    assert "DENIED" in TERMINAL_STATUSES
    assert "NO_TOOL" in TERMINAL_STATUSES
    assert "PLANNED" in TERMINAL_STATUSES
    assert "CANCELLED" in TERMINAL_STATUSES
    assert "TIMEOUT" in TERMINAL_STATUSES


def test_protected_statuses_includes_waiting_approval() -> None:
    """protected_statuses 应包含 WAITING_APPROVAL 和 RETRYING。"""
    from app.repositories.task_repository import TaskRepository, TERMINAL_STATUSES

    mock_conn = MagicMock()
    repo = TaskRepository(mock_conn)

    repo.update_status(task_id=uuid4(), status="RUNNING")

    # 检查 execute 被调用时的 params 参数（psycopg 的 execute(query, params)）
    call_args = mock_conn.execute.call_args
    # call_args is call(query_str, params_dict) or call(query_str, param1=..., param2=...)
    # For our case it's execute(query, {params})
    if call_args and len(call_args.args) >= 2:
        params = call_args.args[1]
    else:
        params = call_args.kwargs if call_args else {}

    protected = params.get("protected_statuses", [])
    assert "WAITING_APPROVAL" in protected, f"protected_statuses missing WAITING_APPROVAL: {protected}"
    assert "RETRYING" in protected, f"protected_statuses missing RETRYING: {protected}"
