from __future__ import annotations

from uuid import UUID

from app.common.exceptions import NotFoundError
from app.repositories.db import get_connection
from app.repositories.task_event_repository import TaskEventRepository
from app.repositories.tool_call_repository import ToolCallRepository
from app.repositories.tool_repository import ToolRepository
from app.schemas.tool import ToolResponse
from app.schemas.tool_call import ToolCallReplayRequest, ToolCallResult
from app.tools.dispatcher import ToolAdapterDispatcher


class ToolReplayService:
    """重放历史工具调用，便于调试失败输入或复现实验结果。"""

    def __init__(self, dispatcher: ToolAdapterDispatcher | None = None) -> None:
        self.dispatcher = dispatcher or ToolAdapterDispatcher()

    def replay_tool_call(
        self,
        tool_call_id: UUID,
        request: ToolCallReplayRequest,
    ) -> ToolCallResult:
        """使用历史 tool_input 重新执行同一个工具，可选择覆盖输入。"""
        with get_connection() as connection:
            tool_call = ToolCallRepository(connection).get_by_id(tool_call_id)
            if tool_call is None:
                raise NotFoundError(f"Tool call not found: {tool_call_id}")

            tool = ToolRepository(connection).get_by_id(tool_call["tool_id"])
            if tool is None:
                raise NotFoundError(f"Tool not found: {tool_call['tool_id']}")

        replay_input = request.override_input or tool_call.get("input") or {}
        result = self.dispatcher.dispatch(
            tool=ToolResponse.model_validate(tool),
            tool_input=replay_input,
            task_id=tool_call.get("task_id"),
            run_id=tool_call["run_id"],
            trace_id=tool_call["trace_id"],
            user_id=request.user_id or tool_call.get("user_id"),
            workspace_id=request.workspace_id or tool_call.get("workspace_id"),
            replay_of_tool_call_id=tool_call_id,
            replay_reason=request.reason,
        )

        if tool_call.get("task_id") is not None:
            with get_connection() as connection:
                TaskEventRepository(connection).create(
                    task_id=tool_call["task_id"],
                    run_id=tool_call["run_id"],
                    trace_id=tool_call["trace_id"],
                    event_type="TOOL_CALL_REPLAYED",
                    step="tool_call_replay",
                    message="已重放一次历史工具调用。",
                    payload={
                        "source_tool_call_id": str(tool_call_id),
                        "status": result.status,
                        "reason": request.reason,
                    },
                    user_id=request.user_id or tool_call.get("user_id"),
                    workspace_id=request.workspace_id or tool_call.get("workspace_id"),
                )
        return result
