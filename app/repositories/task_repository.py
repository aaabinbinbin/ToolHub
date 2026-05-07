from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection

from app.schemas.permission import RunMode


class TaskRepository:
    """负责 `tasks` 表的最小写入能力。

    Day 3 只需要创建一条预演任务，用来关联 task_events。
    后续 Day 6 会继续扩展完整 Task Runtime。
    """

    def __init__(self, connection: Connection) -> None:
        """创建任务 Repository。

        Args:
            connection: 当前事务使用的 PostgreSQL 连接。
        """
        self.connection = connection

    def create_plan_task(
        self,
        *,
        user_input: str,
        run_mode: RunMode,
        priority: str,
        status: str = "PLANNED",
    ) -> dict[str, Any]:
        """创建一条只用于路由和权限预演的任务记录。

        Day 3 的任务不会进入 Celery，也不会执行工具，只用于保存 run_id、trace_id 和事件。
        """
        task_id = uuid4()
        run_id = uuid4()
        trace_id = uuid4()
        return self.connection.execute(
            """
            INSERT INTO tasks (
                id, run_id, trace_id, user_input, run_mode, priority, status, created_at, updated_at
            )
            VALUES (
                %(id)s, %(run_id)s, %(trace_id)s, %(user_input)s, %(run_mode)s,
                %(priority)s, %(status)s, now(), now()
            )
            RETURNING *
            """,
            {
                "id": task_id,
                "run_id": run_id,
                "trace_id": trace_id,
                "user_input": user_input,
                "run_mode": run_mode.value,
                "priority": priority,
                "status": status,
            },
        ).fetchone()

    def update_status_and_selected_tool(
        self,
        *,
        task_id: UUID,
        status: str,
        selected_tool_id: UUID | None,
        current_step: str,
    ) -> None:
        """更新预演任务状态和已选择工具。

        Args:
            task_id: 任务 ID。
            status: 预演后的任务状态，例如 PLANNED、DENIED、NO_TOOL。
            selected_tool_id: ToolRouter 选择出的工具 ID。
            current_step: 当前执行步骤。
        """
        self.connection.execute(
            """
            UPDATE tasks
            SET status = %(status)s,
                selected_tool_id = %(selected_tool_id)s,
                current_step = %(current_step)s,
                updated_at = now()
            WHERE id = %(task_id)s
            """,
            {
                "task_id": task_id,
                "status": status,
                "selected_tool_id": selected_tool_id,
                "current_step": current_step,
            },
        )
