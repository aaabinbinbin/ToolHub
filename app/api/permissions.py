from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.permission import PermissionCheckRequest, PermissionCheckResponse
from app.security.permission_engine import PermissionEngine
from app.services.tool_registry_service import ToolRegistryService

router = APIRouter(prefix="/api/permissions", tags=["permissions"])


def get_permission_engine() -> PermissionEngine:
    """创建 PermissionEngine 依赖。"""
    return PermissionEngine()


def get_tool_registry_service() -> ToolRegistryService:
    """创建 ToolRegistryService 依赖。"""
    return ToolRegistryService()


@router.post("/check", response_model=PermissionCheckResponse)
def check_permission(
    request: PermissionCheckRequest,
    permission_engine: PermissionEngine = Depends(get_permission_engine),
    tool_registry_service: ToolRegistryService = Depends(get_tool_registry_service),
) -> PermissionCheckResponse:
    """检查某个工具在当前 run_mode 下是否允许执行。

    该接口用于单独调试 PermissionEngine，不会写 task_events。
    """
    tool = tool_registry_service.get_tool(request.tool_id)
    permission = permission_engine.check(tool, request.run_mode)
    return PermissionCheckResponse(tool=tool, permission=permission)
