from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.harness.workflow import AgentHarnessWorkflow
from app.repositories.db import get_connection, init_db
from app.repositories.task_repository import TaskRepository
from app.schemas.permission import RunMode
from app.schemas.task import TaskCancelRequest, TaskRunConfig
from app.services.task_service import TaskService


def test_task_run_config_is_persisted_and_cancelable() -> None:
    init_db()
    run_config = TaskRunConfig(max_steps=5, max_retries=2, timeout_seconds=60)
    with get_connection() as connection:
        task = TaskRepository(connection).create_queued_task(
            user_input="check git status",
            run_mode=RunMode.SAFE_EXECUTE,
            priority="default",
            run_config=run_config,
        )

    assert task["run_config"]["max_steps"] == 5
    assert task["max_retries"] == 2

    response = TaskService().cancel_task(
        task["id"],
        TaskCancelRequest(reason="用户主动取消", requested_by="tester"),
    )
    assert response.status == "CANCELLED"
    assert response.cancel_requested is True

    with get_connection() as connection:
        cancelled = TaskRepository(connection).get_by_id(task["id"])
        events = connection.execute(
            "SELECT event_type FROM task_events WHERE task_id = %(task_id)s",
            {"task_id": task["id"]},
        ).fetchall()

    assert cancelled["cancel_requested"] is True
    assert cancelled["cancel_reason"] == "用户主动取消"
    assert "TASK_CANCEL_REQUESTED" in {event["event_type"] for event in events}


def test_workflow_retry_replans_current_step() -> None:
    workflow = AgentHarnessWorkflow()
    task_id = uuid4()
    run_id = uuid4()
    trace_id = uuid4()
    now = datetime.now(timezone.utc)

    class FakeReplanner:
        last_fallback_used = False
        last_reason = "补齐缺失参数"

        def replan_step(self, **kwargs):
            step = dict(kwargs["current_step"])
            step["tool_input"] = {"language": "python", "code": "print('ok')"}
            return step

    workflow.replanner = FakeReplanner()
    init_db()
    with get_connection() as connection:
        task = TaskRepository(connection).create_queued_task(
            user_input="run python",
            run_mode=RunMode.SAFE_EXECUTE,
            priority="default",
            run_config={"max_steps": 1, "max_retries": 1},
        )
        task_id = task["id"]
        run_id = task["run_id"]
        trace_id = task["trace_id"]

    state = {
        "task_id": str(task_id),
        "run_id": str(run_id),
        "trace_id": str(trace_id),
        "user_input": "run python",
        "run_mode": "SAFE_EXECUTE",
        "user_id": "local-user",
        "workspace_id": "default",
        "current_step_index": 0,
        "max_retries": 1,
        "deadline_at": (now.replace(year=now.year + 1)).isoformat(),
        "steps": [
            {
                "index": 0,
                "objective": "运行 Python",
                "intent": "RUN_CODE",
                "suggested_tool_type": "SANDBOX",
                "tool_input": {"language": "python"},
            }
        ],
        "observations": [{"status": "FAILED", "error_message": "missing code"}],
        "final_status": "FAILED",
        "error_message": "missing code",
    }

    update = workflow._decide_next_step(state)

    assert update["final_status"] == "RUNNING"
    assert update["steps"][0]["retry_count"] == 1
    assert update["tool_input"] == {"language": "python", "code": "print('ok')"}
