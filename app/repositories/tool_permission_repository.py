from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg import Connection


class ToolPermissionRepository:
    """读取多维工具权限策略。"""

    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def find_matching_policy(
        self,
        *,
        tool_id: UUID,
        tool_type: str,
        risk_level: str,
        run_mode: str,
        user_id: str | None,
        workspace_id: str | None,
        action: str,
    ) -> dict[str, Any] | None:
        """查找最优先匹配的权限策略。

        NULL 表示通配；priority 越小优先级越高。
        """
        return self.connection.execute(
            """
            SELECT *
            FROM tool_permissions
            WHERE enabled = true
              AND action = %(action)s
              AND (tool_id IS NULL OR tool_id = %(tool_id)s)
              AND (tool_type IS NULL OR tool_type = %(tool_type)s)
              AND (risk_level IS NULL OR risk_level = %(risk_level)s)
              AND (run_mode IS NULL OR run_mode = %(run_mode)s)
              AND (user_id IS NULL OR user_id = %(user_id)s)
              AND (workspace_id IS NULL OR workspace_id = %(workspace_id)s)
            ORDER BY priority ASC, created_at DESC
            LIMIT 1
            """,
            {
                "tool_id": tool_id,
                "tool_type": tool_type,
                "risk_level": risk_level,
                "run_mode": run_mode,
                "user_id": user_id,
                "workspace_id": workspace_id,
                "action": action,
            },
        ).fetchone()
