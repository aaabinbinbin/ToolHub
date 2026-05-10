"""governance and redaction fields

Revision ID: 20260509_0002
Revises: 20260509_0001
Create Date: 2026-05-09
"""
from __future__ import annotations

from alembic import op


revision = "20260509_0002"
down_revision = "20260509_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """补齐最终治理模型需要的核心字段。"""
    op.get_bind().exec_driver_sql(
        """
        ALTER TABLE tools
            ADD COLUMN IF NOT EXISTS owner_id TEXT NOT NULL DEFAULT 'local-user',
            ADD COLUMN IF NOT EXISTS workspace_id TEXT NOT NULL DEFAULT 'default',
            ADD COLUMN IF NOT EXISTS schema_hash TEXT,
            ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            ADD COLUMN IF NOT EXISTS quality_score NUMERIC(6, 4),
            ADD COLUMN IF NOT EXISTS success_rate NUMERIC(6, 4),
            ADD COLUMN IF NOT EXISTS avg_duration_ms INTEGER;
        CREATE INDEX IF NOT EXISTS idx_tools_workspace_id ON tools(workspace_id);
        CREATE INDEX IF NOT EXISTS idx_tools_owner_id ON tools(owner_id);

        ALTER TABLE tasks
            ADD COLUMN IF NOT EXISTS user_id TEXT NOT NULL DEFAULT 'local-user',
            ADD COLUMN IF NOT EXISTS workspace_id TEXT NOT NULL DEFAULT 'default';
        CREATE INDEX IF NOT EXISTS idx_tasks_workspace_id ON tasks(workspace_id);
        CREATE INDEX IF NOT EXISTS idx_tasks_user_id ON tasks(user_id);

        ALTER TABLE task_events
            ADD COLUMN IF NOT EXISTS user_id TEXT,
            ADD COLUMN IF NOT EXISTS workspace_id TEXT;
        CREATE INDEX IF NOT EXISTS idx_task_events_workspace_id ON task_events(workspace_id);

        ALTER TABLE tool_calls
            ADD COLUMN IF NOT EXISTS user_id TEXT,
            ADD COLUMN IF NOT EXISTS workspace_id TEXT;
        CREATE INDEX IF NOT EXISTS idx_tool_calls_workspace_id ON tool_calls(workspace_id);

        ALTER TABLE llm_calls
            ADD COLUMN IF NOT EXISTS user_id TEXT,
            ADD COLUMN IF NOT EXISTS workspace_id TEXT;
        CREATE INDEX IF NOT EXISTS idx_llm_calls_workspace_id ON llm_calls(workspace_id);

        ALTER TABLE approval_requests
            ADD COLUMN IF NOT EXISTS workspace_id TEXT NOT NULL DEFAULT 'default',
            ADD COLUMN IF NOT EXISTS approval_scope TEXT NOT NULL DEFAULT 'TASK'
                CHECK (approval_scope IN ('TASK', 'TOOL', 'WORKSPACE', 'TIME_WINDOW')),
            ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS approved_until TIMESTAMPTZ;
        CREATE INDEX IF NOT EXISTS idx_approval_requests_workspace_id ON approval_requests(workspace_id);
        CREATE INDEX IF NOT EXISTS idx_approval_requests_expires_at ON approval_requests(expires_at);

        ALTER TABLE tool_permissions
            ADD COLUMN IF NOT EXISTS policy_name TEXT,
            ADD COLUMN IF NOT EXISTS workspace_id TEXT,
            ADD COLUMN IF NOT EXISTS user_id TEXT,
            ADD COLUMN IF NOT EXISTS tool_type TEXT,
            ADD COLUMN IF NOT EXISTS risk_level TEXT,
            ADD COLUMN IF NOT EXISTS run_mode TEXT,
            ADD COLUMN IF NOT EXISTS command_rule TEXT,
            ADD COLUMN IF NOT EXISTS http_domain TEXT,
            ADD COLUMN IF NOT EXISTS network_access TEXT,
            ADD COLUMN IF NOT EXISTS filesystem_mount TEXT,
            ADD COLUMN IF NOT EXISTS priority INTEGER NOT NULL DEFAULT 100,
            ADD COLUMN IF NOT EXISTS enabled BOOLEAN NOT NULL DEFAULT true;
        CREATE INDEX IF NOT EXISTS idx_tool_permissions_workspace_id ON tool_permissions(workspace_id);
        CREATE INDEX IF NOT EXISTS idx_tool_permissions_enabled ON tool_permissions(enabled);
        """
    )


def downgrade() -> None:
    """移除治理模型扩展字段。"""
    op.get_bind().exec_driver_sql(
        """
        ALTER TABLE tool_permissions
            DROP COLUMN IF EXISTS enabled,
            DROP COLUMN IF EXISTS priority,
            DROP COLUMN IF EXISTS filesystem_mount,
            DROP COLUMN IF EXISTS network_access,
            DROP COLUMN IF EXISTS http_domain,
            DROP COLUMN IF EXISTS command_rule,
            DROP COLUMN IF EXISTS run_mode,
            DROP COLUMN IF EXISTS risk_level,
            DROP COLUMN IF EXISTS tool_type,
            DROP COLUMN IF EXISTS user_id,
            DROP COLUMN IF EXISTS workspace_id,
            DROP COLUMN IF EXISTS policy_name;

        ALTER TABLE approval_requests
            DROP COLUMN IF EXISTS approved_until,
            DROP COLUMN IF EXISTS expires_at,
            DROP COLUMN IF EXISTS approval_scope,
            DROP COLUMN IF EXISTS workspace_id;

        ALTER TABLE llm_calls
            DROP COLUMN IF EXISTS workspace_id,
            DROP COLUMN IF EXISTS user_id;

        ALTER TABLE tool_calls
            DROP COLUMN IF EXISTS workspace_id,
            DROP COLUMN IF EXISTS user_id;

        ALTER TABLE task_events
            DROP COLUMN IF EXISTS workspace_id,
            DROP COLUMN IF EXISTS user_id;

        ALTER TABLE tasks
            DROP COLUMN IF EXISTS workspace_id,
            DROP COLUMN IF EXISTS user_id;

        ALTER TABLE tools
            DROP COLUMN IF EXISTS avg_duration_ms,
            DROP COLUMN IF EXISTS success_rate,
            DROP COLUMN IF EXISTS quality_score,
            DROP COLUMN IF EXISTS metadata,
            DROP COLUMN IF EXISTS schema_hash,
            DROP COLUMN IF EXISTS workspace_id,
            DROP COLUMN IF EXISTS owner_id;
        """
    )
