from __future__ import annotations

from uuid import uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.schemas.tool_call import ToolCallResult


class ToolCallRepository:
    """负责写入 `tool_calls` 表。"""

    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def create(self, result: ToolCallResult) -> None:
        """记录一次工具调用结果。"""
        self.connection.execute(
            """
            INSERT INTO tool_calls (
                id, task_id, run_id, trace_id, tool_id, tool_name, tool_type,
                input, output, status, error_message, duration_ms
            )
            VALUES (
                %(id)s, %(task_id)s, %(run_id)s, %(trace_id)s, %(tool_id)s,
                %(tool_name)s, %(tool_type)s, %(input)s, %(output)s, %(status)s,
                %(error_message)s, %(duration_ms)s
            )
            """,
            {
                "id": uuid4(),
                "task_id": result.task_id,
                "run_id": result.run_id,
                "trace_id": result.trace_id,
                "tool_id": result.tool_id,
                "tool_name": result.tool_name,
                "tool_type": result.tool_type,
                "input": Jsonb(result.input),
                "output": Jsonb(result.output) if result.output is not None else None,
                "status": result.status,
                "error_message": result.error_message,
                "duration_ms": result.duration_ms,
            },
        )
