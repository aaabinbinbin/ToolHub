from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.security.secret_manager import redactor


class TaskEventRepository:
    """负责读写 `task_events` 表。"""

    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def create(
        self,
        *,
        task_id: UUID,
        run_id: UUID,
        trace_id: UUID,
        event_type: str,
        step: str | None = None,
        message: str | None = None,
        payload: dict[str, Any] | None = None,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> None:
        """写入一条任务事件，并在落库前统一脱敏 payload。"""
        self.connection.execute(
            """
            INSERT INTO task_events (
                id, task_id, run_id, trace_id, event_type, step, message, payload,
                user_id, workspace_id
            )
            VALUES (
                %(id)s, %(task_id)s, %(run_id)s, %(trace_id)s, %(event_type)s,
                %(step)s, %(message)s, %(payload)s, %(user_id)s, %(workspace_id)s
            )
            """,
            {
                "id": uuid4(),
                "task_id": task_id,
                "run_id": run_id,
                "trace_id": trace_id,
                "event_type": event_type,
                "step": step,
                "message": message,
                "payload": Jsonb(redactor.redact(payload)) if payload is not None else None,
                "user_id": user_id,
                "workspace_id": workspace_id,
            },
        )

    def list_by_task_id(self, task_id: UUID) -> list[dict[str, Any]]:
        """按时间顺序查询某个任务的事件。"""
        return list(
            self.connection.execute(
                """
                SELECT *
                FROM task_events
                WHERE task_id = %(task_id)s
                ORDER BY created_at ASC
                """,
                {"task_id": task_id},
            ).fetchall()
        )

    def list_by_trace_id(self, trace_id: UUID) -> list[dict[str, Any]]:
        """按 trace_id 查询任务事件，供 Trace 聚合视图使用。"""
        return list(
            self.connection.execute(
                """
                SELECT *
                FROM task_events
                WHERE trace_id = %(trace_id)s
                ORDER BY created_at ASC
                """,
                {"trace_id": trace_id},
            ).fetchall()
        )
