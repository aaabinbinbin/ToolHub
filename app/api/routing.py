from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.routing import ToolRouteRequest, ToolRouteResult
from app.services.tool_router_service import ToolRouterService

router = APIRouter(prefix="/api/router", tags=["router"])


def get_tool_router_service() -> ToolRouterService:
    """创建 ToolRouterService 依赖。

    测试时可以通过 FastAPI dependency_overrides 替换成 mock router。
    """
    return ToolRouterService()


@router.post("/select", response_model=ToolRouteResult)
def select_tool(
    request: ToolRouteRequest,
    service: ToolRouterService = Depends(get_tool_router_service),
) -> ToolRouteResult:
    """根据用户输入和意图选择工具。

    该接口不调用工具，只返回路由结果。
    """
    return service.select_tool(
        user_input=request.user_input,
        intent=request.intent,
        suggested_tool_type=request.suggested_tool_type,
        tool_input=request.tool_input,
    )
