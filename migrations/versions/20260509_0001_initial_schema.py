"""initial schema

Revision ID: 20260509_0001
Revises:
Create Date: 2026-05-09
"""
from __future__ import annotations

from alembic import op


revision = "20260509_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建 ToolHub 初始数据库结构。"""
    op.get_bind().exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS tools (
            id UUID PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL,
            tool_type TEXT NOT NULL CHECK (tool_type IN ('MCP', 'HTTP', 'CLI', 'SANDBOX')),
            endpoint TEXT,
            mcp_url TEXT,
            transport TEXT,
            version TEXT NOT NULL,
            input_schema JSONB,
            output_schema JSONB,
            tags JSONB NOT NULL DEFAULT '[]'::jsonb,
            risk_level TEXT NOT NULL DEFAULT 'LOW' CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH')),
            status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'DISABLED', 'DELETED')),
            health_status TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK (health_status IN ('UNKNOWN', 'UP', 'DOWN')),
            last_checked_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_tools_type ON tools(tool_type);
        CREATE INDEX IF NOT EXISTS idx_tools_status ON tools(status);
        CREATE INDEX IF NOT EXISTS idx_tools_risk ON tools(risk_level);
        CREATE INDEX IF NOT EXISTS idx_tools_tags_gin ON tools USING GIN (tags);

        CREATE TABLE IF NOT EXISTS tasks (
            id UUID PRIMARY KEY,
            run_id UUID NOT NULL,
            trace_id UUID NOT NULL,
            user_input TEXT NOT NULL,
            run_mode TEXT NOT NULL DEFAULT 'SAFE_EXECUTE'
                CHECK (run_mode IN ('PLAN_ONLY', 'SAFE_EXECUTE', 'FULL_EXECUTE')),
            selected_tool_id UUID,
            priority TEXT NOT NULL DEFAULT 'default',
            status TEXT NOT NULL,
            current_step TEXT,
            retry_count INTEGER NOT NULL DEFAULT 0,
            max_retries INTEGER NOT NULL DEFAULT 3,
            error_message TEXT,
            result JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
        CREATE INDEX IF NOT EXISTS idx_tasks_run_id ON tasks(run_id);
        CREATE INDEX IF NOT EXISTS idx_tasks_trace_id ON tasks(trace_id);

        CREATE TABLE IF NOT EXISTS task_events (
            id UUID PRIMARY KEY,
            task_id UUID NOT NULL REFERENCES tasks(id),
            run_id UUID NOT NULL,
            trace_id UUID NOT NULL,
            event_type TEXT NOT NULL,
            step TEXT,
            message TEXT,
            payload JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_task_events_task_id ON task_events(task_id);
        CREATE INDEX IF NOT EXISTS idx_task_events_run_id ON task_events(run_id);
        CREATE INDEX IF NOT EXISTS idx_task_events_trace_id ON task_events(trace_id);

        CREATE TABLE IF NOT EXISTS tool_calls (
            id UUID PRIMARY KEY,
            task_id UUID REFERENCES tasks(id),
            run_id UUID NOT NULL,
            trace_id UUID NOT NULL,
            tool_id UUID NOT NULL REFERENCES tools(id),
            tool_name TEXT NOT NULL,
            tool_type TEXT NOT NULL,
            input JSONB,
            output JSONB,
            status TEXT NOT NULL,
            error_message TEXT,
            duration_ms INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_tool_calls_task_id ON tool_calls(task_id);
        CREATE INDEX IF NOT EXISTS idx_tool_calls_tool_id ON tool_calls(tool_id);

        CREATE TABLE IF NOT EXISTS sandbox_executions (
            id UUID PRIMARY KEY,
            task_id UUID REFERENCES tasks(id),
            run_id UUID NOT NULL,
            trace_id UUID NOT NULL,
            tool_name TEXT,
            command TEXT NOT NULL,
            stdout TEXT,
            stderr TEXT,
            exit_code INTEGER,
            duration_ms INTEGER,
            timeout_seconds INTEGER,
            container_id TEXT,
            status TEXT NOT NULL,
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_sandbox_task_id ON sandbox_executions(task_id);

        CREATE TABLE IF NOT EXISTS llm_calls (
            id UUID PRIMARY KEY,
            task_id UUID REFERENCES tasks(id),
            run_id UUID NOT NULL,
            trace_id UUID NOT NULL,
            node_name TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            prompt TEXT NOT NULL,
            response TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            duration_ms INTEGER,
            estimated_cost NUMERIC(12, 6),
            status TEXT NOT NULL,
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_llm_calls_task_id ON llm_calls(task_id);
        CREATE INDEX IF NOT EXISTS idx_llm_calls_node ON llm_calls(node_name);

        CREATE TABLE IF NOT EXISTS tool_health_checks (
            id UUID PRIMARY KEY,
            tool_id UUID NOT NULL REFERENCES tools(id),
            status TEXT NOT NULL,
            latency_ms INTEGER,
            error_message TEXT,
            checked_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_health_tool_id ON tool_health_checks(tool_id);

        CREATE TABLE IF NOT EXISTS tool_permissions (
            id UUID PRIMARY KEY,
            tool_id UUID REFERENCES tools(id),
            action TEXT NOT NULL,
            effect TEXT NOT NULL CHECK (effect IN ('ALLOW', 'ASK', 'DENY')),
            condition JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS approval_requests (
            id UUID PRIMARY KEY,
            task_id UUID NOT NULL REFERENCES tasks(id),
            run_id UUID NOT NULL,
            trace_id UUID NOT NULL,
            tool_id UUID REFERENCES tools(id),
            requested_action TEXT NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED')),
            requested_by TEXT,
            decided_by TEXT,
            decision_reason TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            decided_at TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS idx_approval_requests_task_id ON approval_requests(task_id);
        CREATE INDEX IF NOT EXISTS idx_approval_requests_status ON approval_requests(status);
        """
    )


def downgrade() -> None:
    """按依赖关系逆序删除 ToolHub 初始数据库结构。"""
    op.get_bind().exec_driver_sql(
        """
        DROP TABLE IF EXISTS approval_requests;
        DROP TABLE IF EXISTS tool_permissions;
        DROP TABLE IF EXISTS tool_health_checks;
        DROP TABLE IF EXISTS llm_calls;
        DROP TABLE IF EXISTS sandbox_executions;
        DROP TABLE IF EXISTS tool_calls;
        DROP TABLE IF EXISTS task_events;
        DROP TABLE IF EXISTS tasks;
        DROP TABLE IF EXISTS tools;
        """
    )
