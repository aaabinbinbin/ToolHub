from __future__ import annotations

from fastapi import APIRouter, Depends

from uuid import UUID

from app.schemas.tool_call import (
    ToolCallReplayRequest,
    ToolCallRequest,
    ToolCallResult,
)
from app.services.tool_replay_service import ToolReplayService
from app.services.tool_registry_service import ToolRegistryService
from app.tools.dispatcher import ToolAdapterDispatcher

router = APIRouter(prefix="/api/tool-calls", tags=["tool-calls"])


def get_tool_registry_service() -> ToolRegistryService:
    """创建 ToolRegistryService 依赖。"""
    return ToolRegistryService()


def get_tool_adapter_dispatcher() -> ToolAdapterDispatcher:
    """创建 ToolAdapterDispatcher 依赖。"""
    return ToolAdapterDispatcher()


def get_tool_replay_service() -> ToolReplayService:
    """创建 ToolReplayService 依赖。"""
    return ToolReplayService()


@router.post("/execute", response_model=ToolCallResult)
def execute_tool(
    request: ToolCallRequest,
    tool_registry_service: ToolRegistryService = Depends(get_tool_registry_service),
    dispatcher: ToolAdapterDispatcher = Depends(get_tool_adapter_dispatcher),
) -> ToolCallResult:
    """执行一次工具调用。

    该接口用于验证 MCP / HTTP / CLI / SANDBOX 四类 Adapter 是否可调用。
    """
    tool = tool_registry_service.get_tool(request.tool_id)
    # plan 接口生成task_id、run_id、trace_id
    return dispatcher.dispatch(
        tool=tool,
        tool_input=request.tool_input,
        task_id=request.task_id,
        run_id=request.run_id,
        trace_id=request.trace_id,
        user_id=request.user_id,
        workspace_id=request.workspace_id,
    )


@router.post("/{tool_call_id}/replay", response_model=ToolCallResult)
def replay_tool_call(
    tool_call_id: UUID,
    request: ToolCallReplayRequest,
    service: ToolReplayService = Depends(get_tool_replay_service),
) -> ToolCallResult:
    """重放一次历史工具调用，可选择覆盖原始输入。"""
    return service.replay_tool_call(tool_call_id, request)
