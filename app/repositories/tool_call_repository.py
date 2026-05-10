from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.schemas.tool_call import ToolCallResult
from app.security.secret_manager import redactor


class ToolCallRepository:
    """负责读写 `tool_calls` 表。"""

    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def create(self, result: ToolCallResult) -> UUID:
        """记录一次工具调用结果，并返回本次 tool_call_id。"""
        tool_call_id = uuid4()
        self.connection.execute(
            """
            INSERT INTO tool_calls (
                id, task_id, run_id, trace_id, tool_id, tool_name, tool_type,
                input, output, status, error_message, duration_ms, user_id, workspace_id,
                artifacts, replay_of_tool_call_id, replay_reason
            )
            VALUES (
                %(id)s, %(task_id)s, %(run_id)s, %(trace_id)s, %(tool_id)s,
                %(tool_name)s, %(tool_type)s, %(input)s, %(output)s, %(status)s,
                %(error_message)s, %(duration_ms)s, %(user_id)s, %(workspace_id)s,
                %(artifacts)s, %(replay_of_tool_call_id)s, %(replay_reason)s
            )
            """,
            {
                "id": tool_call_id,
                "task_id": result.task_id,
                "run_id": result.run_id,
                "trace_id": result.trace_id,
                "tool_id": result.tool_id,
                "tool_name": result.tool_name,
                "tool_type": result.tool_type,
                "input": Jsonb(redactor.redact(result.input)),
                "output": Jsonb(redactor.redact(result.output)) if result.output is not None else None,
                "status": result.status,
                "error_message": redactor.redact(result.error_message),
                "duration_ms": result.duration_ms,
                "user_id": result.user_id,
                "workspace_id": result.workspace_id,
                "artifacts": Jsonb(redactor.redact(result.artifacts)),
                "replay_of_tool_call_id": result.replay_of_tool_call_id,
                "replay_reason": redactor.redact(result.replay_reason),
            },
        )
        self._refresh_tool_quality(result.tool_id)
        return tool_call_id

    def get_by_id(self, tool_call_id: UUID) -> dict[str, Any] | None:
        """按 ID 查询工具调用记录。"""
        return self.connection.execute(
            "SELECT * FROM tool_calls WHERE id = %(id)s",
            {"id": tool_call_id},
        ).fetchone()

    def list_by_trace_id(self, trace_id: UUID) -> list[dict[str, Any]]:
        """按 trace_id 查询工具调用记录。"""
        return list(
            self.connection.execute(
                """
                SELECT *
                FROM tool_calls
                WHERE trace_id = %(trace_id)s
                ORDER BY created_at ASC
                """,
                {"trace_id": trace_id},
            ).fetchall()
        )

    def _refresh_tool_quality(self, tool_id: UUID) -> None:
        """根据历史调用刷新工具质量指标。"""
        self.connection.execute(
            """
            UPDATE tools
            SET success_rate = metrics.success_rate,
                avg_duration_ms = metrics.avg_duration_ms,
                quality_score = metrics.quality_score,
                updated_at = now()
            FROM (
                SELECT
                    tool_id,
                    AVG(CASE WHEN status = 'SUCCESS' THEN 1.0 ELSE 0.0 END)::numeric(6, 4)
                        AS success_rate,
                    AVG(duration_ms)::integer AS avg_duration_ms,
                    (
                        AVG(CASE WHEN status = 'SUCCESS' THEN 1.0 ELSE 0.0 END)
                        * 0.8
                        + CASE
                            WHEN AVG(duration_ms) IS NULL THEN 0.1
                            WHEN AVG(duration_ms) <= 1000 THEN 0.2
                            WHEN AVG(duration_ms) <= 5000 THEN 0.1
                            ELSE 0.0
                          END
                    )::numeric(6, 4) AS quality_score
                FROM tool_calls
                WHERE tool_id = %(tool_id)s
                GROUP BY tool_id
            ) AS metrics
            WHERE tools.id = metrics.tool_id
            """,
            {"tool_id": tool_id},
        )
