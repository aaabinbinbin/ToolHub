from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.schemas.permission import RunMode
from app.schemas.task import TaskRunConfig
from app.security.secret_manager import redactor


TERMINAL_STATUSES = {
    "SUCCESS",
    "FAILED",
    "DENIED",
    "NO_TOOL",
    "PLANNED",
    "CANCELLED",
    "TIMEOUT",
}


class TaskRepository:
    """负责 `tasks` 表的读写，保持任务运行状态可审计、可恢复。"""

    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def create_plan_task(
        self,
        *,
        user_input: str,
        run_mode: RunMode,
        priority: str,
        user_id: str = "local-user",
        workspace_id: str = "default",
        status: str = "PLANNED",
        run_config: TaskRunConfig | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """创建只用于预演路由和权限检查的任务记录。"""
        task_id = uuid4()
        run_id = uuid4()
        trace_id = uuid4()
        normalized_config = self._normalize_run_config(run_config)
        return self.connection.execute(
            """
            INSERT INTO tasks (
                id, run_id, trace_id, user_input, run_mode, user_id, workspace_id,
                priority, status, run_config, max_retries, created_at, updated_at
            )
            VALUES (
                %(id)s, %(run_id)s, %(trace_id)s, %(user_input)s, %(run_mode)s,
                %(user_id)s, %(workspace_id)s, %(priority)s, %(status)s,
                %(run_config)s, %(max_retries)s, now(), now()
            )
            RETURNING *
            """,
            {
                "id": task_id,
                "run_id": run_id,
                "trace_id": trace_id,
                "user_input": user_input,
                "run_mode": run_mode.value,
                "user_id": user_id,
                "workspace_id": workspace_id,
                "priority": priority,
                "status": status,
                "run_config": Jsonb(normalized_config),
                "max_retries": normalized_config["max_retries"],
            },
        ).fetchone()

    def create_queued_task(
        self,
        *,
        user_input: str,
        run_mode: RunMode,
        priority: str,
        user_id: str = "local-user",
        workspace_id: str = "default",
        run_config: TaskRunConfig | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """创建等待 Celery worker 执行的任务。"""
        task_id = uuid4()
        run_id = uuid4()
        trace_id = uuid4()
        normalized_config = self._normalize_run_config(run_config)
        return self.connection.execute(
            """
            INSERT INTO tasks (
                id, run_id, trace_id, user_input, run_mode, user_id, workspace_id,
                priority, status, run_config, max_retries,
                current_step, created_at, updated_at
            )
            VALUES (
                %(id)s, %(run_id)s, %(trace_id)s, %(user_input)s, %(run_mode)s,
                %(user_id)s, %(workspace_id)s, %(priority)s, 'QUEUED',
                %(run_config)s, %(max_retries)s, 'submit_task', now(), now()
            )
            RETURNING *
            """,
            {
                "id": task_id,
                "run_id": run_id,
                "trace_id": trace_id,
                "user_input": user_input,
                "run_mode": run_mode.value,
                "user_id": user_id,
                "workspace_id": workspace_id,
                "priority": priority,
                "run_config": Jsonb(normalized_config),
                "max_retries": normalized_config["max_retries"],
            },
        ).fetchone()

    def get_by_id(self, task_id: UUID) -> dict[str, Any] | None:
        """按 ID 查询任务。"""
        return self.connection.execute(
            "SELECT * FROM tasks WHERE id = %(task_id)s",
            {"task_id": task_id},
        ).fetchone()

    def list_by_trace_id(self, trace_id: UUID) -> list[dict[str, Any]]:
        """按 trace_id 查询同一条执行链路中的任务。"""
        return list(
            self.connection.execute(
                """
                SELECT *
                FROM tasks
                WHERE trace_id = %(trace_id)s
                ORDER BY created_at ASC
                """,
                {"trace_id": trace_id},
            ).fetchall()
        )

    def request_cancel(
        self,
        *,
        task_id: UUID,
        reason: str | None,
    ) -> dict[str, Any] | None:
        """标记任务取消请求；运行中的工具调用会在下一次 Harness 节点边界停止。"""
        return self.connection.execute(
            """
            UPDATE tasks
            SET cancel_requested = true,
                cancel_reason = %(reason)s,
                cancelled_at = COALESCE(cancelled_at, now()),
                status = CASE
                    WHEN status IN ('SUCCESS', 'FAILED', 'DENIED', 'NO_TOOL', 'PLANNED', 'TIMEOUT')
                        THEN status
                    ELSE 'CANCELLED'
                END,
                finished_at = CASE
                    WHEN status IN ('SUCCESS', 'FAILED', 'DENIED', 'NO_TOOL', 'PLANNED', 'TIMEOUT')
                        THEN finished_at
                    ELSE now()
                END,
                updated_at = now()
            WHERE id = %(task_id)s
            RETURNING *
            """,
            {"task_id": task_id, "reason": redactor.redact(reason)},
        ).fetchone()

    def increment_retry_count(self, task_id: UUID) -> None:
        """增加任务级重试计数，供 Dashboard 和审计使用。"""
        self.connection.execute(
            """
            UPDATE tasks
            SET retry_count = retry_count + 1,
                status = CASE WHEN cancel_requested THEN status ELSE 'RETRYING' END,
                current_step = 'decide_next_step',
                updated_at = now()
            WHERE id = %(task_id)s
            """,
            {"task_id": task_id},
        )

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
            SET status = CASE
                    WHEN cancel_requested AND %(status)s = 'RUNNING' THEN status
                    ELSE %(status)s
                END,
                current_step = COALESCE(%(current_step)s, current_step),
                error_message = %(error_message)s,
                result = %(result)s,
                selected_tool_id = COALESCE(%(selected_tool_id)s, selected_tool_id),
                started_at = CASE
                    WHEN %(status)s = 'RUNNING' AND started_at IS NULL THEN now()
                    ELSE started_at
                END,
                finished_at = CASE
                    WHEN %(status)s = ANY(%(terminal_statuses)s) THEN now()
                    ELSE finished_at
                END,
                updated_at = now()
            WHERE id = %(task_id)s
            """,
            {
                "task_id": task_id,
                "status": status,
                "current_step": current_step,
                "error_message": redactor.redact(error_message),
                "result": Jsonb(redactor.redact(result)) if result is not None else None,
                "selected_tool_id": selected_tool_id,
                "terminal_statuses": list(TERMINAL_STATUSES),
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
        """更新预演任务状态和已选择工具。"""
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
                    WHEN %(status)s = ANY(%(terminal_statuses)s) THEN now()
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
                "error_message": redactor.redact(error_message),
                "terminal_statuses": list(TERMINAL_STATUSES),
            },
        ).fetchone()

    def _normalize_run_config(
        self,
        run_config: TaskRunConfig | dict[str, Any] | None,
    ) -> dict[str, Any]:
        """统一任务级运行参数，避免 Harness 从不完整配置中读取。"""
        if isinstance(run_config, TaskRunConfig):
            return run_config.model_dump(mode="json")
        return TaskRunConfig.model_validate(run_config or {}).model_dump(mode="json")
