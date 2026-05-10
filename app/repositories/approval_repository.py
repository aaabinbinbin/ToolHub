from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection

from app.schemas.approval import ApprovalScope, ApprovalStatus
from app.security.secret_manager import redactor


class ApprovalRepository:
    """负责 approval_requests 表读写。"""

    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def create_pending(
        self,
        *,
        task_id: UUID,
        run_id: UUID,
        trace_id: UUID,
        tool_id: UUID | None,
        requested_action: str,
        reason: str,
        requested_by: str | None = None,
        workspace_id: str = "default",
        approval_scope: ApprovalScope = ApprovalScope.TASK,
        expires_at: datetime | None = None,
    ) -> dict[str, Any]:
        """创建一条待审批请求。"""
        expires_at = expires_at or datetime.now(timezone.utc) + timedelta(hours=1)
        return self.connection.execute(
            """
            INSERT INTO approval_requests (
                id, task_id, run_id, trace_id, tool_id, requested_action,
                reason, status, requested_by, workspace_id, approval_scope, expires_at
            )
            VALUES (
                %(id)s, %(task_id)s, %(run_id)s, %(trace_id)s, %(tool_id)s,
                %(requested_action)s, %(reason)s, 'PENDING', %(requested_by)s,
                %(workspace_id)s, %(approval_scope)s, %(expires_at)s
            )
            RETURNING *
            """,
            {
                "id": uuid4(),
                "task_id": task_id,
                "run_id": run_id,
                "trace_id": trace_id,
                "tool_id": tool_id,
                "requested_action": requested_action,
                "reason": redactor.redact(reason),
                "requested_by": requested_by,
                "workspace_id": workspace_id,
                "approval_scope": approval_scope.value,
                "expires_at": expires_at,
            },
        ).fetchone()

    def get_by_id(self, approval_id: UUID) -> dict[str, Any] | None:
        return self.connection.execute(
            "SELECT * FROM approval_requests WHERE id = %(id)s",
            {"id": approval_id},
        ).fetchone()

    def get_pending_by_task_id(self, task_id: UUID) -> dict[str, Any] | None:
        return self.connection.execute(
            """
            SELECT *
            FROM approval_requests
            WHERE task_id = %(task_id)s
              AND status = 'PENDING'
              AND (expires_at IS NULL OR expires_at > now())
            ORDER BY created_at DESC
            LIMIT 1
            """,
            {"task_id": task_id},
        ).fetchone()

    def list_pending(self) -> list[dict[str, Any]]:
        return list(
            self.connection.execute(
                """
                SELECT *
                FROM approval_requests
                WHERE status = 'PENDING'
                  AND (expires_at IS NULL OR expires_at > now())
                ORDER BY created_at ASC
                """
            ).fetchall()
        )

    def list_by_trace_id(self, trace_id: UUID) -> list[dict[str, Any]]:
        """按 trace_id 查询审批请求。"""
        return list(
            self.connection.execute(
                """
                SELECT *
                FROM approval_requests
                WHERE trace_id = %(trace_id)s
                ORDER BY created_at ASC
                """,
                {"trace_id": trace_id},
            ).fetchall()
        )

    def expire_pending(self) -> int:
        """将已过期的待审批请求标记为 EXPIRED。"""
        result = self.connection.execute(
            """
            UPDATE approval_requests
            SET status = 'EXPIRED',
                decided_at = now(),
                decision_reason = '审批请求已过期。'
            WHERE status = 'PENDING'
              AND expires_at IS NOT NULL
              AND expires_at <= now()
            """
        )
        return int(result.rowcount or 0)

    def decide(
        self,
        *,
        approval_id: UUID,
        status: ApprovalStatus,
        decided_by: str,
        decision_reason: str | None,
        approval_scope: ApprovalScope | None = None,
        approved_until: datetime | None = None,
    ) -> dict[str, Any] | None:
        """更新审批结果。"""
        return self.connection.execute(
            """
            UPDATE approval_requests
            SET status = %(status)s,
                decided_by = %(decided_by)s,
                decision_reason = %(decision_reason)s,
                approval_scope = COALESCE(%(approval_scope)s, approval_scope),
                approved_until = %(approved_until)s,
                decided_at = now()
            WHERE id = %(id)s
              AND status = 'PENDING'
              AND (expires_at IS NULL OR expires_at > now())
            RETURNING *
            """,
            {
                "id": approval_id,
                "status": status.value,
                "decided_by": decided_by,
                "decision_reason": redactor.redact(decision_reason),
                "approval_scope": approval_scope.value if approval_scope is not None else None,
                "approved_until": approved_until,
            },
        ).fetchone()
