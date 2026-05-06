from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.schemas.tool import ToolRegisterRequest, ToolResponse, ToolSearchResponse
from app.services.tool_registry_service import ToolRegistryService

router = APIRouter(prefix="/api/tools", tags=["tools"])


def get_tool_registry_service() -> ToolRegistryService:
    # FastAPI 依赖工厂：接口层不直接创建具体实现，测试时可用 app.dependency_overrides 替换。
    return ToolRegistryService()


@router.post(
    "/register", response_model=ToolResponse, status_code=status.HTTP_201_CREATED
)
def register_tool(
    request: ToolRegisterRequest,
    service: ToolRegistryService = Depends(get_tool_registry_service),
) -> ToolResponse:
    return service.register_tool(request)


@router.get("/search", response_model=ToolSearchResponse)
def search_tools(
    q: str = Query(default="", description="Keyword matched against name, description or tags"),
    include_disabled: bool = Query(default=False),
    service: ToolRegistryService = Depends(get_tool_registry_service),
) -> ToolSearchResponse:
    # 默认 include_disabled=False，避免禁用工具出现在 Agent 可选工具列表中。
    items = service.search_tools(q, include_disabled)
    return ToolSearchResponse(items=items, total=len(items))


@router.get("/{tool_id}", response_model=ToolResponse)
def get_tool(
    tool_id: UUID,
    service: ToolRegistryService = Depends(get_tool_registry_service),
) -> ToolResponse:
    return service.get_tool(tool_id)


@router.patch("/{tool_id}/enable", response_model=ToolResponse)
def enable_tool(
    tool_id: UUID,
    service: ToolRegistryService = Depends(get_tool_registry_service),
) -> ToolResponse:
    return service.enable_tool(tool_id)


@router.patch("/{tool_id}/disable", response_model=ToolResponse)
def disable_tool(
    tool_id: UUID,
    service: ToolRegistryService = Depends(get_tool_registry_service),
) -> ToolResponse:
    return service.disable_tool(tool_id)


@router.delete("/{tool_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tool(
    tool_id: UUID,
    service: ToolRegistryService = Depends(get_tool_registry_service),
) -> Response:
    service.delete_tool(tool_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
