from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection

from app.schemas.approval import ApprovalStatus


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
    ) -> dict[str, Any]:
        """创建一条待审批请求。"""
        return self.connection.execute(
            """
            INSERT INTO approval_requests (
                id, task_id, run_id, trace_id, tool_id, requested_action,
                reason, status, requested_by
            )
            VALUES (
                %(id)s, %(task_id)s, %(run_id)s, %(trace_id)s, %(tool_id)s,
                %(requested_action)s, %(reason)s, 'PENDING', %(requested_by)s
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
                "reason": reason,
                "requested_by": requested_by,
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
            WHERE task_id = %(task_id)s AND status = 'PENDING'
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
                ORDER BY created_at ASC
                """
            ).fetchall()
        )

    def decide(
        self,
        *,
        approval_id: UUID,
        status: ApprovalStatus,
        decided_by: str,
        decision_reason: str | None,
    ) -> dict[str, Any] | None:
        """更新审批结果。"""
        return self.connection.execute(
            """
            UPDATE approval_requests
            SET status = %(status)s,
                decided_by = %(decided_by)s,
                decision_reason = %(decision_reason)s,
                decided_at = now()
            WHERE id = %(id)s AND status = 'PENDING'
            RETURNING *
            """,
            {
                "id": approval_id,
                "status": status.value,
                "decided_by": decided_by,
                "decision_reason": decision_reason,
            },
        ).fetchone()
