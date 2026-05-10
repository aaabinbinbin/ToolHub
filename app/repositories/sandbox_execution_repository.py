from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.schemas.sandbox import SandboxRunResult
from app.security.secret_manager import redactor


class SandboxExecutionRepository:
    """负责写入 `sandbox_executions` 表。"""

    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def create(
        self,
        *,
        result: SandboxRunResult,
        task_id,
        run_id,
        trace_id,
        tool_name: str | None,
    ) -> None:
        """记录一次 Docker 沙箱执行结果。"""
        self.connection.execute(
            """
            INSERT INTO sandbox_executions (
                id, task_id, run_id, trace_id, tool_name, command, stdout, stderr,
                exit_code, duration_ms, timeout_seconds, container_id, status,
                error_message, language, artifacts
            )
            VALUES (
                %(id)s, %(task_id)s, %(run_id)s, %(trace_id)s, %(tool_name)s,
                %(command)s, %(stdout)s, %(stderr)s, %(exit_code)s, %(duration_ms)s,
                %(timeout_seconds)s, %(container_id)s, %(status)s, %(error_message)s,
                %(language)s, %(artifacts)s
            )
            """,
            {
                "id": uuid4(),
                "task_id": task_id,
                "run_id": run_id,
                "trace_id": trace_id,
                "tool_name": tool_name,
                "command": result.command,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_code,
                "duration_ms": result.duration_ms,
                "timeout_seconds": result.timeout_seconds,
                "container_id": result.container_id,
                "status": result.status,
                "error_message": redactor.redact(result.error_message),
                "language": result.language,
                "artifacts": Jsonb(redactor.redact(result.artifacts or [])),
            },
        )

    def list_by_trace_id(self, trace_id: UUID) -> list[dict[str, Any]]:
        """按 trace_id 查询沙箱执行记录。"""
        return list(
            self.connection.execute(
                """
                SELECT *
                FROM sandbox_executions
                WHERE trace_id = %(trace_id)s
                ORDER BY created_at ASC
                """,
                {"trace_id": trace_id},
            ).fetchall()
        )
