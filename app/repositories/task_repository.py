from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb

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

    def create_queued_task(
        self,
        *,
        user_input: str,
        run_mode: RunMode,
        priority: str,
    ) -> dict[str, Any]:
        """创建一条等待 Celery worker 执行的任务。"""
        task_id = uuid4()
        run_id = uuid4()
        trace_id = uuid4()
        return self.connection.execute(
            """
            INSERT INTO tasks (
                id, run_id, trace_id, user_input, run_mode, priority, status,
                current_step, created_at, updated_at
            )
            VALUES (
                %(id)s, %(run_id)s, %(trace_id)s, %(user_input)s, %(run_mode)s,
                %(priority)s, 'QUEUED', 'submit_task', now(), now()
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
            },
        ).fetchone()

    def get_by_id(self, task_id: UUID) -> dict[str, Any] | None:
        """按 ID 查询任务。"""
        return self.connection.execute(
            "SELECT * FROM tasks WHERE id = %(task_id)s",
            {"task_id": task_id},
        ).fetchone()

    def update_status(
        self,
        *,
        task_id: UUID,
        status: str,
        current_step: str | None = None,
        error_message: str | None = None,
        result: dict[str, Any] | None = None,
        selected_tool_id: UUID | None = None,
    ) -> None:
        """更新任务状态、当前步骤、结果和错误信息。"""
        self.connection.execute(
            """
            UPDATE tasks
            SET status = %(status)s,
                current_step = COALESCE(%(current_step)s, current_step),
                error_message = %(error_message)s,
                result = %(result)s,
                selected_tool_id = COALESCE(%(selected_tool_id)s, selected_tool_id),
                started_at = CASE
                    WHEN %(status)s = 'RUNNING' AND started_at IS NULL THEN now()
                    ELSE started_at
                END,
                finished_at = CASE
                    WHEN %(status)s IN ('SUCCESS', 'FAILED', 'DENIED', 'NO_TOOL', 'PLANNED') THEN now()
                    ELSE finished_at
                END,
                updated_at = now()
            WHERE id = %(task_id)s
            """,
            {
                "task_id": task_id,
                "status": status,
                "current_step": current_step,
                "error_message": error_message,
                "result": Jsonb(result) if result is not None else None,
                "selected_tool_id": selected_tool_id,
            },
        )

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

    def update_after_approval(
        self,
        *,
        task_id: UUID,
        status: str,
        run_mode: RunMode | None = None,
        current_step: str,
        error_message: str | None = None,
    ) -> dict[str, Any] | None:
        """审批动作后更新任务状态和运行模式。"""
        return self.connection.execute(
            """
            UPDATE tasks
            SET status = %(status)s,
                run_mode = COALESCE(%(run_mode)s, run_mode),
                current_step = %(current_step)s,
                error_message = %(error_message)s,
                finished_at = CASE
                    WHEN %(status)s IN ('SUCCESS', 'FAILED', 'DENIED', 'NO_TOOL', 'PLANNED') THEN now()
                    ELSE NULL
                END,
                updated_at = now()
            WHERE id = %(task_id)s
            RETURNING *
            """,
            {
                "task_id": task_id,
                "status": status,
                "run_mode": run_mode.value if run_mode is not None else None,
                "current_step": current_step,
                "error_message": error_message,
            },
        ).fetchone()
