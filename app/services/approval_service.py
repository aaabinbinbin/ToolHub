from __future__ import annotations

from uuid import UUID

from app.common.exceptions import ConflictError, NotFoundError
from app.repositories.approval_repository import ApprovalRepository
from app.repositories.db import get_connection
from app.repositories.task_event_repository import TaskEventRepository
from app.repositories.task_repository import TaskRepository
from app.schemas.approval import (
    ApprovalDecisionResponse,
    ApprovalRequestResponse,
    ApprovalStatus,
)
from app.schemas.permission import RunMode


class ApprovalService:
    """审批请求服务。"""

    def create_or_get_pending(
        self,
        *,
        task_id: UUID,
        run_id: UUID,
        trace_id: UUID,
        tool_id: UUID | None,
        requested_action: str,
        reason: str,
    ) -> ApprovalRequestResponse:
        """创建待审批请求；如果同一任务已有待审批请求则复用。"""
        with get_connection() as connection:
            repository = ApprovalRepository(connection)
            existing = repository.get_pending_by_task_id(task_id)
            if existing is not None:
                return ApprovalRequestResponse.model_validate(existing)
            approval = repository.create_pending(
                task_id=task_id,
                run_id=run_id,
                trace_id=trace_id,
                tool_id=tool_id,
                requested_action=requested_action,
                reason=reason,
                requested_by="harness",
            )
            TaskEventRepository(connection).create(
                task_id=task_id,
                run_id=run_id,
                trace_id=trace_id,
                event_type="APPROVAL_REQUESTED",
                step="check_permission",
                message=reason,
                payload={
                    "approval_id": str(approval["id"]),
                    "tool_id": str(tool_id) if tool_id else None,
                    "requested_action": requested_action,
                },
            )
        return ApprovalRequestResponse.model_validate(approval)

    def list_pending(self) -> list[ApprovalRequestResponse]:
        with get_connection() as connection:
            approvals = ApprovalRepository(connection).list_pending()
        return [ApprovalRequestResponse.model_validate(item) for item in approvals]

    def approve(
        self,
        approval_id: UUID,
        *,
        decided_by: str,
        decision_reason: str | None,
    ) -> ApprovalDecisionResponse:
        """审批通过：任务切换到 FULL_EXECUTE 并重新进入队列。"""
        with get_connection() as connection:
            approval_repository = ApprovalRepository(connection)
            task_repository = TaskRepository(connection)
            approval = approval_repository.decide(
                approval_id=approval_id,
                status=ApprovalStatus.APPROVED,
                decided_by=decided_by,
                decision_reason=decision_reason,
            )
            if approval is None:
                self._raise_missing_or_decided(connection, approval_id)

            task = task_repository.update_after_approval(
                task_id=approval["task_id"],
                status="QUEUED",
                run_mode=RunMode.FULL_EXECUTE,
                current_step="approval_approved",
                error_message=None,
            )
            if task is None:
                raise NotFoundError(f"Task not found: {approval['task_id']}")
            TaskEventRepository(connection).create(
                task_id=approval["task_id"],
                run_id=approval["run_id"],
                trace_id=approval["trace_id"],
                event_type="APPROVAL_APPROVED",
                step="approval",
                message=decision_reason or "审批已通过，任务将以 FULL_EXECUTE 重新执行。",
                payload={
                    "approval_id": str(approval_id),
                    "decided_by": decided_by,
                    "next_run_mode": RunMode.FULL_EXECUTE.value,
                },
            )

        from app.workers.task_worker import run_agent_task

        run_agent_task.delay(str(task["id"]))
        return ApprovalDecisionResponse(
            approval=ApprovalRequestResponse.model_validate(approval),
            task=task,
        )

    def reject(
        self,
        approval_id: UUID,
        *,
        decided_by: str,
        decision_reason: str | None,
    ) -> ApprovalDecisionResponse:
        """审批拒绝：任务进入 DENIED。"""
        with get_connection() as connection:
            approval_repository = ApprovalRepository(connection)
            task_repository = TaskRepository(connection)
            approval = approval_repository.decide(
                approval_id=approval_id,
                status=ApprovalStatus.REJECTED,
                decided_by=decided_by,
                decision_reason=decision_reason,
            )
            if approval is None:
                self._raise_missing_or_decided(connection, approval_id)

            reason = decision_reason or "审批被拒绝。"
            task = task_repository.update_after_approval(
                task_id=approval["task_id"],
                status="DENIED",
                current_step="approval_rejected",
                error_message=reason,
            )
            if task is None:
                raise NotFoundError(f"Task not found: {approval['task_id']}")
            TaskEventRepository(connection).create(
                task_id=approval["task_id"],
                run_id=approval["run_id"],
                trace_id=approval["trace_id"],
                event_type="APPROVAL_REJECTED",
                step="approval",
                message=reason,
                payload={
                    "approval_id": str(approval_id),
                    "decided_by": decided_by,
                },
            )

        return ApprovalDecisionResponse(
            approval=ApprovalRequestResponse.model_validate(approval),
            task=task,
        )

    def _raise_missing_or_decided(self, connection, approval_id: UUID) -> None:
        existing = ApprovalRepository(connection).get_by_id(approval_id)
        if existing is None:
            raise NotFoundError(f"Approval request not found: {approval_id}")
        raise ConflictError(f"Approval request is not pending: {approval_id}")
