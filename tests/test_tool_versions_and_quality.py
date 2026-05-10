from __future__ import annotations

from uuid import uuid4

from app.repositories.db import get_connection, init_db
from app.repositories.tool_call_repository import ToolCallRepository
from app.schemas.tool import RiskLevel, ToolRegisterRequest, ToolType
from app.schemas.tool_call import ToolCallResult
from app.services.tool_registry_service import ToolRegistryService


def test_register_tool_creates_version_snapshot_and_quality_updates() -> None:
    init_db()
    tool = ToolRegistryService().register_tool(
        ToolRegisterRequest(
            name=f"quality-test-{uuid4()}",
            description="Quality metric test tool",
            tool_type=ToolType.HTTP,
            endpoint="mock://echo",
            version="1.0.0",
            input_schema={"type": "object"},
            metadata={"Authorization": "Bearer secret"},
            risk_level=RiskLevel.LOW,
        )
    )

    with get_connection() as connection:
        version = connection.execute(
            "SELECT metadata FROM tool_versions WHERE tool_id = %(tool_id)s",
            {"tool_id": tool.id},
        ).fetchone()
        ToolCallRepository(connection).create(
            ToolCallResult(
                success=True,
                status="SUCCESS",
                tool_id=tool.id,
                tool_name=tool.name,
                tool_type=tool.tool_type.value,
                input={"token": "secret"},
                output={"ok": True},
                duration_ms=100,
                run_id=uuid4(),
                trace_id=uuid4(),
                workspace_id="default",
            )
        )
        refreshed = connection.execute(
            "SELECT success_rate, avg_duration_ms, quality_score FROM tools WHERE id = %(tool_id)s",
            {"tool_id": tool.id},
        ).fetchone()

    assert version["metadata"]["Authorization"] == "***REDACTED***"
    assert float(refreshed["success_rate"]) == 1.0
    assert refreshed["avg_duration_ms"] == 100
    assert float(refreshed["quality_score"]) > 0.9
