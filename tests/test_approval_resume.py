from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.schemas.approval import (
    ApprovalDecisionRequest,
    ApprovalRequestResponse,
    ApprovalScope,
    ApprovalStatus,
)
from app.schemas.permission import PermissionDecision, PermissionDecisionType, RunMode
from app.schemas.tool import HealthStatus, RiskLevel, ToolResponse, ToolStatus, ToolType
from app.security.permission_engine import PermissionEngine
from app.services.approval_service import ApprovalService


def make_high_risk_tool() -> ToolResponse:
    now = datetime.now(timezone.utc)
    return ToolResponse(
        id=uuid4(),
        name="danger-python",
        description="高风险 Python 沙箱工具",
        tool_type=ToolType.SANDBOX,
        endpoint="python",
        mcp_url=None,
        transport=None,
        version="1.0.0",
        input_schema=None,
        output_schema=None,
        tags=["sandbox"],
        risk_level=RiskLevel.HIGH,
        status=ToolStatus.ACTIVE,
        health_status=HealthStatus.UNKNOWN,
        last_checked_at=None,
        created_at=now,
        updated_at=now,
    )


def test_approval_creates_pending_request() -> None:
    """create_or_get_pending 应创建新审批请求。"""
    tool = make_high_risk_tool()
    task_id = uuid4()
    run_id = uuid4()
    trace_id = uuid4()

    mock_approval = {
        "id": uuid4(),
        "task_id": task_id,
        "run_id": run_id,
        "trace_id": trace_id,
        "tool_id": tool.id,
        "requested_action": f"execute:{tool.name}",
        "reason": "高风险工具需要审批",
        "status": "PENDING",
        "requested_by": "harness",
        "decided_by": None,
        "decision_reason": None,
        "workspace_id": "default",
        "approval_scope": "TASK",
        "expires_at": None,
        "approved_until": None,
        "created_at": datetime.now(timezone.utc),
        "decided_at": None,
    }

    with (
        patch("app.services.approval_service.get_connection") as mock_conn,
        patch("app.services.approval_service.ApprovalRepository") as mock_repo_cls,
        patch("app.services.approval_service.TaskEventRepository") as mock_event_cls,
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_pending_by_task_id.return_value = None
        mock_repo.create_pending.return_value = mock_approval

        service = ApprovalService()
        result = service.create_or_get_pending(
            task_id=task_id,
            run_id=run_id,
            trace_id=trace_id,
            tool_id=tool.id,
            requested_action=f"execute:{tool.name}",
            reason="高风险工具需要审批",
            requested_by="harness",
        )

        assert result.status == ApprovalStatus.PENDING
        assert str(result.task_id) == str(task_id)


def test_approval_reuses_existing_pending() -> None:
    """如果已有待审批请求，应复用，不重复创建。"""
    tool = make_high_risk_tool()
    task_id = uuid4()
    run_id = uuid4()
    trace_id = uuid4()

    existing_approval = {
        "id": uuid4(),
        "task_id": task_id,
        "run_id": run_id,
        "trace_id": trace_id,
        "tool_id": tool.id,
        "requested_action": f"execute:{tool.name}",
        "reason": "高风险工具需要审批",
        "status": "PENDING",
        "requested_by": "harness",
        "decided_by": None,
        "decision_reason": None,
        "workspace_id": "default",
        "approval_scope": "TASK",
        "expires_at": None,
        "approved_until": None,
        "created_at": datetime.now(timezone.utc),
        "decided_at": None,
    }

    with (
        patch("app.services.approval_service.get_connection") as mock_conn,
        patch("app.services.approval_service.ApprovalRepository") as mock_repo_cls,
        patch("app.services.approval_service.TaskEventRepository") as mock_event_cls,
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_pending_by_task_id.return_value = existing_approval

        service = ApprovalService()
        result = service.create_or_get_pending(
            task_id=task_id,
            run_id=run_id,
            trace_id=trace_id,
            tool_id=tool.id,
            requested_action=f"execute:{tool.name}",
            reason="又一次触发审批",
            requested_by="harness",
        )

        # 应复用已有审批，不创建新审批
        mock_repo.create_pending.assert_not_called()
        assert result.status == ApprovalStatus.PENDING


def test_approve_sets_full_execute_and_reenqueues() -> None:
    """审批通过后应切换到 FULL_EXECUTE 并重新投递 Celery。"""
    approval_id = uuid4()
    task_id = uuid4()
    run_id = uuid4()
    trace_id = uuid4()

    mock_approval = {
        "id": approval_id,
        "task_id": task_id,
        "run_id": run_id,
        "trace_id": trace_id,
        "tool_id": uuid4(),
        "requested_action": "execute:test-tool",
        "reason": "高风险工具",
        "status": "APPROVED",
        "requested_by": "harness",
        "decided_by": "admin",
        "decision_reason": "允许执行",
        "workspace_id": "default",
        "approval_scope": "TASK",
        "expires_at": None,
        "approved_until": None,
        "created_at": datetime.now(timezone.utc),
        "decided_at": datetime.now(timezone.utc),
    }
    mock_task = {
        "id": task_id,
        "run_id": run_id,
        "trace_id": trace_id,
        "status": "QUEUED",
        "run_mode": "FULL_EXECUTE",
    }

    with (
        patch("app.services.approval_service.get_connection") as mock_conn,
        patch("app.services.approval_service.ApprovalRepository") as mock_repo_cls,
        patch("app.services.approval_service.TaskRepository") as mock_task_repo_cls,
        patch("app.services.approval_service.TaskEventRepository") as mock_event_cls,
        patch("app.workers.task_worker.run_agent_task") as mock_celery,
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        mock_repo = mock_repo_cls.return_value
        mock_repo.decide.return_value = mock_approval
        mock_task_repo = mock_task_repo_cls.return_value
        mock_task_repo.update_after_approval.return_value = mock_task

        service = ApprovalService()
        result = service.approve(
            approval_id,
            decided_by="admin",
            decision_reason="允许执行",
        )

        # 验证任务重新入队
        mock_celery.delay.assert_called_once_with(str(task_id))
        assert result.task["status"] == "QUEUED"
        assert result.task["run_mode"] == "FULL_EXECUTE"


def test_reject_sets_denied() -> None:
    """审批拒绝后任务进入 DENIED。"""
    approval_id = uuid4()
    task_id = uuid4()
    run_id = uuid4()
    trace_id = uuid4()

    mock_approval = {
        "id": approval_id,
        "task_id": task_id,
        "run_id": run_id,
        "trace_id": trace_id,
        "tool_id": uuid4(),
        "requested_action": "execute:test-tool",
        "reason": "高风险工具",
        "status": "REJECTED",
        "requested_by": "harness",
        "decided_by": "admin",
        "decision_reason": "拒绝执行",
        "workspace_id": "default",
        "approval_scope": "TASK",
        "expires_at": None,
        "approved_until": None,
        "created_at": datetime.now(timezone.utc),
        "decided_at": datetime.now(timezone.utc),
    }
    mock_task = {
        "id": task_id,
        "run_id": run_id,
        "trace_id": trace_id,
        "status": "DENIED",
        "run_mode": "SAFE_EXECUTE",
    }

    with (
        patch("app.services.approval_service.get_connection") as mock_conn,
        patch("app.services.approval_service.ApprovalRepository") as mock_repo_cls,
        patch("app.services.approval_service.TaskRepository") as mock_task_repo_cls,
        patch("app.services.approval_service.TaskEventRepository") as mock_event_cls,
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        mock_repo = mock_repo_cls.return_value
        mock_repo.decide.return_value = mock_approval
        mock_task_repo = mock_task_repo_cls.return_value
        mock_task_repo.update_after_approval.return_value = mock_task

        service = ApprovalService()
        result = service.reject(
            approval_id,
            decided_by="admin",
            decision_reason="拒绝执行",
        )

        assert result.task["status"] == "DENIED"
