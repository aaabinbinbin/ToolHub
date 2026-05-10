from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection

from app.schemas.llm import LLMCallRecord
from app.security.secret_manager import redactor


class LLMCallRepository:
    """负责 `llm_calls` 表的写入。

    Repository 层只处理 SQL 和数据库字段映射，不处理 LLM 调用逻辑。
    """

    def __init__(self, connection: Connection) -> None:
        """创建 LLM 调用日志 Repository。

        Args:
            connection: 当前事务使用的 PostgreSQL 连接。
        """
        self.connection = connection

    def create(self, record: LLMCallRecord) -> None:
        """写入一条 LLM 调用记录。

        成功、失败、mock fallback 都会写入 `llm_calls`，这样 Dashboard 后续可以展示完整 LLM 调用链路。

        Args:
            record: 标准化后的 LLM 调用记录。
        """
        self.connection.execute(
            """
            INSERT INTO llm_calls (
                id, task_id, run_id, trace_id, node_name, provider, model, prompt,
                response, input_tokens, output_tokens, duration_ms, estimated_cost,
                status, error_message, user_id, workspace_id
            )
            VALUES (
                %(id)s, %(task_id)s, %(run_id)s, %(trace_id)s, %(node_name)s,
                %(provider)s, %(model)s, %(prompt)s, %(response)s, %(input_tokens)s,
                %(output_tokens)s, %(duration_ms)s, %(estimated_cost)s, %(status)s,
                %(error_message)s, %(user_id)s, %(workspace_id)s
            )
            """,
            {
                "id": uuid4(),
                "task_id": record.task_id,
                "run_id": record.run_id,
                "trace_id": record.trace_id,
                "node_name": record.node_name,
                "provider": record.provider,
                "model": record.model,
                "prompt": redactor.redact(record.prompt),
                "response": redactor.redact(record.response),
                "input_tokens": record.input_tokens,
                "output_tokens": record.output_tokens,
                "duration_ms": record.duration_ms,
                "estimated_cost": record.estimated_cost,
                "status": record.status,
                "error_message": redactor.redact(record.error_message),
                "user_id": record.user_id,
                "workspace_id": record.workspace_id,
            },
        )

    def list_by_trace_id(self, trace_id: UUID) -> list[dict[str, Any]]:
        """按 trace_id 查询 LLM 调用记录。"""
        return list(
            self.connection.execute(
                """
                SELECT *
                FROM llm_calls
                WHERE trace_id = %(trace_id)s
                ORDER BY created_at ASC
                """,
                {"trace_id": trace_id},
            ).fetchall()
        )
