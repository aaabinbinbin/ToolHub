from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.security.secret_manager import redactor


class ToolVersionRepository:
    """维护工具版本快照。"""

    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def create_snapshot(self, tool: dict[str, Any]) -> dict[str, Any]:
        """为工具当前配置创建版本快照。"""
        return self.connection.execute(
            """
            INSERT INTO tool_versions (
                id, tool_id, version, input_schema, output_schema, config, metadata
            )
            VALUES (
                %(id)s, %(tool_id)s, %(version)s, %(input_schema)s, %(output_schema)s,
                %(config)s, %(metadata)s
            )
            ON CONFLICT (tool_id, version) DO UPDATE
            SET input_schema = EXCLUDED.input_schema,
                output_schema = EXCLUDED.output_schema,
                config = EXCLUDED.config,
                metadata = EXCLUDED.metadata
            RETURNING *
            """,
            {
                "id": uuid4(),
                "tool_id": tool["id"],
                "version": tool["version"],
                "input_schema": Jsonb(tool.get("input_schema"))
                if tool.get("input_schema") is not None
                else None,
                "output_schema": Jsonb(tool.get("output_schema"))
                if tool.get("output_schema") is not None
                else None,
                "config": Jsonb(
                    redactor.redact(
                        {
                            "endpoint": tool.get("endpoint"),
                            "mcp_url": tool.get("mcp_url"),
                            "transport": tool.get("transport"),
                            "tool_type": tool.get("tool_type"),
                            "risk_level": tool.get("risk_level"),
                        }
                    )
                ),
                "metadata": Jsonb(redactor.redact(tool.get("metadata") or {})),
            },
        ).fetchone()

    def list_by_tool_id(self, tool_id: UUID) -> list[dict[str, Any]]:
        """查询某个工具的所有版本快照。"""
        return list(
            self.connection.execute(
                """
                SELECT *
                FROM tool_versions
                WHERE tool_id = %(tool_id)s
                ORDER BY created_at DESC
                """,
                {"tool_id": tool_id},
            ).fetchall()
        )
