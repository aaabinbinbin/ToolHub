from __future__ import annotations

from uuid import uuid4

from psycopg import Connection

from app.schemas.llm import LLMCallRecord


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
                status, error_message
            )
            VALUES (
                %(id)s, %(task_id)s, %(run_id)s, %(trace_id)s, %(node_name)s,
                %(provider)s, %(model)s, %(prompt)s, %(response)s, %(input_tokens)s,
                %(output_tokens)s, %(duration_ms)s, %(estimated_cost)s, %(status)s,
                %(error_message)s
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
                "prompt": record.prompt,
                "response": record.response,
                "input_tokens": record.input_tokens,
                "output_tokens": record.output_tokens,
                "duration_ms": record.duration_ms,
                "estimated_cost": record.estimated_cost,
                "status": record.status,
                "error_message": record.error_message,
            },
        )
