from __future__ import annotations

from uuid import uuid4

from psycopg import Connection

from app.schemas.sandbox import SandboxRunResult


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
                error_message
            )
            VALUES (
                %(id)s, %(task_id)s, %(run_id)s, %(trace_id)s, %(tool_name)s,
                %(command)s, %(stdout)s, %(stderr)s, %(exit_code)s, %(duration_ms)s,
                %(timeout_seconds)s, %(container_id)s, %(status)s, %(error_message)s
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
                "error_message": result.error_message,
            },
        )

