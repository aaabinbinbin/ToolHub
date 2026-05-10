"""tool versions and runtime metadata

Revision ID: 20260509_0003
Revises: 20260509_0002
Create Date: 2026-05-09
"""
from __future__ import annotations

from alembic import op


revision = "20260509_0003"
down_revision = "20260509_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """新增工具版本快照表，并补齐运行时 artifact 字段。"""
    op.get_bind().exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS tool_versions (
            id UUID PRIMARY KEY,
            tool_id UUID NOT NULL REFERENCES tools(id),
            version TEXT NOT NULL,
            input_schema JSONB,
            output_schema JSONB,
            config JSONB NOT NULL DEFAULT '{}'::jsonb,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_tool_versions_tool_id ON tool_versions(tool_id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_tool_versions_unique
            ON tool_versions(tool_id, version);

        ALTER TABLE sandbox_executions
            ADD COLUMN IF NOT EXISTS language TEXT,
            ADD COLUMN IF NOT EXISTS artifacts JSONB NOT NULL DEFAULT '[]'::jsonb;

        ALTER TABLE tool_calls
            ADD COLUMN IF NOT EXISTS artifacts JSONB NOT NULL DEFAULT '[]'::jsonb;
        """
    )


def downgrade() -> None:
    """回滚工具版本和 artifact 字段。"""
    op.get_bind().exec_driver_sql(
        """
        ALTER TABLE tool_calls DROP COLUMN IF EXISTS artifacts;
        ALTER TABLE sandbox_executions
            DROP COLUMN IF EXISTS artifacts,
            DROP COLUMN IF EXISTS language;
        DROP TABLE IF EXISTS tool_versions;
        """
    )
