from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb


class TaskEventRepository:
    """负责写入 `task_events` 表。

    task_events 是 ToolHub 可观测性的核心表之一，用于还原 Agent Harness 的执行链路。
    """

    def __init__(self, connection: Connection) -> None:
        """创建任务事件 Repository。"""
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
    ) -> None:
        """写入一条任务事件。

        payload 使用 JSONB 保存，方便后续 Dashboard 展示路由结果、权限决策等结构化信息。
        """
        self.connection.execute(
            """
            INSERT INTO task_events (
                id, task_id, run_id, trace_id, event_type, step, message, payload
            )
            VALUES (
                %(id)s, %(task_id)s, %(run_id)s, %(trace_id)s, %(event_type)s,
                %(step)s, %(message)s, %(payload)s
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
                "payload": Jsonb(payload) if payload is not None else None,
            },
        )

    def list_by_task_id(self, task_id: UUID) -> list[dict[str, Any]]:
        """按时间顺序查询任务事件。"""
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
