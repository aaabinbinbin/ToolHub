from __future__ import annotations

from uuid import uuid4

from app.repositories.approval_repository import ApprovalRepository
from app.repositories.db import get_connection, init_db
from app.repositories.task_repository import TaskRepository
from app.schemas.approval import ApprovalStatus
from app.schemas.permission import RunMode
from app.schemas.tool import (
    HealthStatus,
    RiskLevel,
    ToolRegisterRequest,
    ToolResponse,
    ToolStatus,
    ToolType,
)
from app.services.approval_service import ApprovalService


def _register_high_risk_tool() -> str:
    """注册一个 HIGH 风险 sandbox 工具，返回 tool_id 字符串。"""
    from app.repositories.tool_repository import ToolRepository

    with get_connection() as connection:
        # 先检查是否已存在
        try:
            tool = ToolRepository(connection).create(
                ToolRegisterRequest(
                    name="e2e-danger-python",
                    description="E2E 测试用高风险 Python 沙箱",
                    tool_type=ToolType.SANDBOX,
                    endpoint="python",
                    version="1.0.0",
                    tags=["sandbox", "e2e"],
                    risk_level=RiskLevel.HIGH,
                )
            )
            return str(tool["id"])
        except Exception:
            connection.rollback()
            # 工具可能已存在，查询已有记录
            existing = connection.execute(
                "SELECT id FROM tools WHERE name = 'e2e-danger-python'"
            ).fetchone()
            if existing:
                return str(existing["id"])
            raise


def test_approval_resume_e2e_high_risk_waits_then_approved() -> None:
    """端到端：HIGH risk + SAFE_EXECUTE → WAITING_APPROVAL → approve → 任务继续。

    测试步骤：
    1. 注册 HIGH 风险工具
    2. 创建 SAFE_EXECUTE 任务
    3. 调用 ApprovalService.create_or_get_pending 模拟 Harness 触发审批
    4. 验证审批请求为 PENDING
    5. 调用 approve
    6. 验证任务状态变为 QUEUED（等待 worker 重新执行）
    7. 验证 run_mode 切换为 FULL_EXECUTE
    """
    init_db()
    tool_id_str = _register_high_risk_tool()
    tool_uuid = uuid4()  # 可以使用任意 UUID，因为有 FK 约束需要真实 tool_id

    # 创建 SAFE_EXECUTE 任务
    with get_connection() as connection:
        task = TaskRepository(connection).create_queued_task(
            user_input="请运行 Python 代码 print(sum(range(10)))",
            run_mode=RunMode.SAFE_EXECUTE,
            priority="default",
            run_config={"max_steps": 1, "max_retries": 0, "timeout_seconds": 30},
        )
        task_id = task["id"]
        run_id = task["run_id"]
        trace_id = task["trace_id"]

    # 模拟 Harness 在 check_permission 节点触发审批
    approval = ApprovalService().create_or_get_pending(
        task_id=task_id,
        run_id=run_id,
        trace_id=trace_id,
        tool_id=None,  # approval_requests.tool_id 可为空
        requested_action="execute:e2e-danger-python",
        reason="工具风险等级为 HIGH，需要人工审批后才能执行。",
        requested_by="harness",
        workspace_id="default",
    )
    assert approval.status == ApprovalStatus.PENDING

    # 更新任务状态为 WAITING_APPROVAL（模拟 Harness）
    with get_connection() as connection:
        TaskRepository(connection).update_status(
            task_id=task_id,
            status="WAITING_APPROVAL",
            current_step="check_permission",
        )

    # 验证待审批列表可查到
    pending_list = ApprovalService().list_pending()
    assert any(str(a.id) == str(approval.id) for a in pending_list)

    # 审批通过（mock Celery 避免依赖 Redis）
    from unittest.mock import patch

    with patch("app.workers.task_worker.run_agent_task"):
        decision = ApprovalService().approve(
            approval_id=approval.id,
            decided_by="e2e-tester",
            decision_reason="E2E 测试：允许本次沙箱执行",
        )

    # 验证任务状态
    assert decision.task["status"] == "QUEUED"
    assert decision.task["run_mode"] == "FULL_EXECUTE"

    # 验证审批记录
    with get_connection() as connection:
        updated = ApprovalRepository(connection).get_by_id(approval.id)
        assert updated is not None
        assert updated["status"] == "APPROVED"
        assert updated["decided_by"] == "e2e-tester"

    # 验证任务事件中包含审批事件
    with get_connection() as connection:
        events = connection.execute(
            """
            SELECT event_type FROM task_events
            WHERE task_id = %(task_id)s
            ORDER BY created_at ASC
            """,
            {"task_id": task_id},
        ).fetchall()
    event_types = {e["event_type"] for e in events}
    assert "APPROVAL_REQUESTED" in event_types
    assert "APPROVAL_APPROVED" in event_types


def test_approval_reject_sets_denied_e2e() -> None:
    """端到端：HIGH risk + SAFE_EXECUTE → WAITING_APPROVAL → reject → DENIED。"""
    init_db()
    _register_high_risk_tool()

    with get_connection() as connection:
        task = TaskRepository(connection).create_queued_task(
            user_input="请运行危险 Python 代码",
            run_mode=RunMode.SAFE_EXECUTE,
            priority="default",
        )
        task_id = task["id"]
        run_id = task["run_id"]
        trace_id = task["trace_id"]

    approval = ApprovalService().create_or_get_pending(
        task_id=task_id,
        run_id=run_id,
        trace_id=trace_id,
        tool_id=None,
        requested_action="execute:e2e-danger-python",
        reason="高风险工具需要审批",
        requested_by="harness",
    )

    with get_connection() as connection:
        TaskRepository(connection).update_status(
            task_id=task_id,
            status="WAITING_APPROVAL",
            current_step="check_permission",
        )

    decision = ApprovalService().reject(
        approval_id=approval.id,
        decided_by="e2e-tester",
        decision_reason="E2E 测试：拒绝本次执行",
    )

    assert decision.task["status"] == "DENIED"

    with get_connection() as connection:
        updated = ApprovalRepository(connection).get_by_id(approval.id)
        assert updated["status"] == "REJECTED"

        events = connection.execute(
            "SELECT event_type FROM task_events WHERE task_id = %(task_id)s",
            {"task_id": task_id},
        ).fetchall()
    event_types = {e["event_type"] for e in events}
    assert "APPROVAL_REJECTED" in event_types


def test_approval_does_not_duplicate_pending() -> None:
    """同一任务重复触发审批时不创建重复记录。"""
    init_db()

    with get_connection() as connection:
        task = TaskRepository(connection).create_queued_task(
            user_input="test",
            run_mode=RunMode.SAFE_EXECUTE,
            priority="default",
        )
        task_id = task["id"]
        run_id = task["run_id"]
        trace_id = task["trace_id"]

    # 第一次创建
    first = ApprovalService().create_or_get_pending(
        task_id=task_id,
        run_id=run_id,
        trace_id=trace_id,
        tool_id=None,
        requested_action="execute:test-tool",
        reason="first reason",
    )

    # 第二次调用应复用已有审批
    second = ApprovalService().create_or_get_pending(
        task_id=task_id,
        run_id=run_id,
        trace_id=trace_id,
        tool_id=None,
        requested_action="execute:test-tool",
        reason="second reason, should be ignored",
    )

    assert str(first.id) == str(second.id)
    assert first.reason == second.reason  # 原因不变

    # 数据库中只有一条 PENDING
    with get_connection() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM approval_requests WHERE task_id = %(task_id)s",
            {"task_id": task_id},
        ).fetchone()
    assert count is not None
    assert count["count"] == 1
