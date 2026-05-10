from __future__ import annotations

from uuid import uuid4

from app.repositories.db import get_connection, init_db
from app.repositories.tool_call_repository import ToolCallRepository
from app.schemas.tool import RiskLevel, ToolRegisterRequest, ToolType
from app.schemas.tool_call import ToolCallReplayRequest, ToolCallResult
from app.services.tool_registry_service import ToolRegistryService
from app.services.tool_replay_service import ToolReplayService


class FakeDispatcher:
    def __init__(self) -> None:
        self.kwargs = None

    def dispatch(self, **kwargs):
        self.kwargs = kwargs
        return ToolCallResult(
            success=True,
            status="SUCCESS",
            tool_id=kwargs["tool"].id,
            tool_name=kwargs["tool"].name,
            tool_type=kwargs["tool"].tool_type.value,
            input=kwargs["tool_input"],
            output={"ok": True},
            duration_ms=1,
            run_id=kwargs["run_id"],
            trace_id=kwargs["trace_id"],
            task_id=kwargs["task_id"],
            user_id=kwargs["user_id"],
            workspace_id=kwargs["workspace_id"],
            replay_of_tool_call_id=kwargs["replay_of_tool_call_id"],
            replay_reason=kwargs["replay_reason"],
        )


def test_tool_call_replay_uses_original_input_and_tracks_source() -> None:
    init_db()
    tool = ToolRegistryService().register_tool(
        ToolRegisterRequest(
            name=f"replay-test-{uuid4()}",
            description="Replay test tool",
            tool_type=ToolType.HTTP,
            endpoint="mock://echo",
            risk_level=RiskLevel.LOW,
        )
    )
    run_id = uuid4()
    trace_id = uuid4()
    with get_connection() as connection:
        source_id = ToolCallRepository(connection).create(
            ToolCallResult(
                success=False,
                status="FAILED",
                tool_id=tool.id,
                tool_name=tool.name,
                tool_type=tool.tool_type.value,
                input={"q": "old"},
                output={"error": "bad"},
                error_message="bad",
                duration_ms=10,
                run_id=run_id,
                trace_id=trace_id,
                workspace_id="default",
            )
        )

    dispatcher = FakeDispatcher()
    result = ToolReplayService(dispatcher=dispatcher).replay_tool_call(
        source_id,
        ToolCallReplayRequest(reason="debug"),
    )

    assert result.success is True
    assert result.input == {"q": "old"}
    assert result.replay_of_tool_call_id == source_id
    assert dispatcher.kwargs["replay_reason"] == "debug"
