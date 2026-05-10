"""runtime controls and replay metadata

Revision ID: 20260509_0004
Revises: 20260509_0003
Create Date: 2026-05-09
"""
from __future__ import annotations

from alembic import op


revision = "20260509_0004"
down_revision = "20260509_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """补齐任务级运行控制、取消状态和 replay 追踪字段。"""
    op.get_bind().exec_driver_sql(
        """
        ALTER TABLE tasks
            ADD COLUMN IF NOT EXISTS run_config JSONB NOT NULL DEFAULT '{}'::jsonb,
            ADD COLUMN IF NOT EXISTS cancel_requested BOOLEAN NOT NULL DEFAULT false,
            ADD COLUMN IF NOT EXISTS cancel_reason TEXT,
            ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ;
        CREATE INDEX IF NOT EXISTS idx_tasks_cancel_requested
            ON tasks(cancel_requested);

        ALTER TABLE tool_calls
            ADD COLUMN IF NOT EXISTS replay_of_tool_call_id UUID REFERENCES tool_calls(id),
            ADD COLUMN IF NOT EXISTS replay_reason TEXT;
        CREATE INDEX IF NOT EXISTS idx_tool_calls_replay_of
            ON tool_calls(replay_of_tool_call_id);
        """
    )


def downgrade() -> None:
    """回滚任务运行控制和 replay 字段。"""
    op.get_bind().exec_driver_sql(
        """
        ALTER TABLE tool_calls
            DROP COLUMN IF EXISTS replay_reason,
            DROP COLUMN IF EXISTS replay_of_tool_call_id;

        ALTER TABLE tasks
            DROP COLUMN IF EXISTS cancelled_at,
            DROP COLUMN IF EXISTS cancel_reason,
            DROP COLUMN IF EXISTS cancel_requested,
            DROP COLUMN IF EXISTS run_config;
        """
    )
