from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from app.common.exceptions import ConflictError
from app.schemas.tool import ToolRegisterRequest

# 选择 psycopg 的原因
# 1.PostgreSQL 驱动：支持同步/异步 API
# 2.原生 JSONB 支持：通过 Jsonb 类型安全写入半结构化数据
# 3.参数化查询：使用 %(name)s 占位符防止 SQL 注入
class ToolRepository:
    # Repository 层只负责 SQL 和数据持久化，不处理 HTTP 状态码和业务编排。
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def create(self, request: ToolRegisterRequest) -> dict[str, Any]:
        # UUID 在应用层生成，后续 Celery worker 或多进程写入时也不依赖数据库自增序列。
        tool_id = uuid4()
        try:
            # RETURNING 子句
            # 1.PostgreSQL 特有语法，插入后立即返回完整行
            # 2.避免二次查询获取 created_at、updated_at 等数据库生成字段
            row = self.connection.execute(
                """
                INSERT INTO tools (
                    id, name, description, tool_type, endpoint, mcp_url, transport,
                    version, input_schema, output_schema, tags, risk_level
                )
                VALUES (
                    %(id)s, %(name)s, %(description)s, %(tool_type)s, %(endpoint)s,
                    %(mcp_url)s, %(transport)s, %(version)s, %(input_schema)s,
                    %(output_schema)s, %(tags)s, %(risk_level)s
                )
                RETURNING *
                """,
                {
                    "id": tool_id,
                    "name": request.name,
                    "description": request.description,
                    "tool_type": request.tool_type.value,
                    "endpoint": request.endpoint,
                    "mcp_url": request.mcp_url,
                    "transport": request.transport,
                    "version": request.version,
                    # psycopg 需要用 Jsonb 包装 Python dict/list，才能正确写入 PostgreSQL JSONB 字段。
                    # Jsonb() 明确告诉驱动："这是 JSONB 类型，请使用二进制格式存储"
                    "input_schema": Jsonb(request.input_schema)
                    if request.input_schema is not None
                    else None,
                    "output_schema": Jsonb(request.output_schema)
                    if request.output_schema is not None
                    else None,
                    "tags": Jsonb(request.tags),
                    "risk_level": request.risk_level.value,
                },
            ).fetchone()
        except UniqueViolation as exc:
            # 数据库唯一约束是最后一道防线；Service/API 层会把这个错误转换成 409。
            raise ConflictError(f"Tool name already exists: {request.name}") from exc

        return row

    def get_by_id(self, tool_id: UUID, include_deleted: bool = False) -> dict[str, Any] | None:
        # 删除采用软删除。默认查询不会返回 DELETED 工具，便于保留审计历史。
        query = "SELECT * FROM tools WHERE id = %(id)s"
        if not include_deleted:
            query += " AND status != 'DELETED'"
        return self.connection.execute(query, {"id": tool_id}).fetchone()

    def search(self, query: str, include_disabled: bool = False) -> list[dict[str, Any]]:
        pattern = f"%{query}%"
        # 默认只搜索 ACTIVE 工具，保证禁用工具不会被 ToolRouter 选中。
        status_filter = "" if include_disabled else "AND status = 'ACTIVE'"
        return list(
            self.connection.execute(
                f"""
                SELECT *
                FROM tools
                WHERE status != 'DELETED'
                  {status_filter}
                  AND (
                      name ILIKE %(pattern)s
                      OR description ILIKE %(pattern)s
                      OR tags ? %(tag)s
                  )
                ORDER BY created_at DESC
                """,
                {
                    "pattern": pattern,
                    # tags 是 JSONB 数组，这里用 ? 做数组元素精确匹配，
                    # 避免 tags::text ILIKE 把 "tag" 误匹配到 "tag1"。
                    "tag": query,
                },
            ).fetchall()
        )

    def enable(self, tool_id: UUID) -> dict[str, Any] | None:
        return self._update_status(tool_id, "ACTIVE")

    def disable(self, tool_id: UUID) -> dict[str, Any] | None:
        return self._update_status(tool_id, "DISABLED")

    def delete(self, tool_id: UUID) -> dict[str, Any] | None:
        return self._update_status(tool_id, "DELETED")

    def _update_status(self, tool_id: UUID, status: str) -> dict[str, Any] | None:
        # enable / disable / delete 都走同一个状态更新逻辑，避免重复 SQL。
        return self.connection.execute(
            """
            UPDATE tools
            SET status = %(status)s, updated_at = now()
            WHERE id = %(id)s AND status != 'DELETED'
            RETURNING *
            """,
            {"id": tool_id, "status": status},
        ).fetchone()
